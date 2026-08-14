"""Read inventory rows for infra shape detail panel (k8s / kubevirt)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.db.introspection import ci_order_clause
from backend.app.db.k8s_inventory import (
    DEFAULT_INFRA_TYPE,
    INFRA_TYPE_VSPHERE,
    SCRAPEABLE_INFRA_TYPES,
    SHAPEABLE_INFRA_TYPES,
    _drop_namespace_readyreplicas_column,
    _ensure_deployment_readyreplicas_column,
    _ensure_namespace_egress_columns,
    _ensure_node_role_column,
    _list_user_tables,
    _quote_ident,
    cluster_inventory_table,
    cluster_inventory_tables,
    validate_cluster_name,
)


def _row_to_dict(row) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    return dict(row)


@dataclass
class ShapeNamespaceListItem:
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


@dataclass
class ShapeNodeListItem:
    idx: int
    node_name: str
    node_cpu: int | None = None
    node_mem: int | None = None
    node_os: str | None = None
    node_k8s_ver: str | None = None
    node_role: str | None = None


@dataclass
class ShapeVmListItem:
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


@dataclass
class ShapeNamespaceDetail:
    namespace: dict[str, Any]
    deployments: list[dict[str, Any]] = field(default_factory=list)
    pvcs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ShapeNodeDetail:
    node: dict[str, Any]
    pods: list[dict[str, Any]] = field(default_factory=list)
    vms: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ShapeVmDetail:
    vm: dict[str, Any]
    volumes: list[dict[str, Any]] = field(default_factory=list)


def _lookup_infra_type(connection, cluster_name: str) -> str | None:
    """Return scrapeable (k8s/kubevirt) infra type for inventory detail paths."""
    row = connection.execute(
        """
        SELECT infra_type FROM infra_cluster WHERE cluster_name = ?
        """,
        (cluster_name,),
    ).fetchone()
    if row is None:
        return None
    infra_type = str(row["infra_type"] or DEFAULT_INFRA_TYPE).strip() or DEFAULT_INFRA_TYPE
    if infra_type not in SCRAPEABLE_INFRA_TYPES:
        return None
    return infra_type


def _lookup_shapeable_infra_type(connection, cluster_name: str) -> str | None:
    row = connection.execute(
        """
        SELECT infra_type FROM infra_cluster WHERE cluster_name = ?
        """,
        (cluster_name,),
    ).fetchone()
    if row is None:
        return None
    infra_type = str(row["infra_type"] or DEFAULT_INFRA_TYPE).strip() or DEFAULT_INFRA_TYPE
    if infra_type not in SHAPEABLE_INFRA_TYPES:
        return None
    return infra_type


def _pods_on_nodes_table(cluster_name: str, infra_type: str) -> str:
    if infra_type == "kubevirt":
        from backend.app.db.kubevirt_inventory import kubevirt_inventory_table

        return kubevirt_inventory_table(cluster_name, "kubevirt_pods_on_nodes")
    return cluster_inventory_table(cluster_name, "k8s_pods_on_nodes")


def _inventory_core_tables(
    cluster_name: str,
    infra_type: str,
) -> tuple[str, str, str, str]:
    if infra_type == "kubevirt":
        from backend.app.db.kubevirt_inventory import kubevirt_inventory_tables

        nodes_t, ns_t, dep_t, pvc_t, _, _, _ = kubevirt_inventory_tables(cluster_name)
        return nodes_t, ns_t, dep_t, pvc_t
    nodes_t, ns_t, dep_t, pvc_t, _ = cluster_inventory_tables(cluster_name)
    return nodes_t, ns_t, dep_t, pvc_t


def _kubevirt_vm_tables(cluster_name: str) -> tuple[str, str, str]:
    from backend.app.db.kubevirt_inventory import kubevirt_inventory_tables

    _, ns_t, _, _, vms_t, vol_t, _ = kubevirt_inventory_tables(cluster_name)
    return ns_t, vms_t, vol_t


def list_shape_namespaces(
    database_path: str | Path,
    cluster_name: str,
) -> list[ShapeNamespaceListItem] | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_infra_type(connection, name)
        if infra_type is None:
            return None
        _, ns_t, _, _ = _inventory_core_tables(name, infra_type)
        tables = _list_user_tables(connection)
        if ns_t not in tables:
            return []
        _ensure_namespace_egress_columns(connection, ns_t)
        _drop_namespace_readyreplicas_column(connection, ns_t)
        rows = connection.execute(
            f"""
            SELECT
                idx,
                namespace,
                okd_display_name,
                resource_quota_cpu_limit,
                resource_quota_mem_limit,
                resource_quota_pod_limit,
                okd_egressip1,
                okd_egressip2,
                using_egressip,
                egressip_assigned_node
            FROM {_quote_ident(ns_t)}
            ORDER BY {ci_order_clause(connection, "namespace")}, idx ASC
            """
        ).fetchall()
    return [
        ShapeNamespaceListItem(
            idx=int(row["idx"]),
            namespace=str(row["namespace"] or ""),
            okd_display_name=(
                str(row["okd_display_name"]) if row["okd_display_name"] else None
            ),
            resource_quota_cpu_limit=(
                float(row["resource_quota_cpu_limit"])
                if row["resource_quota_cpu_limit"] is not None
                else None
            ),
            resource_quota_mem_limit=(
                int(row["resource_quota_mem_limit"])
                if row["resource_quota_mem_limit"] is not None
                else None
            ),
            resource_quota_pod_limit=(
                int(row["resource_quota_pod_limit"])
                if row["resource_quota_pod_limit"] is not None
                else None
            ),
            okd_egressip1=str(row["okd_egressip1"]) if row["okd_egressip1"] else None,
            okd_egressip2=str(row["okd_egressip2"]) if row["okd_egressip2"] else None,
            using_egressip=(
                str(row["using_egressip"]) if row["using_egressip"] else None
            ),
            egressip_assigned_node=(
                str(row["egressip_assigned_node"])
                if row["egressip_assigned_node"]
                else None
            ),
        )
        for row in rows
    ]


def get_shape_namespace_detail(
    database_path: str | Path,
    cluster_name: str,
    namespace_idx: int,
) -> ShapeNamespaceDetail | None:
    name = validate_cluster_name(cluster_name)
    ns_idx = int(namespace_idx)
    with get_connection(database_path) as connection:
        infra_type = _lookup_infra_type(connection, name)
        if infra_type is None:
            return None
        _, ns_t, dep_t, pvc_t = _inventory_core_tables(name, infra_type)
        tables = _list_user_tables(connection)
        if ns_t not in tables:
            return None
        ns_row = connection.execute(
            f"""
            SELECT * FROM {_quote_ident(ns_t)} WHERE idx = ?
            """,
            (ns_idx,),
        ).fetchone()
        if ns_row is None:
            return None

        deployments: list[dict[str, Any]] = []
        if dep_t in tables:
            _ensure_deployment_readyreplicas_column(connection, dep_t)
            dep_rows = connection.execute(
                f"""
                SELECT * FROM {_quote_ident(dep_t)}
                WHERE namespace_id = ?
                ORDER BY {ci_order_clause(connection, "name")}, idx ASC
                """,
                (ns_idx,),
            ).fetchall()
            deployments = [_row_to_dict(row) for row in dep_rows]

        pvcs: list[dict[str, Any]] = []
        if pvc_t in tables:
            pvc_rows = connection.execute(
                f"""
                SELECT * FROM {_quote_ident(pvc_t)}
                WHERE namespace_id = ?
                ORDER BY {ci_order_clause(connection, "name")}, idx ASC
                """,
                (ns_idx,),
            ).fetchall()
            pvcs = [_row_to_dict(row) for row in pvc_rows]

    return ShapeNamespaceDetail(
        namespace=_row_to_dict(ns_row),
        deployments=deployments,
        pvcs=pvcs,
    )


def list_shape_nodes(
    database_path: str | Path,
    cluster_name: str,
) -> list[ShapeNodeListItem] | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_infra_type(connection, name)
        if infra_type is None:
            return None
        nodes_t, _, _, _ = _inventory_core_tables(name, infra_type)
        tables = _list_user_tables(connection)
        if nodes_t not in tables:
            return []
        _ensure_node_role_column(connection, nodes_t)
        rows = connection.execute(
            f"""
            SELECT idx, node_name, node_cpu, node_mem, node_os, node_k8s_ver, node_role
            FROM {_quote_ident(nodes_t)}
            ORDER BY {ci_order_clause(connection, "node_name")}, idx ASC
            """
        ).fetchall()
    return [
        ShapeNodeListItem(
            idx=int(row["idx"]),
            node_name=str(row["node_name"] or ""),
            node_cpu=int(row["node_cpu"]) if row["node_cpu"] is not None else None,
            node_mem=int(row["node_mem"]) if row["node_mem"] is not None else None,
            node_os=str(row["node_os"]) if row["node_os"] else None,
            node_k8s_ver=str(row["node_k8s_ver"]) if row["node_k8s_ver"] else None,
            node_role=str(row["node_role"]) if row["node_role"] else None,
        )
        for row in rows
    ]


def get_shape_node_detail(
    database_path: str | Path,
    cluster_name: str,
    node_idx: int,
) -> ShapeNodeDetail | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_infra_type(connection, name)
        if infra_type is None:
            return None
        nodes_t, _, _, _ = _inventory_core_tables(name, infra_type)
        tables = _list_user_tables(connection)
        if nodes_t not in tables:
            return None
        row = connection.execute(
            f"""
            SELECT * FROM {_quote_ident(nodes_t)} WHERE idx = ?
            """,
            (int(node_idx),),
        ).fetchone()
        if row is None:
            return None
        node = _row_to_dict(row)
        node_name = str(node.get("node_name") or "")
        pods: list[dict[str, Any]] = []
        pods_t = _pods_on_nodes_table(name, infra_type)
        if node_name and pods_t in tables:
            pod_rows = connection.execute(
                f"""
                SELECT
                    idx, node_name, namespace, pod_name,
                    cpu_request, cpu_limit, mem_request, mem_limit, age
                FROM {_quote_ident(pods_t)}
                WHERE node_name = ?
                ORDER BY {ci_order_clause(connection, "namespace")},
                         {ci_order_clause(connection, "pod_name")}, idx ASC
                """,
                (node_name,),
            ).fetchall()
            pods = [_row_to_dict(pod_row) for pod_row in pod_rows]

        vms: list[dict[str, Any]] = []
        if infra_type == "kubevirt" and node_name:
            ns_t, vms_t, _ = _kubevirt_vm_tables(name)
            if vms_t in tables:
                if ns_t in tables:
                    vm_rows = connection.execute(
                        f"""
                        SELECT
                            v.idx AS idx,
                            v.name AS name,
                            n.namespace AS namespace,
                            v.run_strategy AS run_strategy,
                            v.printable_status AS printable_status,
                            v.ready AS ready,
                            v.vmi_phase AS vmi_phase,
                            v.node_name AS node_name,
                            v.ip_address AS ip_address,
                            v.cpu_cores AS cpu_cores,
                            v.memory_gi AS memory_gi
                        FROM {_quote_ident(vms_t)} AS v
                        LEFT JOIN {_quote_ident(ns_t)} AS n ON n.idx = v.namespace_id
                        WHERE v.node_name = ?
                        ORDER BY {ci_order_clause(connection, "n.namespace", "v.name")},
                                 v.idx ASC
                        """,
                        (node_name,),
                    ).fetchall()
                else:
                    vm_rows = connection.execute(
                        f"""
                        SELECT
                            idx,
                            name,
                            NULL AS namespace,
                            run_strategy,
                            printable_status,
                            ready,
                            vmi_phase,
                            node_name,
                            ip_address,
                            cpu_cores,
                            memory_gi
                        FROM {_quote_ident(vms_t)}
                        WHERE node_name = ?
                        ORDER BY {ci_order_clause(connection, "name")}, idx ASC
                        """,
                        (node_name,),
                    ).fetchall()
                vms = [_row_to_dict(vm_row) for vm_row in vm_rows]
        return ShapeNodeDetail(node=node, pods=pods, vms=vms)


def list_shape_vms(
    database_path: str | Path,
    cluster_name: str,
) -> list[ShapeVmListItem] | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_infra_type(connection, name)
        if infra_type is None:
            return None
        if infra_type != "kubevirt":
            return []
        ns_t, vms_t, _ = _kubevirt_vm_tables(name)
        tables = _list_user_tables(connection)
        if vms_t not in tables:
            return []
        if ns_t in tables:
            rows = connection.execute(
                f"""
                SELECT
                    v.idx AS idx,
                    v.name AS name,
                    n.namespace AS namespace,
                    v.run_strategy AS run_strategy,
                    v.printable_status AS printable_status,
                    v.ready AS ready,
                    v.vmi_phase AS vmi_phase,
                    v.node_name AS node_name,
                    v.ip_address AS ip_address,
                    v.cpu_cores AS cpu_cores,
                    v.memory_gi AS memory_gi
                FROM {_quote_ident(vms_t)} AS v
                LEFT JOIN {_quote_ident(ns_t)} AS n ON n.idx = v.namespace_id
                ORDER BY {ci_order_clause(connection, "n.namespace", "v.name")}, v.idx ASC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT
                    idx,
                    name,
                    NULL AS namespace,
                    run_strategy,
                    printable_status,
                    ready,
                    vmi_phase,
                    node_name,
                    ip_address,
                    cpu_cores,
                    memory_gi
                FROM {_quote_ident(vms_t)}
                ORDER BY {ci_order_clause(connection, "name")}, idx ASC
                """
            ).fetchall()
    return [
        ShapeVmListItem(
            idx=int(row["idx"]),
            name=str(row["name"] or ""),
            namespace=str(row["namespace"]) if row["namespace"] else None,
            run_strategy=(
                str(row["run_strategy"]) if row["run_strategy"] else None
            ),
            printable_status=(
                str(row["printable_status"]) if row["printable_status"] else None
            ),
            ready=bool(row["ready"]) if row["ready"] is not None else None,
            vmi_phase=str(row["vmi_phase"]) if row["vmi_phase"] else None,
            node_name=str(row["node_name"]) if row["node_name"] else None,
            ip_address=str(row["ip_address"]) if row["ip_address"] else None,
            cpu_cores=(
                float(row["cpu_cores"]) if row["cpu_cores"] is not None else None
            ),
            memory_gi=(
                int(row["memory_gi"]) if row["memory_gi"] is not None else None
            ),
        )
        for row in rows
    ]


def get_shape_vm_detail(
    database_path: str | Path,
    cluster_name: str,
    vm_idx: int,
) -> ShapeVmDetail | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_infra_type(connection, name)
        if infra_type is None or infra_type != "kubevirt":
            return None
        ns_t, vms_t, vol_t = _kubevirt_vm_tables(name)
        tables = _list_user_tables(connection)
        if vms_t not in tables:
            return None
        if ns_t in tables:
            row = connection.execute(
                f"""
                SELECT
                    v.*,
                    n.namespace AS namespace
                FROM {_quote_ident(vms_t)} AS v
                LEFT JOIN {_quote_ident(ns_t)} AS n ON n.idx = v.namespace_id
                WHERE v.idx = ?
                """,
                (int(vm_idx),),
            ).fetchone()
        else:
            row = connection.execute(
                f"""
                SELECT *, NULL AS namespace
                FROM {_quote_ident(vms_t)}
                WHERE idx = ?
                """,
                (int(vm_idx),),
            ).fetchone()
        if row is None:
            return None

        volumes: list[dict[str, Any]] = []
        if vol_t in tables:
            vol_rows = connection.execute(
                f"""
                SELECT * FROM {_quote_ident(vol_t)}
                WHERE vm_id = ?
                ORDER BY {ci_order_clause(connection, "volume_name")}, idx ASC
                """,
                (int(vm_idx),),
            ).fetchall()
            volumes = [_row_to_dict(item) for item in vol_rows]

    return ShapeVmDetail(vm=_row_to_dict(row), volumes=volumes)


@dataclass
class ShapeVsphereClusterListItem:
    idx: int
    cluster_id: str
    cluster_name: str | None = None
    ha_enabled: bool | None = None
    drs_enabled: bool | None = None


@dataclass
class ShapeVsphereHostListItem:
    idx: int
    host_id: str
    host_name: str | None = None
    connection_state: str | None = None
    power_state: str | None = None
    cluster_id: str | None = None
    cpu_count: int | None = None
    memory_mib: int | None = None


@dataclass
class ShapeVsphereVmListItem:
    idx: int
    vm_id: str
    host_id: str
    vm_name: str | None = None
    power_state: str | None = None
    cpu_count: int | None = None
    memory_mib: int | None = None


@dataclass
class ShapeVsphereClusterDetail:
    cluster: dict[str, Any]
    hosts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ShapeVsphereHostDetail:
    host: dict[str, Any]
    vms: list[dict[str, Any]] = field(default_factory=list)


def _as_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return bool(value)


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_shape_vsphere_clusters(
    database_path: str | Path,
    cluster_name: str,
) -> list[ShapeVsphereClusterListItem] | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_shapeable_infra_type(connection, name)
        if infra_type != INFRA_TYPE_VSPHERE:
            return None
        from backend.app.db.vsphere_inventory import vsphere_inventory_table

        clusters_t = vsphere_inventory_table(name, "vsphere_cluster")
        tables = _list_user_tables(connection)
        if clusters_t not in tables:
            return []
        rows = connection.execute(
            f"""
            SELECT idx, cluster_id, cluster_name, ha_enabled, drs_enabled
            FROM {_quote_ident(clusters_t)}
            ORDER BY {ci_order_clause(connection, "cluster_name")}, idx ASC
            """
        ).fetchall()
    return [
        ShapeVsphereClusterListItem(
            idx=int(row["idx"]),
            cluster_id=str(row["cluster_id"] or ""),
            cluster_name=str(row["cluster_name"]) if row["cluster_name"] else None,
            ha_enabled=_as_optional_bool(row["ha_enabled"]),
            drs_enabled=_as_optional_bool(row["drs_enabled"]),
        )
        for row in rows
    ]


def get_shape_vsphere_cluster_detail(
    database_path: str | Path,
    cluster_name: str,
    cluster_idx: int,
) -> ShapeVsphereClusterDetail | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_shapeable_infra_type(connection, name)
        if infra_type != INFRA_TYPE_VSPHERE:
            return None
        from backend.app.db.vsphere_inventory import vsphere_inventory_table

        clusters_t = vsphere_inventory_table(name, "vsphere_cluster")
        hosts_t = vsphere_inventory_table(name, "vsphere_hosts")
        tables = _list_user_tables(connection)
        if clusters_t not in tables:
            return None
        row = connection.execute(
            f"""
            SELECT * FROM {_quote_ident(clusters_t)} WHERE idx = ?
            """,
            (int(cluster_idx),),
        ).fetchone()
        if row is None:
            return None
        cluster = _row_to_dict(row)
        cluster_id = str(cluster.get("cluster_id") or "")
        hosts: list[dict[str, Any]] = []
        if cluster_id and hosts_t in tables:
            host_rows = connection.execute(
                f"""
                SELECT *
                FROM {_quote_ident(hosts_t)}
                WHERE cluster_id = ?
                ORDER BY {ci_order_clause(connection, "host_name")}, idx ASC
                """,
                (cluster_id,),
            ).fetchall()
            hosts = [_row_to_dict(item) for item in host_rows]
    return ShapeVsphereClusterDetail(cluster=cluster, hosts=hosts)


def list_shape_vsphere_hosts(
    database_path: str | Path,
    cluster_name: str,
) -> list[ShapeVsphereHostListItem] | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_shapeable_infra_type(connection, name)
        if infra_type != INFRA_TYPE_VSPHERE:
            return None
        from backend.app.db.vsphere_inventory import (
            _ensure_hosts_hardware_columns,
            vsphere_inventory_table,
        )

        hosts_t = vsphere_inventory_table(name, "vsphere_hosts")
        tables = _list_user_tables(connection)
        if hosts_t not in tables:
            return []
        _ensure_hosts_hardware_columns(connection, hosts_t)
        rows = connection.execute(
            f"""
            SELECT idx, host_id, host_name, connection_state, power_state, cluster_id,
                   cpu_count, memory_mib
            FROM {_quote_ident(hosts_t)}
            ORDER BY {ci_order_clause(connection, "host_name")}, idx ASC
            """
        ).fetchall()
    return [
        ShapeVsphereHostListItem(
            idx=int(row["idx"]),
            host_id=str(row["host_id"] or ""),
            host_name=str(row["host_name"]) if row["host_name"] else None,
            connection_state=(
                str(row["connection_state"]) if row["connection_state"] else None
            ),
            power_state=str(row["power_state"]) if row["power_state"] else None,
            cluster_id=str(row["cluster_id"]) if row["cluster_id"] else None,
            cpu_count=_as_optional_int(row["cpu_count"]),
            memory_mib=_as_optional_int(row["memory_mib"]),
        )
        for row in rows
    ]


def get_shape_vsphere_host_detail(
    database_path: str | Path,
    cluster_name: str,
    host_idx: int,
) -> ShapeVsphereHostDetail | None:
    name = validate_cluster_name(cluster_name)
    with get_connection(database_path) as connection:
        infra_type = _lookup_shapeable_infra_type(connection, name)
        if infra_type != INFRA_TYPE_VSPHERE:
            return None
        from backend.app.db.vsphere_inventory import vsphere_inventory_table

        hosts_t = vsphere_inventory_table(name, "vsphere_hosts")
        vms_t = vsphere_inventory_table(name, "vsphere_vms_on_host")
        tables = _list_user_tables(connection)
        if hosts_t not in tables:
            return None
        row = connection.execute(
            f"""
            SELECT * FROM {_quote_ident(hosts_t)} WHERE idx = ?
            """,
            (int(host_idx),),
        ).fetchone()
        if row is None:
            return None
        host = _row_to_dict(row)
        host_id = str(host.get("host_id") or "")
        vms: list[dict[str, Any]] = []
        if host_id and vms_t in tables:
            vm_rows = connection.execute(
                f"""
                SELECT *
                FROM {_quote_ident(vms_t)}
                WHERE host_id = ?
                ORDER BY {ci_order_clause(connection, "vm_name")}, idx ASC
                """,
                (host_id,),
            ).fetchall()
            vms = [_row_to_dict(item) for item in vm_rows]
    return ShapeVsphereHostDetail(host=host, vms=vms)
