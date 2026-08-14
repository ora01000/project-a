"""Cluster CPU/MEM capacity aggregation for the infra shape tab."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.k8s_inventory import (
    DEFAULT_INFRA_TYPE,
    INFRA_TYPE_VSPHERE,
    SHAPEABLE_INFRA_TYPES,
    _list_user_tables,
    _quote_ident,
    cluster_inventory_tables,
    validate_cluster_name,
)

_WORKER_ROLE_FILTER = "LOWER(COALESCE(node_role, '')) LIKE '%worker%'"
_ACTIVE_REPLICA_FILTER = "COALESCE(replicas, 0) > 0"
_RUNNING_VM_FILTER = "LOWER(COALESCE(printable_status, '')) = 'running'"
_VSPHERE_POWERED_ON_FILTER = (
    "UPPER(REPLACE(COALESCE(power_state, ''), '-', '_')) IN ('POWERED_ON', 'POWER_ON')"
)


@dataclass
class ResourceCapacity:
    capacity: float = 0.0
    request: float = 0.0
    limit: float = 0.0


@dataclass
class NodeShapeCapacity:
    node_name: str
    cpu: ResourceCapacity
    mem: ResourceCapacity


@dataclass
class PvcShapeCapacity:
    name: str
    capacity: int | None = None
    used: int | None = None
    namespace: str = ""
    deployment_name: str = ""
    storage_class: str = ""
    access_mode: str = ""


@dataclass
class ClusterShapeCapacity:
    cluster_name: str
    infra_type: str
    supported: bool
    node_count: int = 0
    include_all_nodes: bool = False
    cpu: ResourceCapacity | None = None
    mem: ResourceCapacity | None = None
    nodes: list[NodeShapeCapacity] = field(default_factory=list)
    storages: list[PvcShapeCapacity] = field(default_factory=list)


def _row_float(row, key: str) -> float:
    if row is None:
        return 0.0
    raw = row[key] if hasattr(row, "keys") else None
    if raw is None:
        return 0.0
    return float(raw)


def _row_int(row, key: str) -> int:
    return int(_row_float(row, key))


def _row_optional_int(row, key: str) -> int | None:
    if row is None:
        return None
    raw = row[key] if hasattr(row, "keys") else None
    if raw is None:
        return None
    return int(float(raw))


def _row_text(row, key: str) -> str:
    if row is None:
        return ""
    raw = row[key] if hasattr(row, "keys") else None
    if raw is None:
        return ""
    return str(raw).strip()


def _mib_to_gi(memory_mib: float) -> float:
    return memory_mib / 1024.0


def _vsphere_shape_capacity(connection, cluster_name: str, tables: set[str]) -> ClusterShapeCapacity:
    from backend.app.db.vsphere_inventory import vsphere_inventory_tables

    _clusters_t, hosts_t, vms_t, _ds_t = vsphere_inventory_tables(cluster_name)
    node_count = 0
    cpu_cap = 0.0
    mem_cap_mib = 0.0
    if hosts_t in tables:
        count_row = connection.execute(
            f"SELECT COUNT(*) AS cnt FROM {_quote_ident(hosts_t)}"
        ).fetchone()
        node_count = _row_int(count_row, "cnt")
        cpu_cap, mem_cap_mib = _sum_pair(connection, hosts_t, "cpu_count", "memory_mib")

    cpu_used = 0.0
    mem_used_mib = 0.0
    if vms_t in tables:
        cpu_used, mem_used_mib = _sum_pair(
            connection,
            vms_t,
            "cpu_count",
            "memory_mib",
            where=_VSPHERE_POWERED_ON_FILTER,
        )

    mem_cap = _mib_to_gi(mem_cap_mib)
    mem_used = _mib_to_gi(mem_used_mib)
    return ClusterShapeCapacity(
        cluster_name=cluster_name,
        infra_type=INFRA_TYPE_VSPHERE,
        supported=True,
        node_count=node_count,
        include_all_nodes=True,
        cpu=ResourceCapacity(capacity=cpu_cap, request=cpu_used, limit=cpu_used),
        mem=ResourceCapacity(capacity=mem_cap, request=mem_used, limit=mem_used),
        nodes=_vsphere_host_shape_capacities(connection, hosts_t, vms_t, tables),
        storages=_vsphere_datastore_shape_capacities(connection, _ds_t, tables),
    )


def _vsphere_datastore_shape_capacities(
    connection,
    ds_t: str,
    tables: set[str],
) -> list[PvcShapeCapacity]:
    if ds_t not in tables:
        return []
    sql = f"""
        SELECT COALESCE(NULLIF(name, ''), datastore_id) AS name,
               capacity_bytes AS capacity,
               free_bytes AS used,
               COALESCE(datacenter_name, '') AS namespace,
               COALESCE(type, '') AS storage_class,
               COALESCE(CAST(accessible AS TEXT), '') AS access_mode
        FROM {_quote_ident(ds_t)}
        ORDER BY name
        """
    rows: list[PvcShapeCapacity] = []
    for row in connection.execute(sql).fetchall():
        name = _row_text(row, "name")
        if not name:
            continue
        rows.append(
            PvcShapeCapacity(
                name=name,
                capacity=_row_optional_int(row, "capacity"),
                used=_row_optional_int(row, "used"),
                namespace=_row_text(row, "namespace"),
                storage_class=_row_text(row, "storage_class"),
                access_mode=_row_text(row, "access_mode"),
            )
        )
    return rows


def _vsphere_host_shape_capacities(
    connection,
    hosts_t: str,
    vms_t: str,
    tables: set[str],
) -> list[NodeShapeCapacity]:
    if hosts_t not in tables:
        return []
    if vms_t in tables:
        sql = f"""
            SELECT COALESCE(NULLIF(h.host_name, ''), h.host_id) AS node_name,
                   COALESCE(h.cpu_count, 0) AS cpu_cap,
                   COALESCE(h.memory_mib, 0) AS mem_cap,
                   COALESCE(SUM(v.cpu_count), 0) AS cpu_req,
                   COALESCE(SUM(v.memory_mib), 0) AS mem_req
            FROM {_quote_ident(hosts_t)} h
            LEFT JOIN {_quote_ident(vms_t)} v
              ON v.host_id = h.host_id
             AND {_VSPHERE_POWERED_ON_FILTER.replace("power_state", "v.power_state")}
            GROUP BY h.host_id, h.host_name, h.cpu_count, h.memory_mib
            ORDER BY node_name
            """
    else:
        sql = f"""
            SELECT COALESCE(NULLIF(h.host_name, ''), h.host_id) AS node_name,
                   COALESCE(h.cpu_count, 0) AS cpu_cap,
                   COALESCE(h.memory_mib, 0) AS mem_cap,
                   0 AS cpu_req,
                   0 AS mem_req
            FROM {_quote_ident(hosts_t)} h
            ORDER BY node_name
            """
    rows: list[NodeShapeCapacity] = []
    for row in connection.execute(sql).fetchall():
        name = str(row["node_name"] or "").strip()
        if not name:
            continue
        cpu_req = _row_float(row, "cpu_req")
        mem_req = _row_float(row, "mem_req")
        rows.append(
            NodeShapeCapacity(
                node_name=name,
                cpu=ResourceCapacity(
                    capacity=_row_float(row, "cpu_cap"),
                    request=cpu_req,
                    limit=cpu_req,
                ),
                mem=ResourceCapacity(
                    capacity=_row_float(row, "mem_cap"),
                    request=mem_req,
                    limit=mem_req,
                ),
            )
        )
    return rows


def _k8s_node_shape_capacities(
    connection,
    nodes_t: str,
    pods_t: str | None,
    tables: set[str],
    *,
    include_all_nodes: bool,
    vms_t: str | None = None,
) -> list[NodeShapeCapacity]:
    if nodes_t not in tables:
        return []
    node_where = "" if include_all_nodes else (
        "WHERE LOWER(COALESCE(n.node_role, '')) LIKE '%worker%'"
    )
    if pods_t and pods_t in tables:
        sql = f"""
            SELECT n.node_name AS node_name,
                   COALESCE(n.node_cpu, 0) AS cpu_cap,
                   COALESCE(n.node_mem, 0) AS mem_cap,
                   COALESCE(SUM(p.cpu_request), 0) AS cpu_req,
                   COALESCE(SUM(p.mem_request), 0) AS mem_req,
                   COALESCE(SUM(p.cpu_limit), 0) AS cpu_lim,
                   COALESCE(SUM(p.mem_limit), 0) AS mem_lim
            FROM {_quote_ident(nodes_t)} n
            LEFT JOIN {_quote_ident(pods_t)} p ON p.node_name = n.node_name
            {node_where}
            GROUP BY n.node_name, n.node_cpu, n.node_mem
            ORDER BY n.node_name
            """
    else:
        sql = f"""
            SELECT n.node_name AS node_name,
                   COALESCE(n.node_cpu, 0) AS cpu_cap,
                   COALESCE(n.node_mem, 0) AS mem_cap,
                   0 AS cpu_req,
                   0 AS mem_req,
                   0 AS cpu_lim,
                   0 AS mem_lim
            FROM {_quote_ident(nodes_t)} n
            {node_where}
            ORDER BY n.node_name
            """
    vm_cpu_by_node: dict[str, float] = {}
    vm_mem_by_node: dict[str, float] = {}
    if vms_t and vms_t in tables:
        for vm_row in connection.execute(
            f"""
            SELECT node_name AS node_name,
                   COALESCE(SUM(cpu_cores), 0) AS cpu_sum,
                   COALESCE(SUM(memory_gi), 0) AS mem_sum
            FROM {_quote_ident(vms_t)}
            WHERE COALESCE(node_name, '') <> ''
            GROUP BY node_name
            """
        ).fetchall():
            vm_name = str(vm_row["node_name"] or "").strip()
            if not vm_name:
                continue
            vm_cpu_by_node[vm_name] = _row_float(vm_row, "cpu_sum")
            vm_mem_by_node[vm_name] = _row_float(vm_row, "mem_sum")
    rows: list[NodeShapeCapacity] = []
    for row in connection.execute(sql).fetchall():
        name = str(row["node_name"] or "").strip()
        if not name:
            continue
        rows.append(
            NodeShapeCapacity(
                node_name=name,
                cpu=ResourceCapacity(
                    capacity=_row_float(row, "cpu_cap"),
                    request=_row_float(row, "cpu_req") + vm_cpu_by_node.get(name, 0.0),
                    limit=_row_float(row, "cpu_lim"),
                ),
                mem=ResourceCapacity(
                    capacity=_row_float(row, "mem_cap"),
                    request=_row_float(row, "mem_req") + vm_mem_by_node.get(name, 0.0),
                    limit=_row_float(row, "mem_lim"),
                ),
            )
        )
    return rows


def _k8s_pvc_shape_capacities(
    connection,
    pvc_t: str,
    ns_t: str,
    dep_t: str,
    tables: set[str],
) -> list[PvcShapeCapacity]:
    if pvc_t not in tables or ns_t not in tables:
        return []
    if dep_t in tables:
        sql = f"""
            SELECT p.name AS name,
                   p.capacity AS capacity,
                   p.used AS used,
                   COALESCE(n.namespace, '') AS namespace,
                   COALESCE(d.name, '') AS deployment_name,
                   COALESCE(p.storage_class, '') AS storage_class,
                   COALESCE(p.access_mode, '') AS access_mode
            FROM {_quote_ident(pvc_t)} p
            JOIN {_quote_ident(ns_t)} n ON n.idx = p.namespace_id
            LEFT JOIN {_quote_ident(dep_t)} d ON d.idx = p.deployment_id
            ORDER BY n.namespace, p.name
            """
    else:
        sql = f"""
            SELECT p.name AS name,
                   p.capacity AS capacity,
                   p.used AS used,
                   COALESCE(n.namespace, '') AS namespace,
                   '' AS deployment_name,
                   COALESCE(p.storage_class, '') AS storage_class,
                   COALESCE(p.access_mode, '') AS access_mode
            FROM {_quote_ident(pvc_t)} p
            JOIN {_quote_ident(ns_t)} n ON n.idx = p.namespace_id
            ORDER BY n.namespace, p.name
            """
    rows: list[PvcShapeCapacity] = []
    for row in connection.execute(sql).fetchall():
        name = _row_text(row, "name")
        if not name:
            continue
        rows.append(
            PvcShapeCapacity(
                name=name,
                capacity=_row_optional_int(row, "capacity"),
                used=_row_optional_int(row, "used"),
                namespace=_row_text(row, "namespace"),
                deployment_name=_row_text(row, "deployment_name"),
                storage_class=_row_text(row, "storage_class"),
                access_mode=_row_text(row, "access_mode"),
            )
        )
    return rows


def _sum_pair(connection, table_name: str, cpu_col: str, mem_col: str, *, where: str = "") -> tuple[float, float]:
    clause = f" WHERE {where}" if where else ""
    row = connection.execute(
        f"""
        SELECT COALESCE(SUM({cpu_col}), 0) AS cpu_sum,
               COALESCE(SUM({mem_col}), 0) AS mem_sum
        FROM {_quote_ident(table_name)}{clause}
        """
    ).fetchone()
    return _row_float(row, "cpu_sum"), _row_float(row, "mem_sum")


def get_cluster_shape_capacity(
    database_path: str | Path,
    cluster_name: str,
    *,
    include_all_nodes: bool = False,
) -> ClusterShapeCapacity | None:
    name = validate_cluster_name(cluster_name)

    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT cluster_name, infra_type
            FROM infra_cluster
            WHERE cluster_name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            return None

        infra_type = str(row["infra_type"] or DEFAULT_INFRA_TYPE).strip() or DEFAULT_INFRA_TYPE
        if infra_type not in SHAPEABLE_INFRA_TYPES:
            return None

        tables = _list_user_tables(connection)
        if infra_type == INFRA_TYPE_VSPHERE:
            return _vsphere_shape_capacity(connection, name, tables)
        if infra_type == "kubevirt":
            from backend.app.db.kubevirt_inventory import kubevirt_inventory_tables

            nodes_t, ns_t, dep_t, pvc_t, vms_t, _, pods_t = kubevirt_inventory_tables(name)
        else:
            nodes_t, ns_t, dep_t, pvc_t, pods_t = cluster_inventory_tables(name)
            vms_t = None

        node_count = 0
        cpu_cap = 0.0
        mem_cap = 0.0
        node_where = "" if include_all_nodes else _WORKER_ROLE_FILTER
        if nodes_t in tables:
            count_sql = f"SELECT COUNT(*) AS cnt FROM {_quote_ident(nodes_t)}"
            if node_where:
                count_sql += f" WHERE {node_where}"
            count_row = connection.execute(count_sql).fetchone()
            node_count = _row_int(count_row, "cnt")
            cpu_cap, mem_cap = _sum_pair(
                connection,
                nodes_t,
                "node_cpu",
                "node_mem",
                where=node_where,
            )

        cpu_req = 0.0
        mem_req = 0.0
        cpu_lim = 0.0
        mem_lim = 0.0
        if dep_t in tables:
            cpu_req, mem_req = _sum_pair(
                connection,
                dep_t,
                "resource_cpu_request",
                "resource_mem_request",
                where=_ACTIVE_REPLICA_FILTER,
            )
            cpu_lim, mem_lim = _sum_pair(
                connection,
                dep_t,
                "resource_cpu_limit",
                "resource_mem_limit",
                where=_ACTIVE_REPLICA_FILTER,
            )

        if vms_t and vms_t in tables:
            vm_cpu, vm_mem = _sum_pair(
                connection,
                vms_t,
                "cpu_cores",
                "memory_gi",
                where=_RUNNING_VM_FILTER,
            )
            cpu_req += vm_cpu
            mem_req += vm_mem

        return ClusterShapeCapacity(
            cluster_name=name,
            infra_type=infra_type,
            supported=True,
            node_count=node_count,
            include_all_nodes=include_all_nodes,
            cpu=ResourceCapacity(capacity=cpu_cap, request=cpu_req, limit=cpu_lim),
            mem=ResourceCapacity(capacity=mem_cap, request=mem_req, limit=mem_lim),
            nodes=_k8s_node_shape_capacities(
                connection,
                nodes_t,
                pods_t,
                tables,
                include_all_nodes=include_all_nodes,
                vms_t=vms_t,
            ),
            storages=_k8s_pvc_shape_capacities(connection, pvc_t, ns_t, dep_t, tables),
        )
