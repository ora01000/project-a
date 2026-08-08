"""Read inventory rows for infra shape detail panel (k8s / kubevirt)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.db.introspection import ci_order_clause
from backend.app.db.k8s_inventory import (
    DEFAULT_INFRA_TYPE,
    KNOWN_INFRA_TYPES,
    _list_user_tables,
    _quote_ident,
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


@dataclass
class ShapeNodeListItem:
    idx: int
    node_name: str
    node_cpu: int | None = None
    node_mem: int | None = None
    node_os: str | None = None
    node_k8s_ver: str | None = None


@dataclass
class ShapeVmListItem:
    idx: int
    name: str
    namespace: str | None = None
    printable_status: str | None = None
    ready: bool | None = None
    node_name: str | None = None


@dataclass
class ShapeNamespaceDetail:
    namespace: dict[str, Any]
    deployments: list[dict[str, Any]] = field(default_factory=list)
    pvcs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ShapeVmDetail:
    vm: dict[str, Any]
    volumes: list[dict[str, Any]] = field(default_factory=list)


def _lookup_infra_type(connection, cluster_name: str) -> str | None:
    row = connection.execute(
        """
        SELECT infra_type FROM infra_cluster WHERE cluster_name = ?
        """,
        (cluster_name,),
    ).fetchone()
    if row is None:
        return None
    infra_type = str(row["infra_type"] or DEFAULT_INFRA_TYPE).strip() or DEFAULT_INFRA_TYPE
    if infra_type not in KNOWN_INFRA_TYPES:
        return None
    return infra_type


def _inventory_core_tables(
    cluster_name: str,
    infra_type: str,
) -> tuple[str, str, str, str]:
    if infra_type == "kubevirt":
        from backend.app.db.kubevirt_inventory import kubevirt_inventory_tables

        nodes_t, ns_t, dep_t, pvc_t, _, _ = kubevirt_inventory_tables(cluster_name)
        return nodes_t, ns_t, dep_t, pvc_t
    return cluster_inventory_tables(cluster_name)


def _kubevirt_vm_tables(cluster_name: str) -> tuple[str, str, str]:
    from backend.app.db.kubevirt_inventory import kubevirt_inventory_tables

    _, ns_t, _, _, vms_t, vol_t = kubevirt_inventory_tables(cluster_name)
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
        rows = connection.execute(
            f"""
            SELECT idx, namespace, okd_display_name
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
        rows = connection.execute(
            f"""
            SELECT idx, node_name, node_cpu, node_mem, node_os, node_k8s_ver
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
        )
        for row in rows
    ]


def get_shape_node_detail(
    database_path: str | Path,
    cluster_name: str,
    node_idx: int,
) -> dict[str, Any] | None:
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
        return _row_to_dict(row)


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
                    v.printable_status AS printable_status,
                    v.ready AS ready,
                    v.node_name AS node_name
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
                    printable_status,
                    ready,
                    node_name
                FROM {_quote_ident(vms_t)}
                ORDER BY {ci_order_clause(connection, "name")}, idx ASC
                """
            ).fetchall()
    return [
        ShapeVmListItem(
            idx=int(row["idx"]),
            name=str(row["name"] or ""),
            namespace=str(row["namespace"]) if row["namespace"] else None,
            printable_status=(
                str(row["printable_status"]) if row["printable_status"] else None
            ),
            ready=bool(row["ready"]) if row["ready"] is not None else None,
            node_name=str(row["node_name"]) if row["node_name"] else None,
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
