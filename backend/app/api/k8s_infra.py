"""Admin API for K8S infrastructure configuration and scrape."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.k8s_inventory import (
    DEFAULT_CRON_EXPR,
    DEFAULT_INFRA_TYPE,
    delete_k8s_cluster,
    get_cluster_shape_analysis,
    get_k8s_cluster,
    list_infra_clusters,
    save_k8s_clusters,
)
from backend.app.db.shape_detail import (
    get_shape_namespace_detail,
    get_shape_node_detail,
    get_shape_vm_detail,
    list_shape_namespaces,
    list_shape_nodes,
    list_shape_vms,
)
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.k8s_collector import (
    KubeconfigRequiredError,
    collect_and_persist_cluster,
)
from backend.app.services.kubevirt_collector import collect_and_persist_kubevirt

router = APIRouter(tags=["k8s-infra"])


class K8sClusterItem(BaseModel):
    idx: int
    cluster_name: str
    last_update: str | None = None
    cron: bool = False
    cron_expr: str = DEFAULT_CRON_EXPR
    infra_type: str = DEFAULT_INFRA_TYPE


class K8sClusterSaveItem(BaseModel):
    idx: int | None = None
    cluster_name: str
    cron: bool = False
    cron_expr: str = DEFAULT_CRON_EXPR
    infra_type: str = DEFAULT_INFRA_TYPE


class K8sClusterSaveRequest(BaseModel):
    clusters: list[K8sClusterSaveItem] = Field(default_factory=list)


class ManualCollectResponse(BaseModel):
    idx: int
    cluster_name: str
    last_update: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)
    backup_tables: list[str] = Field(default_factory=list)


class K8sShapeClusterItem(BaseModel):
    idx: int
    cluster_name: str
    last_update: str | None = None
    infra_type: str = DEFAULT_INFRA_TYPE


class K8sShapeCountsModel(BaseModel):
    nodes: int = 0
    namespaces: int = 0
    deployments: int = 0
    pvcs: int = 0
    vms: int = 0
    volumes: int = 0


class K8sShapeHistoryPointModel(BaseModel):
    label: str
    stamp: str | None = None
    is_latest: bool = False
    counts: K8sShapeCountsModel


class K8sShapeAnalysisResponse(BaseModel):
    cluster_name: str
    last_update: str | None = None
    cluster_version: str | None = None
    infra_type: str = DEFAULT_INFRA_TYPE
    summary: K8sShapeCountsModel
    history: list[K8sShapeHistoryPointModel] = Field(default_factory=list)


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _require_user(request: Request) -> None:
    get_request_auth_user(request)


def _to_item(record) -> K8sClusterItem:
    return K8sClusterItem(
        idx=record.idx,
        cluster_name=record.cluster_name,
        last_update=record.last_update,
        cron=bool(record.cron),
        cron_expr=record.cron_expr or DEFAULT_CRON_EXPR,
        infra_type=record.infra_type or DEFAULT_INFRA_TYPE,
    )


@router.get("/k8s-infra/clusters", response_model=list[K8sClusterItem])
async def list_clusters(request: Request) -> list[K8sClusterItem]:
    _require_admin(request)
    records = list_infra_clusters(request.app.state.database_path)
    return [_to_item(record) for record in records]


@router.post("/k8s-infra/clusters/save", response_model=list[K8sClusterItem])
async def save_clusters(
    payload: K8sClusterSaveRequest,
    request: Request,
) -> list[K8sClusterItem]:
    _require_admin(request)
    try:
        records = save_k8s_clusters(
            request.app.state.database_path,
            [item.model_dump() for item in payload.clusters],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"저장 실패: {exc}") from exc

    return [_to_item(record) for record in records]


@router.delete("/k8s-infra/clusters/{cluster_idx}", response_model=dict[str, bool])
async def remove_cluster(cluster_idx: int, request: Request) -> dict[str, bool]:
    _require_admin(request)
    deleted = delete_k8s_cluster(request.app.state.database_path, cluster_idx)
    if not deleted:
        raise HTTPException(status_code=404, detail="클러스터를 찾을 수 없습니다.")
    return {"ok": True}


@router.post(
    "/k8s-infra/clusters/{cluster_idx}/collect",
    response_model=ManualCollectResponse,
)
async def collect_cluster(cluster_idx: int, request: Request) -> ManualCollectResponse:
    _require_admin(request)
    database_path = Path(request.app.state.database_path)
    record = get_k8s_cluster(database_path, cluster_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="클러스터를 찾을 수 없습니다.")
    if record.infra_type not in {DEFAULT_INFRA_TYPE, "kubevirt"}:
        raise HTTPException(
            status_code=400,
            detail=f"수집은 infra_type k8s|kubevirt 만 지원합니다 (got {record.infra_type}).",
        )

    runtime_mode = getattr(request.app.state, "agent_runtime_mode", None) or "mock"
    try:
        if record.infra_type == "kubevirt":
            result = await asyncio.to_thread(
                collect_and_persist_kubevirt,
                database_path,
                cluster_idx=record.idx,
                cluster_name=record.cluster_name,
                runtime_mode=runtime_mode,
            )
        else:
            result = await asyncio.to_thread(
                collect_and_persist_cluster,
                database_path,
                cluster_idx=record.idx,
                cluster_name=record.cluster_name,
                runtime_mode=runtime_mode,
            )
    except KubeconfigRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"수집 실패: {exc}") from exc

    backups = result.get("backup_tables") or []
    if isinstance(backups, int):
        backups = []

    return ManualCollectResponse(
        idx=record.idx,
        cluster_name=record.cluster_name,
        last_update=str(result.get("last_update") or "") or None,
        counts={
            key: value
            for key, value in result.items()
            if key not in {"last_update", "backup_tables", "pruned_backup_tables"}
        },
        backup_tables=[str(name) for name in backups],
    )


def _shape_counts_model(counts) -> K8sShapeCountsModel:
    return K8sShapeCountsModel(
        nodes=counts.nodes,
        namespaces=counts.namespaces,
        deployments=counts.deployments,
        pvcs=counts.pvcs,
        vms=getattr(counts, "vms", 0) or 0,
        volumes=getattr(counts, "volumes", 0) or 0,
    )


@router.get("/k8s-infra/shape/clusters", response_model=list[K8sShapeClusterItem])
async def list_shape_clusters(request: Request) -> list[K8sShapeClusterItem]:
    """Authenticated users: cluster labels for infra shape analysis."""
    _require_user(request)
    records = list_infra_clusters(request.app.state.database_path)
    return [
        K8sShapeClusterItem(
            idx=record.idx,
            cluster_name=record.cluster_name,
            last_update=record.last_update,
            infra_type=record.infra_type or DEFAULT_INFRA_TYPE,
        )
        for record in records
    ]


@router.get(
    "/k8s-infra/shape/clusters/{cluster_name}",
    response_model=K8sShapeAnalysisResponse,
)
async def get_shape_analysis(
    cluster_name: str,
    request: Request,
) -> K8sShapeAnalysisResponse:
    """Authenticated users: summary + history (live + up to 4 backups)."""
    _require_user(request)
    try:
        analysis = get_cluster_shape_analysis(
            request.app.state.database_path,
            cluster_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if analysis is None:
        raise HTTPException(status_code=404, detail="클러스터를 찾을 수 없습니다.")

    return K8sShapeAnalysisResponse(
        cluster_name=analysis.cluster_name,
        last_update=analysis.last_update,
        cluster_version=analysis.cluster_version,
        infra_type=analysis.infra_type or DEFAULT_INFRA_TYPE,
        summary=_shape_counts_model(analysis.summary),
        history=[
            K8sShapeHistoryPointModel(
                label=point.label,
                stamp=point.stamp,
                is_latest=point.is_latest,
                counts=_shape_counts_model(point.counts),
            )
            for point in analysis.history
        ],
    )


class ShapeNamespaceListItemModel(BaseModel):
    idx: int
    namespace: str
    okd_display_name: str | None = None
    resource_quota_cpu_limit: float | None = None
    resource_quota_mem_limit: int | None = None
    resource_quota_pod_limit: int | None = None
    okd_egressip1: str | None = None
    okd_egressip2: str | None = None
    using_egressip: str | None = None
    egressip_assigned_node: str | None = None


class ShapeNodeListItemModel(BaseModel):
    idx: int
    node_name: str
    node_cpu: int | None = None
    node_mem: int | None = None
    node_os: str | None = None
    node_k8s_ver: str | None = None
    node_role: str | None = None


class ShapeVmListItemModel(BaseModel):
    idx: int
    name: str
    namespace: str | None = None
    run_strategy: str | None = None
    printable_status: str | None = None
    ready: bool | None = None
    vmi_phase: str | None = None
    node_name: str | None = None
    ip_address: str | None = None
    cpu_cores: float | None = None
    memory_gi: int | None = None


class ShapeNamespaceDetailResponse(BaseModel):
    namespace: dict[str, Any] = Field(default_factory=dict)
    deployments: list[dict[str, Any]] = Field(default_factory=list)
    pvcs: list[dict[str, Any]] = Field(default_factory=list)


class ShapeNodeDetailResponse(BaseModel):
    node: dict[str, Any] = Field(default_factory=dict)
    pods: list[dict[str, Any]] = Field(default_factory=list)


class ShapeVmDetailResponse(BaseModel):
    vm: dict[str, Any] = Field(default_factory=dict)
    volumes: list[dict[str, Any]] = Field(default_factory=list)


@router.get(
    "/k8s-infra/shape/clusters/{cluster_name}/namespaces",
    response_model=list[ShapeNamespaceListItemModel],
)
async def shape_list_namespaces(
    cluster_name: str,
    request: Request,
) -> list[ShapeNamespaceListItemModel]:
    _require_user(request)
    try:
        items = list_shape_namespaces(request.app.state.database_path, cluster_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if items is None:
        raise HTTPException(status_code=404, detail="클러스터를 찾을 수 없습니다.")
    return [
        ShapeNamespaceListItemModel(
            idx=item.idx,
            namespace=item.namespace,
            okd_display_name=item.okd_display_name,
            resource_quota_cpu_limit=item.resource_quota_cpu_limit,
            resource_quota_mem_limit=item.resource_quota_mem_limit,
            resource_quota_pod_limit=item.resource_quota_pod_limit,
            okd_egressip1=item.okd_egressip1,
            okd_egressip2=item.okd_egressip2,
            using_egressip=item.using_egressip,
            egressip_assigned_node=item.egressip_assigned_node,
        )
        for item in items
    ]


@router.get(
    "/k8s-infra/shape/clusters/{cluster_name}/namespaces/{namespace_idx}",
    response_model=ShapeNamespaceDetailResponse,
)
async def shape_get_namespace(
    cluster_name: str,
    namespace_idx: int,
    request: Request,
) -> ShapeNamespaceDetailResponse:
    _require_user(request)
    try:
        detail = get_shape_namespace_detail(
            request.app.state.database_path,
            cluster_name,
            namespace_idx,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="네임스페이스를 찾을 수 없습니다.")
    return ShapeNamespaceDetailResponse(
        namespace=detail.namespace,
        deployments=detail.deployments,
        pvcs=detail.pvcs,
    )


@router.get(
    "/k8s-infra/shape/clusters/{cluster_name}/nodes",
    response_model=list[ShapeNodeListItemModel],
)
async def shape_list_nodes(
    cluster_name: str,
    request: Request,
) -> list[ShapeNodeListItemModel]:
    _require_user(request)
    try:
        items = list_shape_nodes(request.app.state.database_path, cluster_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if items is None:
        raise HTTPException(status_code=404, detail="클러스터를 찾을 수 없습니다.")
    return [
        ShapeNodeListItemModel(
            idx=item.idx,
            node_name=item.node_name,
            node_cpu=item.node_cpu,
            node_mem=item.node_mem,
            node_os=item.node_os,
            node_k8s_ver=item.node_k8s_ver,
        )
        for item in items
    ]


@router.get(
    "/k8s-infra/shape/clusters/{cluster_name}/nodes/{node_idx}",
    response_model=ShapeNodeDetailResponse,
)
async def shape_get_node(
    cluster_name: str,
    node_idx: int,
    request: Request,
) -> ShapeNodeDetailResponse:
    _require_user(request)
    try:
        detail = get_shape_node_detail(
            request.app.state.database_path,
            cluster_name,
            node_idx,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다.")
    return ShapeNodeDetailResponse(node=detail.node, pods=detail.pods)


@router.get(
    "/k8s-infra/shape/clusters/{cluster_name}/vms",
    response_model=list[ShapeVmListItemModel],
)
async def shape_list_vms(
    cluster_name: str,
    request: Request,
) -> list[ShapeVmListItemModel]:
    _require_user(request)
    try:
        items = list_shape_vms(request.app.state.database_path, cluster_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if items is None:
        raise HTTPException(status_code=404, detail="클러스터를 찾을 수 없습니다.")
    return [
        ShapeVmListItemModel(
            idx=item.idx,
            name=item.name,
            namespace=item.namespace,
            run_strategy=item.run_strategy,
            printable_status=item.printable_status,
            ready=item.ready,
            vmi_phase=item.vmi_phase,
            node_name=item.node_name,
            ip_address=item.ip_address,
            cpu_cores=item.cpu_cores,
            memory_gi=item.memory_gi,
        )
        for item in items
    ]


@router.get(
    "/k8s-infra/shape/clusters/{cluster_name}/vms/{vm_idx}",
    response_model=ShapeVmDetailResponse,
)
async def shape_get_vm(
    cluster_name: str,
    vm_idx: int,
    request: Request,
) -> ShapeVmDetailResponse:
    _require_user(request)
    try:
        detail = get_shape_vm_detail(
            request.app.state.database_path,
            cluster_name,
            vm_idx,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="VM을 찾을 수 없습니다.")
    return ShapeVmDetailResponse(vm=detail.vm, volumes=detail.volumes)
