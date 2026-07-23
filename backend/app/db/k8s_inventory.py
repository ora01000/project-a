"""Persist Kubernetes inventory snapshots into SQLite k8s_* tables."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.timezone import format_display_datetime, now_display_datetime

logger = logging.getLogger(__name__)


@dataclass
class K8sNodeRow:
    node_name: str
    node_cpu: int | None = None
    node_mem: int | None = None
    node_os: str | None = None
    node_k8s_ver: str | None = None


@dataclass
class K8sNamespaceRow:
    namespace: str
    okd_display_name: str | None = None
    resource_quota_cpu_limit: float | None = None
    resource_quota_mem_limit: int | None = None
    resource_quota_pod_limit: int | None = None
    okd_egressip1: str | None = None
    okd_egressip2: str | None = None


@dataclass
class K8sDeploymentRow:
    namespace: str
    name: str
    type: str
    replicas: int | None = None
    resource_cpu_request: float | None = None
    resource_mem_request: int | None = None
    resource_cpu_limit: float | None = None
    resource_mem_limit: int | None = None
    containers_cnt: int | None = None
    containers_name: list[str] = field(default_factory=list)
    containers_image: list[str] = field(default_factory=list)


@dataclass
class K8sPvcRow:
    namespace: str
    name: str
    deployment_name: str | None = None
    deployment_type: str | None = None
    storage_class: str | None = None
    capacity: int | None = None
    used: int | None = None
    access_mode: str | None = None


@dataclass
class K8sPodRow:
    namespace: str
    name: str
    deployment_name: str | None = None
    deployment_type: str | None = None
    scheduled_node_name: str | None = None


@dataclass
class K8sClusterSnapshot:
    cluster_name: str
    nodes: list[K8sNodeRow] = field(default_factory=list)
    namespaces: list[K8sNamespaceRow] = field(default_factory=list)
    deployments: list[K8sDeploymentRow] = field(default_factory=list)
    pvcs: list[K8sPvcRow] = field(default_factory=list)
    pods: list[K8sPodRow] = field(default_factory=list)


def _json_list(values: list[str], max_len: int) -> str | None:
    if not values:
        return "[]"
    payload = json.dumps(values, ensure_ascii=False)
    if len(payload) <= max_len:
        return payload
    truncated: list[str] = []
    for value in values:
        candidate = truncated + [value]
        encoded = json.dumps(candidate, ensure_ascii=False)
        if len(encoded) > max_len:
            break
        truncated = candidate
    return json.dumps(truncated, ensure_ascii=False)


def get_or_create_k8s_cluster(connection, cluster_name: str) -> int:
    name = cluster_name.strip()
    if not name:
        raise ValueError("cluster_name is required")
    truncated = name[:50]

    row = connection.execute(
        "SELECT idx FROM k8s_cluster WHERE cluster_name = ?",
        (truncated,),
    ).fetchone()
    if row is not None:
        return int(row["idx"])

    cursor = connection.execute(
        """
        INSERT INTO k8s_cluster (cluster_name, last_update)
        VALUES (?, NULL)
        """,
        (truncated,),
    )
    return int(cursor.lastrowid)


def touch_k8s_cluster_last_update(
    connection,
    cluster_id: int,
    *,
    when: datetime | None = None,
) -> str:
    stamp = format_display_datetime(when) if when is not None else format_display_datetime()
    connection.execute(
        """
        UPDATE k8s_cluster
        SET last_update = ?
        WHERE idx = ?
        """,
        (stamp, cluster_id),
    )
    return stamp


def replace_cluster_snapshot(database_path: str | Path, snapshot: K8sClusterSnapshot) -> dict[str, int]:
    cluster_name = snapshot.cluster_name.strip()
    if not cluster_name:
        raise ValueError("cluster_name is required")

    with get_connection(database_path) as connection:
        cluster_id = get_or_create_k8s_cluster(connection, cluster_name)

        connection.execute("DELETE FROM k8s_pods WHERE cluster_id = ?", (cluster_id,))
        connection.execute("DELETE FROM k8s_pvcs WHERE cluster_id = ?", (cluster_id,))
        connection.execute("DELETE FROM k8s_deployments WHERE cluster_id = ?", (cluster_id,))
        connection.execute("DELETE FROM k8s_namespaces WHERE cluster_id = ?", (cluster_id,))
        connection.execute("DELETE FROM k8s_nodes WHERE cluster_id = ?", (cluster_id,))

        node_ids: dict[str, int] = {}
        for node in snapshot.nodes:
            cursor = connection.execute(
                """
                INSERT INTO k8s_nodes (
                    cluster_id, node_name, node_cpu, node_mem, node_os, node_k8s_ver
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster_id,
                    node.node_name[:50],
                    node.node_cpu,
                    node.node_mem,
                    (node.node_os or None) and node.node_os[:50],
                    (node.node_k8s_ver or None) and node.node_k8s_ver[:50],
                ),
            )
            node_ids[node.node_name] = int(cursor.lastrowid)

        namespace_ids: dict[str, int] = {}
        for namespace in snapshot.namespaces:
            cursor = connection.execute(
                """
                INSERT INTO k8s_namespaces (
                    cluster_id, namespace, okd_display_name,
                    resource_quota_cpu_limit, resource_quota_mem_limit, resource_quota_pod_limit,
                    okd_egressip1, okd_egressip2
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster_id,
                    namespace.namespace[:50],
                    (namespace.okd_display_name or None) and namespace.okd_display_name[:100],
                    namespace.resource_quota_cpu_limit,
                    namespace.resource_quota_mem_limit,
                    namespace.resource_quota_pod_limit,
                    (namespace.okd_egressip1 or None) and namespace.okd_egressip1[:20],
                    (namespace.okd_egressip2 or None) and namespace.okd_egressip2[:20],
                ),
            )
            namespace_ids[namespace.namespace] = int(cursor.lastrowid)

        deployment_ids: dict[tuple[str, str, str], int] = {}
        for deployment in snapshot.deployments:
            namespace_id = namespace_ids.get(deployment.namespace)
            if namespace_id is None:
                continue
            cursor = connection.execute(
                """
                INSERT INTO k8s_deployments (
                    cluster_id, namespace_id, name, type, replicas,
                    resource_cpu_request, resource_mem_request,
                    resource_cpu_limit, resource_mem_limit,
                    containers_cnt, containers_name, containers_image
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster_id,
                    namespace_id,
                    deployment.name[:50],
                    deployment.type[:20],
                    deployment.replicas,
                    deployment.resource_cpu_request,
                    deployment.resource_mem_request,
                    deployment.resource_cpu_limit,
                    deployment.resource_mem_limit,
                    deployment.containers_cnt,
                    _json_list(deployment.containers_name, 300),
                    _json_list(deployment.containers_image, 500),
                ),
            )
            deployment_ids[(deployment.namespace, deployment.name, deployment.type)] = int(
                cursor.lastrowid
            )

        for pvc in snapshot.pvcs:
            namespace_id = namespace_ids.get(pvc.namespace)
            if namespace_id is None:
                continue
            deployment_id = None
            if pvc.deployment_name and pvc.deployment_type:
                deployment_id = deployment_ids.get(
                    (pvc.namespace, pvc.deployment_name, pvc.deployment_type)
                )
            connection.execute(
                """
                INSERT INTO k8s_pvcs (
                    cluster_id, namespace_id, deployment_id, name, storage_class,
                    capacity, used, access_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster_id,
                    namespace_id,
                    deployment_id,
                    pvc.name[:50],
                    (pvc.storage_class or None) and pvc.storage_class[:20],
                    pvc.capacity,
                    pvc.used,
                    (pvc.access_mode or None) and pvc.access_mode[:20],
                ),
            )

        for pod in snapshot.pods:
            namespace_id = namespace_ids.get(pod.namespace)
            if namespace_id is None:
                continue
            deployment_id = None
            if pod.deployment_name and pod.deployment_type:
                deployment_id = deployment_ids.get(
                    (pod.namespace, pod.deployment_name, pod.deployment_type)
                )
            scheduled_node = (
                node_ids.get(pod.scheduled_node_name) if pod.scheduled_node_name else None
            )
            connection.execute(
                """
                INSERT INTO k8s_pods (
                    cluster_id, namespace_id, deployment_id, name, scheduled_node
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cluster_id,
                    namespace_id,
                    deployment_id,
                    pod.name[:50],
                    scheduled_node,
                ),
            )

        last_update = touch_k8s_cluster_last_update(connection, cluster_id)
        connection.commit()

    counts = {
        "cluster_id": cluster_id,
        "nodes": len(snapshot.nodes),
        "namespaces": len(snapshot.namespaces),
        "deployments": len(snapshot.deployments),
        "pvcs": len(snapshot.pvcs),
        "pods": len(snapshot.pods),
    }
    logger.info(
        "Replaced k8s inventory for cluster_name=%s cluster_id=%s last_update=%s counts=%s",
        cluster_name,
        cluster_id,
        last_update,
        counts,
    )
    return counts


def get_k8s_cluster_last_updates(database_path: str | Path) -> dict[str, str | None]:
    """Return map of cluster_name -> last_update (ISO-like local stamp or None)."""
    with get_connection(database_path) as connection:
        rows = connection.execute(
            "SELECT cluster_name, last_update FROM k8s_cluster ORDER BY cluster_name"
        ).fetchall()
    return {
        str(row["cluster_name"]): (str(row["last_update"]) if row["last_update"] else None)
        for row in rows
    }


def snapshot_to_debug_dict(snapshot: K8sClusterSnapshot) -> dict[str, Any]:
    return {
        "cluster_name": snapshot.cluster_name,
        "nodes": len(snapshot.nodes),
        "namespaces": len(snapshot.namespaces),
        "deployments": len(snapshot.deployments),
        "pvcs": len(snapshot.pvcs),
        "pods": len(snapshot.pods),
    }
