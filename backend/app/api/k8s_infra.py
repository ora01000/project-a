"""Admin API for K8S infrastructure configuration and scrape."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.k8s_inventory import (
    delete_k8s_cluster,
    get_k8s_cluster,
    list_k8s_clusters,
    save_k8s_clusters,
)
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.k8s_collector import (
    KubeconfigRequiredError,
    collect_and_persist_cluster,
)

router = APIRouter(tags=["k8s-infra"])


class K8sClusterItem(BaseModel):
    idx: int
    cluster_name: str
    last_update: str | None = None


class K8sClusterSaveItem(BaseModel):
    idx: int | None = None
    cluster_name: str


class K8sClusterSaveRequest(BaseModel):
    clusters: list[K8sClusterSaveItem] = Field(default_factory=list)


class ManualCollectResponse(BaseModel):
    idx: int
    cluster_name: str
    last_update: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)
    backup_tables: list[str] = Field(default_factory=list)


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


@router.get("/k8s-infra/clusters", response_model=list[K8sClusterItem])
async def list_clusters(request: Request) -> list[K8sClusterItem]:
    _require_admin(request)
    records = list_k8s_clusters(request.app.state.database_path)
    return [
        K8sClusterItem(
            idx=record.idx,
            cluster_name=record.cluster_name,
            last_update=record.last_update,
        )
        for record in records
    ]


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

    return [
        K8sClusterItem(
            idx=record.idx,
            cluster_name=record.cluster_name,
            last_update=record.last_update,
        )
        for record in records
    ]


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

    runtime_mode = getattr(request.app.state, "agent_runtime_mode", None) or "mock"
    try:
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
            if key not in {"last_update", "backup_tables"}
        },
        backup_tables=[str(name) for name in backups],
    )
