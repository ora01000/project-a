"""Persist KubeVirt inventory into per-cluster dynamic SQLite tables.

Layout (infra_type=kubevirt):
  {cluster_name}_kubevirt_nodes
  {cluster_name}_kubevirt_namespaces
  {cluster_name}_kubevirt_deployments
  {cluster_name}_kubevirt_pvcs
  {cluster_name}_kubevirt_vms
  {cluster_name}_kubevirt_vm_volumes

Backups: {table}_{YYYYMMDD_HHMMSS} (keep newest 4 stamp sets).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.db.k8s_inventory import (
    K8sDeploymentRow,
    K8sNamespaceRow,
    K8sNodeRow,
    K8sPvcRow,
    MAX_INVENTORY_BACKUP_GENERATIONS,
    _BACKUP_STAMP_SUFFIX_RE,
    _json_list,
    _list_user_tables,
    _quote_ident,
    format_backup_stamp,
    touch_k8s_cluster_last_update,
    validate_cluster_name,
)

logger = logging.getLogger(__name__)

KUBEVIRT_INVENTORY_SUFFIXES = (
    "kubevirt_nodes",
    "kubevirt_namespaces",
    "kubevirt_deployments",
    "kubevirt_pvcs",
    "kubevirt_vms",
    "kubevirt_vm_volumes",
)


@dataclass
class KubevirtVmRow:
    namespace: str
    name: str
    run_strategy: str | None = None
    printable_status: str | None = None
    ready: bool | None = None
    vmi_phase: str | None = None
    node_name: str | None = None
    ip_address: str | None = None
    cpu_cores: float | None = None
    memory_gi: int | None = None
    disk_count: int | None = None
    network_count: int | None = None
    volume_names: list[str] = field(default_factory=list)
    os_info: str | None = None
    created_at: str | None = None


@dataclass
class KubevirtVmVolumeRow:
    namespace: str
    vm_name: str
    volume_name: str
    pvc_name: str | None = None
    capacity_gi: int | None = None


@dataclass
class KubevirtClusterSnapshot:
    cluster_name: str
    nodes: list[K8sNodeRow] = field(default_factory=list)
    namespaces: list[K8sNamespaceRow] = field(default_factory=list)
    deployments: list[K8sDeploymentRow] = field(default_factory=list)
    pvcs: list[K8sPvcRow] = field(default_factory=list)
    vms: list[KubevirtVmRow] = field(default_factory=list)
    vm_volumes: list[KubevirtVmVolumeRow] = field(default_factory=list)


def kubevirt_inventory_table(cluster_name: str, suffix: str) -> str:
    name = validate_cluster_name(cluster_name)
    if suffix not in KUBEVIRT_INVENTORY_SUFFIXES:
        raise ValueError(f"unknown kubevirt inventory suffix: {suffix}")
    return f"{name}_{suffix}"


def kubevirt_inventory_tables(cluster_name: str) -> tuple[str, ...]:
    return tuple(
        kubevirt_inventory_table(cluster_name, suffix)
        for suffix in KUBEVIRT_INVENTORY_SUFFIXES
    )


def ensure_kubevirt_inventory_tables(
    connection,
    cluster_name: str,
) -> dict[str, str]:
    """Create kubevirt inventory tables if missing. Returns suffix -> table name."""
    name = validate_cluster_name(cluster_name)
    tables = _list_user_tables(connection)
    nodes_t = kubevirt_inventory_table(name, "kubevirt_nodes")
    ns_t = kubevirt_inventory_table(name, "kubevirt_namespaces")
    dep_t = kubevirt_inventory_table(name, "kubevirt_deployments")
    pvc_t = kubevirt_inventory_table(name, "kubevirt_pvcs")
    vms_t = kubevirt_inventory_table(name, "kubevirt_vms")
    vol_t = kubevirt_inventory_table(name, "kubevirt_vm_volumes")

    if nodes_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(nodes_t)} (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                node_name VARCHAR(50) NOT NULL,
                node_cpu INTEGER,
                node_mem INTEGER,
                node_os VARCHAR(50),
                node_k8s_ver VARCHAR(50)
            )
            """
        )
    if ns_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(ns_t)} (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace VARCHAR(50) NOT NULL,
                okd_display_name VARCHAR(100),
                resource_quota_cpu_limit REAL,
                resource_quota_mem_limit INTEGER,
                resource_quota_pod_limit INTEGER,
                okd_egressip1 VARCHAR(20),
                okd_egressip2 VARCHAR(20),
                using_egressip VARCHAR(20),
                egressip_assigned_node VARCHAR(50)
            )
            """
        )
    if dep_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(dep_t)} (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace_id INTEGER NOT NULL,
                name VARCHAR(50) NOT NULL,
                type VARCHAR(20) NOT NULL,
                replicas INTEGER,
                resource_cpu_request REAL,
                resource_mem_request INTEGER,
                resource_cpu_limit REAL,
                resource_mem_limit INTEGER,
                containers_cnt INTEGER,
                containers_name VARCHAR(300),
                containers_image VARCHAR(500),
                FOREIGN KEY (namespace_id) REFERENCES {_quote_ident(ns_t)}(idx)
            )
            """
        )
    if pvc_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(pvc_t)} (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace_id INTEGER NOT NULL,
                deployment_id INTEGER,
                name VARCHAR(50) NOT NULL,
                storage_class VARCHAR(20),
                capacity INTEGER,
                used INTEGER,
                access_mode VARCHAR(20),
                FOREIGN KEY (namespace_id) REFERENCES {_quote_ident(ns_t)}(idx),
                FOREIGN KEY (deployment_id) REFERENCES {_quote_ident(dep_t)}(idx)
            )
            """
        )
    if vms_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(vms_t)} (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace_id INTEGER NOT NULL,
                name VARCHAR(50) NOT NULL,
                run_strategy VARCHAR(20),
                printable_status VARCHAR(30),
                ready INTEGER,
                vmi_phase VARCHAR(20),
                node_name VARCHAR(50),
                ip_address VARCHAR(45),
                cpu_cores REAL,
                memory_gi INTEGER,
                disk_count INTEGER,
                network_count INTEGER,
                volume_names VARCHAR(300),
                os_info VARCHAR(100),
                created_at TEXT,
                FOREIGN KEY (namespace_id) REFERENCES {_quote_ident(ns_t)}(idx)
            )
            """
        )
    if vol_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(vol_t)} (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                vm_id INTEGER NOT NULL,
                volume_name VARCHAR(50),
                pvc_name VARCHAR(50),
                capacity_gi INTEGER,
                FOREIGN KEY (vm_id) REFERENCES {_quote_ident(vms_t)}(idx)
            )
            """
        )
    return {
        "nodes": nodes_t,
        "namespaces": ns_t,
        "deployments": dep_t,
        "pvcs": pvc_t,
        "vms": vms_t,
        "vm_volumes": vol_t,
    }


def backup_kubevirt_inventory_tables(
    connection,
    cluster_name: str,
    *,
    stamp: str,
) -> list[str]:
    created: list[str] = []
    safe_stamp = re.sub(r"[^0-9_]", "", stamp) or format_backup_stamp(None)
    tables = _list_user_tables(connection)
    for table_name in kubevirt_inventory_tables(cluster_name):
        if table_name not in tables:
            continue
        backup_name = f"{table_name}_{safe_stamp}"
        connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(backup_name)}")
        connection.execute(
            f"CREATE TABLE {_quote_ident(backup_name)} AS "
            f"SELECT * FROM {_quote_ident(table_name)}"
        )
        created.append(backup_name)
    if created:
        logger.info("Backed up kubevirt cluster=%s -> %s", cluster_name, created)
    return created


def _backup_stamp_from_table(live_table: str, table_name: str) -> str | None:
    prefix = f"{live_table}_"
    if not table_name.startswith(prefix):
        return None
    stamp = table_name[len(prefix) :]
    if _BACKUP_STAMP_SUFFIX_RE.fullmatch(stamp):
        return stamp
    return None


def list_kubevirt_inventory_backup_stamps(connection, cluster_name: str) -> list[str]:
    stamps: set[str] = set()
    tables = _list_user_tables(connection)
    for live_table in kubevirt_inventory_tables(cluster_name):
        for table_name in tables:
            stamp = _backup_stamp_from_table(live_table, table_name)
            if stamp:
                stamps.add(stamp)
    return sorted(stamps, reverse=True)


def prune_kubevirt_inventory_backups(
    connection,
    cluster_name: str,
    *,
    keep: int = MAX_INVENTORY_BACKUP_GENERATIONS,
) -> list[str]:
    keep_n = max(0, int(keep))
    stamps = list_kubevirt_inventory_backup_stamps(connection, cluster_name)
    stale = set(stamps[keep_n:])
    if not stale:
        return []
    dropped: list[str] = []
    tables = _list_user_tables(connection)
    for live_table in kubevirt_inventory_tables(cluster_name):
        for table_name in sorted(tables):
            stamp = _backup_stamp_from_table(live_table, table_name)
            if stamp is None or stamp not in stale:
                continue
            connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
            dropped.append(table_name)
            tables.discard(table_name)
    if dropped:
        logger.info(
            "Pruned kubevirt cluster=%s backups keep=%s dropped=%s",
            cluster_name,
            keep_n,
            dropped,
        )
    return dropped


def drop_kubevirt_inventory_tables(connection, cluster_name: str) -> list[str]:
    dropped: list[str] = []
    try:
        prefixes = [
            f"{validate_cluster_name(cluster_name)}_{suffix}"
            for suffix in KUBEVIRT_INVENTORY_SUFFIXES
        ]
    except ValueError:
        return dropped
    tables = _list_user_tables(connection)
    for table_name in sorted(tables, reverse=True):
        for prefix in prefixes:
            if table_name == prefix or table_name.startswith(f"{prefix}_"):
                connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
                dropped.append(table_name)
                break
    if dropped:
        logger.info("Dropped kubevirt cluster=%s tables: %s", cluster_name, dropped)
    return dropped


def rename_kubevirt_inventory_tables(
    connection,
    old_name: str,
    new_name: str,
) -> list[tuple[str, str]]:
    if old_name == new_name:
        return []
    renamed: list[tuple[str, str]] = []
    tables = _list_user_tables(connection)
    for suffix in KUBEVIRT_INVENTORY_SUFFIXES:
        old_table = f"{old_name}_{suffix}"
        new_table = f"{new_name}_{suffix}"
        if old_table not in tables:
            continue
        if new_table in tables:
            connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(new_table)}")
        connection.execute(
            f"ALTER TABLE {_quote_ident(old_table)} RENAME TO {_quote_ident(new_table)}"
        )
        renamed.append((old_table, new_table))
    return renamed


def replace_kubevirt_snapshot(
    database_path: str | Path,
    snapshot: KubevirtClusterSnapshot,
    *,
    cluster_idx: int | None = None,
) -> dict[str, Any]:
    cluster_name = validate_cluster_name(snapshot.cluster_name)

    with get_connection(database_path) as connection:
        if cluster_idx is not None:
            row = connection.execute(
                """
                SELECT idx, cluster_name, last_update, infra_type
                FROM infra_cluster WHERE idx = ?
                """,
                (cluster_idx,),
            ).fetchone()
            if row is None:
                raise ValueError(f"cluster idx not found: {cluster_idx}")
            cluster_id = int(row["idx"])
            cluster_name = validate_cluster_name(str(row["cluster_name"]))
            previous_last_update = (
                str(row["last_update"]) if row["last_update"] else None
            )
        else:
            raise ValueError("kubevirt replace requires cluster_idx")

        stamp = format_backup_stamp(previous_last_update)
        backups = backup_kubevirt_inventory_tables(
            connection, cluster_name, stamp=stamp
        )
        pruned = prune_kubevirt_inventory_backups(connection, cluster_name)
        table_map = ensure_kubevirt_inventory_tables(connection, cluster_name)
        nodes_t = table_map["nodes"]
        ns_t = table_map["namespaces"]
        dep_t = table_map["deployments"]
        pvc_t = table_map["pvcs"]
        vms_t = table_map["vms"]
        vol_t = table_map["vm_volumes"]

        connection.execute(f"DELETE FROM {_quote_ident(vol_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(vms_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(pvc_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(dep_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(ns_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(nodes_t)}")

        for node in snapshot.nodes:
            connection.execute(
                f"""
                INSERT INTO {_quote_ident(nodes_t)} (
                    node_name, node_cpu, node_mem, node_os, node_k8s_ver
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    node.node_name[:50],
                    node.node_cpu,
                    node.node_mem,
                    (node.node_os or None) and node.node_os[:50],
                    (node.node_k8s_ver or None) and node.node_k8s_ver[:50],
                ),
            )

        namespace_ids: dict[str, int] = {}
        for namespace in snapshot.namespaces:
            cursor = connection.execute(
                f"""
                INSERT INTO {_quote_ident(ns_t)} (
                    namespace, okd_display_name,
                    resource_quota_cpu_limit, resource_quota_mem_limit,
                    resource_quota_pod_limit,
                    okd_egressip1, okd_egressip2,
                    using_egressip, egressip_assigned_node
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace.namespace[:50],
                    (namespace.okd_display_name or None)
                    and namespace.okd_display_name[:100],
                    namespace.resource_quota_cpu_limit,
                    namespace.resource_quota_mem_limit,
                    namespace.resource_quota_pod_limit,
                    (namespace.okd_egressip1 or None) and namespace.okd_egressip1[:20],
                    (namespace.okd_egressip2 or None) and namespace.okd_egressip2[:20],
                    (namespace.using_egressip or None) and namespace.using_egressip[:20],
                    (namespace.egressip_assigned_node or None)
                    and namespace.egressip_assigned_node[:50],
                ),
            )
            namespace_ids[namespace.namespace] = int(cursor.lastrowid)

        deployment_ids: dict[tuple[str, str, str], int] = {}
        for deployment in snapshot.deployments:
            namespace_id = namespace_ids.get(deployment.namespace)
            if namespace_id is None:
                continue
            cursor = connection.execute(
                f"""
                INSERT INTO {_quote_ident(dep_t)} (
                    namespace_id, name, type, replicas,
                    resource_cpu_request, resource_mem_request,
                    resource_cpu_limit, resource_mem_limit,
                    containers_cnt, containers_name, containers_image
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
                f"""
                INSERT INTO {_quote_ident(pvc_t)} (
                    namespace_id, deployment_id, name, storage_class,
                    capacity, used, access_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace_id,
                    deployment_id,
                    pvc.name[:50],
                    (pvc.storage_class or None) and pvc.storage_class[:20],
                    pvc.capacity,
                    pvc.used,
                    (pvc.access_mode or None) and pvc.access_mode[:20],
                ),
            )

        vm_ids: dict[tuple[str, str], int] = {}
        for vm in snapshot.vms:
            namespace_id = namespace_ids.get(vm.namespace)
            if namespace_id is None:
                continue
            cursor = connection.execute(
                f"""
                INSERT INTO {_quote_ident(vms_t)} (
                    namespace_id, name, run_strategy, printable_status, ready,
                    vmi_phase, node_name, ip_address, cpu_cores, memory_gi,
                    disk_count, network_count, volume_names, os_info, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace_id,
                    vm.name[:50],
                    (vm.run_strategy or None) and vm.run_strategy[:20],
                    (vm.printable_status or None) and vm.printable_status[:30],
                    None if vm.ready is None else (1 if vm.ready else 0),
                    (vm.vmi_phase or None) and vm.vmi_phase[:20],
                    (vm.node_name or None) and vm.node_name[:50],
                    (vm.ip_address or None) and vm.ip_address[:45],
                    vm.cpu_cores,
                    vm.memory_gi,
                    vm.disk_count,
                    vm.network_count,
                    _json_list(vm.volume_names, 300),
                    (vm.os_info or None) and vm.os_info[:100],
                    vm.created_at,
                ),
            )
            vm_ids[(vm.namespace, vm.name)] = int(cursor.lastrowid)

        for volume in snapshot.vm_volumes:
            vm_id = vm_ids.get((volume.namespace, volume.vm_name))
            if vm_id is None:
                continue
            connection.execute(
                f"""
                INSERT INTO {_quote_ident(vol_t)} (
                    vm_id, volume_name, pvc_name, capacity_gi
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    vm_id,
                    (volume.volume_name or "")[:50] or None,
                    (volume.pvc_name or None) and volume.pvc_name[:50],
                    volume.capacity_gi,
                ),
            )

        last_update = touch_k8s_cluster_last_update(connection, cluster_id)
        connection.commit()

    counts = {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "infra_type": "kubevirt",
        "tables": table_map,
        "nodes": len(snapshot.nodes),
        "namespaces": len(snapshot.namespaces),
        "deployments": len(snapshot.deployments),
        "pvcs": len(snapshot.pvcs),
        "vms": len(snapshot.vms),
        "vm_volumes": len(snapshot.vm_volumes),
    }
    logger.info(
        "Replaced kubevirt inventory cluster=%s idx=%s last_update=%s "
        "counts=%s backups=%s pruned=%s",
        cluster_name,
        cluster_id,
        last_update,
        counts,
        backups,
        pruned,
    )
    return {
        **counts,
        "last_update": last_update,
        "backup_tables": backups,
        "pruned_backup_tables": pruned,
    }
