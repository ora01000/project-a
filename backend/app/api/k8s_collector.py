import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.agents.k8s_agent import K8S_CLUSTER_SPECS
from backend.app.db.k8s_inventory import get_k8s_cluster_last_updates
from backend.app.db.roles import ROLE_ADMIN
from backend.app.services.k8s_collector_loop import collect_one_cluster

router = APIRouter(tags=["k8s-collector"])


class K8sCollectorClusterItem(BaseModel):
    agent_id: str
    display_name: str
    last_update: str | None = None
    operation_status: str = "idle"
    operation_detail: str | None = None


class ManualCollectRequest(BaseModel):
    viewer_role: int


class ManualCollectResponse(BaseModel):
    agent_id: str
    display_name: str
    last_update: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)


def _require_admin(viewer_role: int) -> None:
    if viewer_role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _known_cluster_ids() -> set[str]:
    return {cluster_id for cluster_id, _ in K8S_CLUSTER_SPECS}


@router.get("/k8s-collector/clusters", response_model=list[K8sCollectorClusterItem])
async def list_k8s_collector_clusters(
    request: Request,
    viewer_role: int,
) -> list[K8sCollectorClusterItem]:
    _require_admin(viewer_role)
    manager = request.app.state.agent_manager
    last_updates = get_k8s_cluster_last_updates(request.app.state.database_path)
    return [
        K8sCollectorClusterItem(
            agent_id=cluster_id,
            display_name=display_name,
            last_update=last_updates.get(cluster_id),
            operation_status=manager.get_operation_status(cluster_id),
            operation_detail=manager.get_operation_detail(cluster_id),
        )
        for cluster_id, display_name in K8S_CLUSTER_SPECS
    ]


@router.post(
    "/k8s-collector/clusters/{cluster_id}/collect",
    response_model=ManualCollectResponse,
)
async def collect_k8s_cluster_manual(
    cluster_id: str,
    payload: ManualCollectRequest,
    request: Request,
) -> ManualCollectResponse:
    _require_admin(payload.viewer_role)
    if cluster_id not in _known_cluster_ids():
        raise HTTPException(status_code=404, detail=f"알 수 없는 클러스터입니다: {cluster_id}")

    display_name = next(
        (name for cid, name in K8S_CLUSTER_SPECS if cid == cluster_id),
        cluster_id,
    )
    manager = request.app.state.agent_manager
    database_path = Path(request.app.state.database_path)

    try:
        counts = await asyncio.to_thread(
            collect_one_cluster,
            database_path,
            cluster_id,
            agent_manager=manager,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"수집 실패: {exc}") from exc

    last_updates = get_k8s_cluster_last_updates(database_path)
    return ManualCollectResponse(
        agent_id=cluster_id,
        display_name=display_name,
        last_update=last_updates.get(cluster_id),
        counts=counts,
    )
