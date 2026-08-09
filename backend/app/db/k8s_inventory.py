"""Persist Kubernetes inventory into per-cluster dynamic SQLite tables.

Layout:
  infra_cluster (shared registry; formerly k8s_cluster)
  {cluster_name}_k8s_nodes
  {cluster_name}_k8s_namespaces
  {cluster_name}_k8s_deployments
  {cluster_name}_k8s_pvcs

Backups before replace: {table}_{YYYYMMDD_HHMMSS}
Retention: keep the newest MAX_INVENTORY_BACKUP_GENERATIONS stamp sets per cluster.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.db.introspection import (
    ensure_table_idx_serial,
    list_table_columns,
    list_user_tables,
    pk_autoincrement_sql,
)
from backend.app.timezone import format_display_datetime, now_display_datetime

logger = logging.getLogger(__name__)

INVENTORY_SUFFIXES = (
    "k8s_nodes",
    "k8s_namespaces",
    "k8s_deployments",
    "k8s_pvcs",
    "k8s_pods_on_nodes",
)

# Keep this many timestamped backup generations per cluster (by YYYYMMDD_HHMMSS).
MAX_INVENTORY_BACKUP_GENERATIONS = 4

# Shared (pre-260806-fix) tables to drop on migrate.
LEGACY_SHARED_INVENTORY_TABLES = (
    "k8s_pods",
    "k8s_pvcs",
    "k8s_deployments",
    "k8s_namespaces",
    "k8s_nodes",
)

_BACKUP_STAMP_RE = re.compile(r"[^0-9]")
_BACKUP_STAMP_SUFFIX_RE = re.compile(r"^\d{8}_\d{6}$")
_CLUSTER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
_LEGACY_SHARED_BACKUP_RE = re.compile(
    r"^k8s_(?:pods|pvcs|deployments|namespaces|nodes)_\d{8}_\d{6}$"
)


@dataclass
class K8sNodeRow:
    node_name: str
    node_cpu: int | None = None
    node_mem: int | None = None
    node_os: str | None = None
    node_k8s_ver: str | None = None
    node_role: str | None = None


@dataclass
class K8sNamespaceRow:
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
class K8sDeploymentRow:
    namespace: str
    name: str
    type: str
    replicas: int | None = None
    readyreplicas: int | None = None
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
    """In-memory only — used to map PVCs to workloads. Not persisted."""

    namespace: str
    name: str
    deployment_name: str | None = None
    deployment_type: str | None = None
    scheduled_node_name: str | None = None


@dataclass
class K8sPodOnNodeRow:
    node_name: str
    namespace: str
    pod_name: str
    cpu_request: float | None = None
    cpu_limit: float | None = None
    mem_request: float | None = None
    mem_limit: float | None = None
    age: str | None = None


@dataclass
class K8sClusterSnapshot:
    cluster_name: str
    nodes: list[K8sNodeRow] = field(default_factory=list)
    namespaces: list[K8sNamespaceRow] = field(default_factory=list)
    deployments: list[K8sDeploymentRow] = field(default_factory=list)
    pvcs: list[K8sPvcRow] = field(default_factory=list)
    pods: list[K8sPodRow] = field(default_factory=list)
    pods_on_nodes: list[K8sPodOnNodeRow] = field(default_factory=list)


@dataclass
class K8sClusterRecord:
    idx: int
    cluster_name: str
    last_update: str | None = None
    cron: bool = False
    cron_expr: str = "0 23 * * 6"
    infra_type: str = "k8s"


DEFAULT_CRON_EXPR = "0 23 * * 6"  # every Saturday 23:00
DEFAULT_INFRA_TYPE = "k8s"
KNOWN_INFRA_TYPES = frozenset({"k8s", "kubevirt"})
_CRON_EXPR_MAX_LEN = 20
_INFRA_TYPE_MAX_LEN = 20
_INFRA_TYPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$")
MAX_SHAPE_HISTORY_POINTS = 5


@dataclass
class K8sShapeCounts:
    nodes: int = 0
    namespaces: int = 0
    deployments: int = 0
    pvcs: int = 0
    vms: int = 0
    volumes: int = 0


@dataclass
class K8sShapeHistoryPoint:
    label: str
    stamp: str | None
    is_latest: bool
    counts: K8sShapeCounts


@dataclass
class K8sClusterShapeAnalysis:
    cluster_name: str
    last_update: str | None
    cluster_version: str | None
    summary: K8sShapeCounts
    history: list[K8sShapeHistoryPoint] = field(default_factory=list)
    infra_type: str = DEFAULT_INFRA_TYPE


def _table_row_count(connection, table_name: str, tables: set[str]) -> int:
    if table_name not in tables:
        return 0
    row = connection.execute(
        f"SELECT COUNT(*) AS cnt FROM {_quote_ident(table_name)}"
    ).fetchone()
    if row is None:
        return 0
    return int(row["cnt"] if hasattr(row, "keys") else row[0])


def _counts_for_suffix_tables(
    connection,
    *,
    cluster_name: str,
    stamp: str | None,
    tables: set[str],
) -> K8sShapeCounts:
    nodes_t, ns_t, dep_t, pvc_t, _pods_on_nodes_t = cluster_inventory_tables(cluster_name)
    if stamp:
        nodes_t = f"{nodes_t}_{stamp}"
        ns_t = f"{ns_t}_{stamp}"
        dep_t = f"{dep_t}_{stamp}"
        pvc_t = f"{pvc_t}_{stamp}"
    return K8sShapeCounts(
        nodes=_table_row_count(connection, nodes_t, tables),
        namespaces=_table_row_count(connection, ns_t, tables),
        deployments=_table_row_count(connection, dep_t, tables),
        pvcs=_table_row_count(connection, pvc_t, tables),
    )


def _counts_for_kubevirt_tables(
    connection,
    *,
    cluster_name: str,
    stamp: str | None,
    tables: set[str],
) -> K8sShapeCounts:
    from backend.app.db.kubevirt_inventory import kubevirt_inventory_tables

    nodes_t, ns_t, dep_t, pvc_t, vms_t, vol_t, _pods_on_nodes_t = kubevirt_inventory_tables(
        cluster_name
    )
    if stamp:
        nodes_t = f"{nodes_t}_{stamp}"
        ns_t = f"{ns_t}_{stamp}"
        dep_t = f"{dep_t}_{stamp}"
        pvc_t = f"{pvc_t}_{stamp}"
        vms_t = f"{vms_t}_{stamp}"
        vol_t = f"{vol_t}_{stamp}"
    return K8sShapeCounts(
        nodes=_table_row_count(connection, nodes_t, tables),
        namespaces=_table_row_count(connection, ns_t, tables),
        deployments=_table_row_count(connection, dep_t, tables),
        pvcs=_table_row_count(connection, pvc_t, tables),
        vms=_table_row_count(connection, vms_t, tables),
        volumes=_table_row_count(connection, vol_t, tables),
    )


def _cluster_version_from_nodes(
    connection,
    nodes_table: str,
    tables: set[str],
) -> str | None:
    if nodes_table not in tables:
        return None
    row = connection.execute(
        f"""
        SELECT node_k8s_ver AS ver, COUNT(*) AS cnt
        FROM {_quote_ident(nodes_table)}
        WHERE node_k8s_ver IS NOT NULL AND TRIM(node_k8s_ver) != ''
        GROUP BY node_k8s_ver
        ORDER BY cnt DESC, ver ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    ver = row["ver"] if hasattr(row, "keys") else row[0]
    text = str(ver or "").strip()
    return text[:50] if text else None


def _format_stamp_label(stamp: str) -> str:
    if _BACKUP_STAMP_SUFFIX_RE.fullmatch(stamp):
        return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"
    return stamp


def get_cluster_shape_analysis(
    database_path: str | Path,
    cluster_name: str,
    *,
    max_points: int = MAX_SHAPE_HISTORY_POINTS,
) -> K8sClusterShapeAnalysis | None:
    """Build live summary + up to ``max_points`` history snapshots (oldest→newest)."""
    name = validate_cluster_name(cluster_name)
    keep = max(1, int(max_points))

    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, cluster_name, last_update, cron, cron_expr, infra_type
            FROM infra_cluster
            WHERE cluster_name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            return None
        infra_type = str(row["infra_type"] or DEFAULT_INFRA_TYPE).strip() or DEFAULT_INFRA_TYPE
        if infra_type not in KNOWN_INFRA_TYPES:
            return None

        tables = _list_user_tables(connection)
        is_kubevirt = infra_type == "kubevirt"
        if is_kubevirt:
            from backend.app.db.kubevirt_inventory import (
                kubevirt_inventory_tables,
                list_kubevirt_inventory_backup_stamps,
            )

            nodes_t, _, _, _, _, _, _ = kubevirt_inventory_tables(name)
            count_fn = _counts_for_kubevirt_tables
            stamps = list_kubevirt_inventory_backup_stamps(connection, name)
        else:
            nodes_t, _, _, _, _ = cluster_inventory_tables(name)
            count_fn = _counts_for_suffix_tables
            stamps = list_cluster_inventory_backup_stamps(connection, name)

        summary = count_fn(
            connection, cluster_name=name, stamp=None, tables=tables
        )
        version = _cluster_version_from_nodes(connection, nodes_t, tables)
        last_update = str(row["last_update"]) if row["last_update"] else None

        # Newest backups first; keep room for live "latest" point.
        backup_limit = max(0, keep - 1)
        selected_stamps = stamps[:backup_limit]

        history: list[K8sShapeHistoryPoint] = []
        # Chronological: oldest backup → newest backup → latest
        for stamp in reversed(selected_stamps):
            history.append(
                K8sShapeHistoryPoint(
                    label=_format_stamp_label(stamp),
                    stamp=stamp,
                    is_latest=False,
                    counts=count_fn(
                        connection, cluster_name=name, stamp=stamp, tables=tables
                    ),
                )
            )
        history.append(
            K8sShapeHistoryPoint(
                label="latest" if not last_update else last_update,
                stamp=None,
                is_latest=True,
                counts=summary,
            )
        )

    return K8sClusterShapeAnalysis(
        cluster_name=name,
        last_update=last_update,
        cluster_version=version,
        summary=summary,
        history=history,
        infra_type=infra_type,
    )


def validate_cluster_name(cluster_name: str) -> str:
    name = (cluster_name or "").strip()
    if not name:
        raise ValueError("cluster_name은 필수입니다.")
    if len(name) > 50:
        raise ValueError("cluster_name은 50자를 초과할 수 없습니다.")
    if not _CLUSTER_NAME_RE.match(name):
        raise ValueError(
            "cluster_name은 영문/숫자/._- 만 사용할 수 있으며 테이블명으로 안전해야 합니다."
        )
    return name


def validate_cron_expr(cron_expr: str | None) -> str:
    """Validate a 5-field cron expression (max 20 chars). Empty -> default."""
    text = (cron_expr or "").strip() or DEFAULT_CRON_EXPR
    if len(text) > _CRON_EXPR_MAX_LEN:
        raise ValueError(
            f"cron_expr은 {_CRON_EXPR_MAX_LEN}자를 초과할 수 없습니다."
        )
    try:
        from croniter import croniter

        if not croniter.is_valid(text):
            raise ValueError(f"잘못된 cron 표현식입니다: {text}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"잘못된 cron 표현식입니다: {text}") from exc
    return text


def validate_infra_type(infra_type: str | None) -> str:
    text = (infra_type or "").strip() or DEFAULT_INFRA_TYPE
    if len(text) > _INFRA_TYPE_MAX_LEN:
        raise ValueError(
            f"infra_type은 {_INFRA_TYPE_MAX_LEN}자를 초과할 수 없습니다."
        )
    if not _INFRA_TYPE_RE.match(text):
        raise ValueError(
            "infra_type은 영문/숫자/._- 만 사용할 수 있습니다."
        )
    if text not in KNOWN_INFRA_TYPES:
        allowed = ", ".join(sorted(KNOWN_INFRA_TYPES))
        raise ValueError(f"지원하지 않는 infra_type 입니다: {text} (허용: {allowed})")
    return text


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n", ""}:
        return False
    return default


def _cluster_record_from_row(row: Any) -> K8sClusterRecord:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    cron_raw = row["cron"] if "cron" in keys else 0
    cron_expr_raw = row["cron_expr"] if "cron_expr" in keys else DEFAULT_CRON_EXPR
    infra_type_raw = row["infra_type"] if "infra_type" in keys else DEFAULT_INFRA_TYPE
    return K8sClusterRecord(
        idx=int(row["idx"]),
        cluster_name=str(row["cluster_name"]),
        last_update=str(row["last_update"]) if row["last_update"] else None,
        cron=_as_bool(cron_raw, default=False),
        cron_expr=str(cron_expr_raw or DEFAULT_CRON_EXPR)[:_CRON_EXPR_MAX_LEN],
        infra_type=str(infra_type_raw or DEFAULT_INFRA_TYPE)[:_INFRA_TYPE_MAX_LEN]
        or DEFAULT_INFRA_TYPE,
    )


def cluster_inventory_table(cluster_name: str, suffix: str) -> str:
    name = validate_cluster_name(cluster_name)
    if suffix not in INVENTORY_SUFFIXES:
        raise ValueError(f"unknown inventory suffix: {suffix}")
    return f"{name}_{suffix}"


def cluster_inventory_tables(
    cluster_name: str,
) -> tuple[str, str, str, str, str]:
    return (
        cluster_inventory_table(cluster_name, "k8s_nodes"),
        cluster_inventory_table(cluster_name, "k8s_namespaces"),
        cluster_inventory_table(cluster_name, "k8s_deployments"),
        cluster_inventory_table(cluster_name, "k8s_pvcs"),
        cluster_inventory_table(cluster_name, "k8s_pods_on_nodes"),
    )


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


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


def format_backup_stamp(last_update: str | None) -> str:
    """Build YYYYMMDD_HHMMSS from last_update, or now if empty."""
    raw = (last_update or "").strip()
    digits = _BACKUP_STAMP_RE.sub("", raw)
    if len(digits) >= 14:
        return f"{digits[:8]}_{digits[8:14]}"
    now = now_display_datetime()
    return now.strftime("%Y%m%d_%H%M%S")


def _list_user_tables(connection) -> set[str]:
    return list_user_tables(connection)


def drop_legacy_shared_inventory_tables(connection) -> list[str]:
    """Drop shared k8s_* inventory tables and their YYYYMMDD_HHMMSS backups."""
    dropped: list[str] = []
    tables = _list_user_tables(connection)
    for table_name in LEGACY_SHARED_INVENTORY_TABLES:
        if table_name in tables:
            connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
            dropped.append(table_name)
    for table_name in sorted(tables):
        if _LEGACY_SHARED_BACKUP_RE.match(table_name):
            connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
            dropped.append(table_name)
    if dropped:
        logger.info("Dropped legacy shared k8s inventory tables: %s", dropped)
    return dropped


def _ensure_namespace_egress_columns(connection, namespace_table: str) -> None:
    """Add using_egressip / egressip_assigned_node to existing namespace tables."""
    columns = list_table_columns(connection, namespace_table)
    if "using_egressip" not in columns:
        connection.execute(
            f"ALTER TABLE {_quote_ident(namespace_table)} "
            "ADD COLUMN using_egressip VARCHAR(20)"
        )
        logger.info("Added %s.using_egressip", namespace_table)
    if "egressip_assigned_node" not in columns:
        connection.execute(
            f"ALTER TABLE {_quote_ident(namespace_table)} "
            "ADD COLUMN egressip_assigned_node VARCHAR(50)"
        )
        logger.info("Added %s.egressip_assigned_node", namespace_table)


def _drop_namespace_readyreplicas_column(connection, namespace_table: str) -> None:
    """Remove mistakenly added readyreplicas from namespace inventory tables."""
    columns = list_table_columns(connection, namespace_table)
    if "readyreplicas" not in columns:
        return
    try:
        connection.execute(
            f"ALTER TABLE {_quote_ident(namespace_table)} DROP COLUMN readyreplicas"
        )
        logger.info("Dropped %s.readyreplicas", namespace_table)
    except Exception as exc:
        logger.warning(
            "Could not drop %s.readyreplicas (%s)", namespace_table, exc
        )


def _ensure_deployment_readyreplicas_column(connection, deployment_table: str) -> None:
    """Add readyreplicas to existing deployment inventory tables."""
    columns = list_table_columns(connection, deployment_table)
    if "readyreplicas" not in columns:
        connection.execute(
            f"ALTER TABLE {_quote_ident(deployment_table)} "
            "ADD COLUMN readyreplicas INTEGER"
        )
        logger.info("Added %s.readyreplicas", deployment_table)


def _ensure_node_role_column(connection, nodes_table: str) -> None:
    """Add node_role to existing node inventory tables."""
    columns = list_table_columns(connection, nodes_table)
    if "node_role" not in columns:
        connection.execute(
            f"ALTER TABLE {_quote_ident(nodes_table)} "
            "ADD COLUMN node_role VARCHAR(30)"
        )
        logger.info("Added %s.node_role", nodes_table)


def ensure_cluster_inventory_tables(
    connection, cluster_name: str
) -> tuple[str, str, str, str, str]:
    """Create per-cluster inventory tables if missing. Returns table names."""
    nodes_t, ns_t, dep_t, pvc_t, pods_on_nodes_t = cluster_inventory_tables(cluster_name)
    tables = _list_user_tables(connection)

    if nodes_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(nodes_t)} (
                {pk_autoincrement_sql(connection)},
                node_name VARCHAR(50) NOT NULL,
                node_cpu INTEGER,
                node_mem INTEGER,
                node_os VARCHAR(50),
                node_k8s_ver VARCHAR(50),
                node_role VARCHAR(30)
            )
            """
        )
    else:
        _ensure_node_role_column(connection, nodes_t)
    if ns_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(ns_t)} (
                {pk_autoincrement_sql(connection)},
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
    else:
        _ensure_namespace_egress_columns(connection, ns_t)
        _drop_namespace_readyreplicas_column(connection, ns_t)
    if dep_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(dep_t)} (
                {pk_autoincrement_sql(connection)},
                namespace_id INTEGER NOT NULL,
                name VARCHAR(50) NOT NULL,
                type VARCHAR(20) NOT NULL,
                replicas INTEGER,
                readyreplicas INTEGER,
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
    else:
        _ensure_deployment_readyreplicas_column(connection, dep_t)
    if pvc_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(pvc_t)} (
                {pk_autoincrement_sql(connection)},
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
    if pods_on_nodes_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(pods_on_nodes_t)} (
                {pk_autoincrement_sql(connection)},
                node_name VARCHAR(50) NOT NULL,
                namespace VARCHAR(50) NOT NULL,
                pod_name VARCHAR(50) NOT NULL,
                cpu_request REAL,
                cpu_limit REAL,
                mem_request REAL,
                mem_limit REAL,
                age VARCHAR(20)
            )
            """
        )
    for table_name in (nodes_t, ns_t, dep_t, pvc_t, pods_on_nodes_t):
        ensure_table_idx_serial(connection, table_name)
    return nodes_t, ns_t, dep_t, pvc_t, pods_on_nodes_t


def backup_cluster_inventory_tables(
    connection,
    cluster_name: str,
    *,
    stamp: str,
) -> list[str]:
    """Copy existing per-cluster tables to {table}_{YYYYMMDD_HHMMSS}."""
    created: list[str] = []
    safe_stamp = re.sub(r"[^0-9_]", "", stamp) or format_backup_stamp(None)
    tables = _list_user_tables(connection)
    for table_name in cluster_inventory_tables(cluster_name):
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
        logger.info("Backed up cluster=%s inventory -> %s", cluster_name, created)
    return created


def _backup_stamp_from_table(live_table: str, table_name: str) -> str | None:
    """Return YYYYMMDD_HHMMSS if table_name is a backup of live_table."""
    prefix = f"{live_table}_"
    if not table_name.startswith(prefix):
        return None
    stamp = table_name[len(prefix) :]
    if _BACKUP_STAMP_SUFFIX_RE.fullmatch(stamp):
        return stamp
    return None


def list_cluster_inventory_backup_stamps(connection, cluster_name: str) -> list[str]:
    """Unique backup stamps for a cluster, newest first (YYYYMMDD_HHMMSS)."""
    stamps: set[str] = set()
    tables = _list_user_tables(connection)
    for live_table in cluster_inventory_tables(cluster_name):
        for table_name in tables:
            stamp = _backup_stamp_from_table(live_table, table_name)
            if stamp:
                stamps.add(stamp)
    return sorted(stamps, reverse=True)


def prune_cluster_inventory_backups(
    connection,
    cluster_name: str,
    *,
    keep: int = MAX_INVENTORY_BACKUP_GENERATIONS,
) -> list[str]:
    """Drop backup table generations older than the newest ``keep`` stamps."""
    keep_n = max(0, int(keep))
    stamps = list_cluster_inventory_backup_stamps(connection, cluster_name)
    stale_stamps = set(stamps[keep_n:])
    if not stale_stamps:
        return []

    dropped: list[str] = []
    tables = _list_user_tables(connection)
    for live_table in cluster_inventory_tables(cluster_name):
        for table_name in sorted(tables):
            stamp = _backup_stamp_from_table(live_table, table_name)
            if stamp is None or stamp not in stale_stamps:
                continue
            connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
            dropped.append(table_name)
            tables.discard(table_name)

    if dropped:
        logger.info(
            "Pruned cluster=%s inventory backups keep=%s dropped=%s",
            cluster_name,
            keep_n,
            dropped,
        )
    return dropped


def drop_cluster_inventory_tables(connection, cluster_name: str) -> list[str]:
    """Drop per-cluster inventory tables (k8s + kubevirt) and timestamped backups."""
    from backend.app.db.kubevirt_inventory import KUBEVIRT_INVENTORY_SUFFIXES

    dropped: list[str] = []
    try:
        name = validate_cluster_name(cluster_name)
        prefixes = [
            f"{name}_{suffix}"
            for suffix in (*INVENTORY_SUFFIXES, *KUBEVIRT_INVENTORY_SUFFIXES)
        ]
    except ValueError:
        return dropped

    tables = _list_user_tables(connection)
    # Drop backups first, then live tables (pvcs/deps before namespaces for FK safety).
    for table_name in sorted(tables, reverse=True):
        for prefix in prefixes:
            if table_name == prefix or table_name.startswith(f"{prefix}_"):
                connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
                dropped.append(table_name)
                break
    if dropped:
        logger.info("Dropped cluster=%s inventory tables: %s", cluster_name, dropped)
    return dropped


def rename_cluster_inventory_tables(
    connection,
    old_name: str,
    new_name: str,
) -> list[tuple[str, str]]:
    """Rename live per-cluster tables when cluster_name changes."""
    from backend.app.db.kubevirt_inventory import KUBEVIRT_INVENTORY_SUFFIXES

    if old_name == new_name:
        return []
    renamed: list[tuple[str, str]] = []
    tables = _list_user_tables(connection)
    for suffix in (*INVENTORY_SUFFIXES, *KUBEVIRT_INVENTORY_SUFFIXES):
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
    if renamed:
        logger.info("Renamed inventory tables %s -> %s: %s", old_name, new_name, renamed)
    return renamed


def list_infra_clusters(
    database_path: str | Path,
    *,
    infra_types: tuple[str, ...] | None = None,
) -> list[K8sClusterRecord]:
    """List infra_cluster rows for the given types (default: all known types)."""
    types = infra_types or tuple(sorted(KNOWN_INFRA_TYPES))
    if not types:
        return []
    placeholders = ", ".join("?" for _ in types)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT idx, cluster_name, last_update, cron, cron_expr, infra_type
            FROM infra_cluster
            WHERE infra_type IN ({placeholders})
            ORDER BY cluster_name
            """,
            types,
        ).fetchall()
    return [_cluster_record_from_row(row) for row in rows]


def list_k8s_clusters(database_path: str | Path) -> list[K8sClusterRecord]:
    """List infra_cluster rows with infra_type=k8s (scrape / shape)."""
    return list_infra_clusters(database_path, infra_types=(DEFAULT_INFRA_TYPE,))


def list_scheduled_k8s_clusters(database_path: str | Path) -> list[K8sClusterRecord]:
    """Cron-enabled clusters for scrapeable infra types (k8s + kubevirt)."""
    managed = tuple(sorted(KNOWN_INFRA_TYPES))
    placeholders = ", ".join("?" for _ in managed)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT idx, cluster_name, last_update, cron, cron_expr, infra_type
            FROM infra_cluster
            WHERE cron = 1 AND infra_type IN ({placeholders})
            ORDER BY cluster_name
            """,
            managed,
        ).fetchall()
    return [_cluster_record_from_row(row) for row in rows]


def get_k8s_cluster(
    database_path: str | Path,
    cluster_idx: int,
) -> K8sClusterRecord | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, cluster_name, last_update, cron, cron_expr, infra_type
            FROM infra_cluster
            WHERE idx = ?
            """,
            (cluster_idx,),
        ).fetchone()
    if row is None:
        return None
    return _cluster_record_from_row(row)


def delete_k8s_cluster(database_path: str | Path, cluster_idx: int) -> bool:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, cluster_name, infra_type
            FROM infra_cluster
            WHERE idx = ?
            """,
            (cluster_idx,),
        ).fetchone()
        if row is None:
            return False
        infra_type = validate_infra_type(
            str(row["infra_type"] or DEFAULT_INFRA_TYPE)
        )
        # K8S inventory tables share cluster_name prefix; safe no-op for other types.
        drop_cluster_inventory_tables(connection, str(row["cluster_name"]))
        connection.execute("DELETE FROM infra_cluster WHERE idx = ?", (cluster_idx,))
        connection.commit()
    return True


def save_k8s_clusters(
    database_path: str | Path,
    clusters: list[dict[str, Any]],
) -> list[K8sClusterRecord]:
    """Replace known infra_cluster rows with the provided list.

    - Existing idx kept when present
    - Names must be unique and non-empty
    - Clusters removed from the list are deleted (with per-cluster table drop)
    - Renamed clusters rename their inventory tables
    - Persists cron / cron_expr / infra_type when provided
    """
    normalized: list[tuple[int | None, str, bool, str, str]] = []
    seen_names: set[str] = set()
    for item in clusters:
        name = validate_cluster_name(str(item.get("cluster_name") or ""))
        if name in seen_names:
            raise ValueError(f"중복된 cluster_name 입니다: {name}")
        seen_names.add(name)
        raw_idx = item.get("idx")
        idx: int | None
        if raw_idx is None or raw_idx == "":
            idx = None
        else:
            idx = int(raw_idx)
            if idx < 1:
                raise ValueError(f"잘못된 idx 입니다: {raw_idx}")
        cron_enabled = _as_bool(item.get("cron"), default=False)
        cron_expr = validate_cron_expr(item.get("cron_expr"))
        infra_type = validate_infra_type(item.get("infra_type") or DEFAULT_INFRA_TYPE)
        normalized.append((idx, name, cron_enabled, cron_expr, infra_type))

    managed_types = tuple(sorted(KNOWN_INFRA_TYPES))
    placeholders = ", ".join("?" for _ in managed_types)

    with get_connection(database_path) as connection:
        existing_rows = connection.execute(
            f"""
            SELECT idx, cluster_name, last_update, cron, cron_expr, infra_type
            FROM infra_cluster
            WHERE infra_type IN ({placeholders})
            """,
            managed_types,
        ).fetchall()
        existing_by_idx = {int(row["idx"]): row for row in existing_rows}
        keep_ids: set[int] = set()

        for idx, name, cron_enabled, cron_expr, infra_type in normalized:
            if idx is not None:
                if idx not in existing_by_idx:
                    raise ValueError(f"존재하지 않는 클러스터 idx 입니다: {idx}")
                old_name = str(existing_by_idx[idx]["cluster_name"])
                if old_name != name:
                    rename_cluster_inventory_tables(connection, old_name, name)
                connection.execute(
                    """
                    UPDATE infra_cluster
                    SET cluster_name = ?, cron = ?, cron_expr = ?, infra_type = ?
                    WHERE idx = ?
                    """,
                    (name, 1 if cron_enabled else 0, cron_expr, infra_type, idx),
                )
                keep_ids.add(idx)
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO infra_cluster (
                        cluster_name, last_update, cron, cron_expr, infra_type
                    )
                    VALUES (?, NULL, ?, ?, ?)
                    """,
                    (name, 1 if cron_enabled else 0, cron_expr, infra_type),
                )
                keep_ids.add(int(cursor.lastrowid))

        for row in existing_rows:
            cluster_id = int(row["idx"])
            if cluster_id in keep_ids:
                continue
            drop_cluster_inventory_tables(connection, str(row["cluster_name"]))
            connection.execute("DELETE FROM infra_cluster WHERE idx = ?", (cluster_id,))

        connection.commit()

    return list_infra_clusters(database_path)


def get_or_create_k8s_cluster(connection, cluster_name: str) -> int:
    name = validate_cluster_name(cluster_name)

    row = connection.execute(
        """
        SELECT idx, infra_type FROM infra_cluster
        WHERE cluster_name = ?
        """,
        (name,),
    ).fetchone()
    if row is not None:
        infra_type = str(row["infra_type"] or DEFAULT_INFRA_TYPE).strip() or DEFAULT_INFRA_TYPE
        if infra_type != DEFAULT_INFRA_TYPE:
            raise ValueError(
                f"cluster_name '{name}' 은 infra_type={infra_type} 로 이미 등록되어 있습니다."
            )
        return int(row["idx"])

    cursor = connection.execute(
        """
        INSERT INTO infra_cluster (
            cluster_name, last_update, cron, cron_expr, infra_type
        )
        VALUES (?, NULL, 0, ?, ?)
        """,
        (name, DEFAULT_CRON_EXPR, DEFAULT_INFRA_TYPE),
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
        UPDATE infra_cluster
        SET last_update = ?
        WHERE idx = ?
        """,
        (stamp, cluster_id),
    )
    return stamp


def replace_cluster_snapshot(
    database_path: str | Path,
    snapshot: K8sClusterSnapshot,
    *,
    cluster_idx: int | None = None,
) -> dict[str, Any]:
    cluster_name = validate_cluster_name(snapshot.cluster_name)

    with get_connection(database_path) as connection:
        if cluster_idx is not None:
            row = connection.execute(
                "SELECT idx, cluster_name, last_update FROM infra_cluster WHERE idx = ?",
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
            cluster_id = get_or_create_k8s_cluster(connection, cluster_name)
            row = connection.execute(
                "SELECT last_update FROM infra_cluster WHERE idx = ?",
                (cluster_id,),
            ).fetchone()
            previous_last_update = (
                str(row["last_update"]) if row and row["last_update"] else None
            )

        stamp = format_backup_stamp(previous_last_update)
        backups = backup_cluster_inventory_tables(
            connection, cluster_name, stamp=stamp
        )
        pruned = prune_cluster_inventory_backups(connection, cluster_name)
        nodes_t, ns_t, dep_t, pvc_t, pods_on_nodes_t = ensure_cluster_inventory_tables(
            connection, cluster_name
        )

        # Clear in FK-safe order
        connection.execute(f"DELETE FROM {_quote_ident(pods_on_nodes_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(pvc_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(dep_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(ns_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(nodes_t)}")

        for node in snapshot.nodes:
            connection.execute(
                f"""
                INSERT INTO {_quote_ident(nodes_t)} (
                    node_name, node_cpu, node_mem, node_os, node_k8s_ver, node_role
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    node.node_name[:50],
                    node.node_cpu,
                    node.node_mem,
                    (node.node_os or None) and node.node_os[:50],
                    (node.node_k8s_ver or None) and node.node_k8s_ver[:50],
                    (node.node_role or None) and node.node_role[:30],
                ),
            )

        namespace_ids: dict[str, int] = {}
        for namespace in snapshot.namespaces:
            cursor = connection.execute(
                f"""
                INSERT INTO {_quote_ident(ns_t)} (
                    namespace, okd_display_name,
                    resource_quota_cpu_limit, resource_quota_mem_limit, resource_quota_pod_limit,
                    okd_egressip1, okd_egressip2,
                    using_egressip, egressip_assigned_node
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace.namespace[:50],
                    (namespace.okd_display_name or None) and namespace.okd_display_name[:100],
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
                    namespace_id, name, type, replicas, readyreplicas,
                    resource_cpu_request, resource_mem_request,
                    resource_cpu_limit, resource_mem_limit,
                    containers_cnt, containers_name, containers_image
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace_id,
                    deployment.name[:50],
                    deployment.type[:20],
                    deployment.replicas,
                    deployment.readyreplicas,
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

        for pod in snapshot.pods_on_nodes:
            if not pod.node_name or not pod.namespace or not pod.pod_name:
                continue
            connection.execute(
                f"""
                INSERT INTO {_quote_ident(pods_on_nodes_t)} (
                    node_name, namespace, pod_name,
                    cpu_request, cpu_limit, mem_request, mem_limit, age
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pod.node_name[:50],
                    pod.namespace[:50],
                    pod.pod_name[:50],
                    pod.cpu_request,
                    pod.cpu_limit,
                    pod.mem_request,
                    pod.mem_limit,
                    (pod.age or None) and pod.age[:20],
                ),
            )

        last_update = touch_k8s_cluster_last_update(connection, cluster_id)
        connection.commit()

    counts = {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "tables": {
            "nodes": nodes_t,
            "namespaces": ns_t,
            "deployments": dep_t,
            "pvcs": pvc_t,
            "pods_on_nodes": pods_on_nodes_t,
        },
        "nodes": len(snapshot.nodes),
        "namespaces": len(snapshot.namespaces),
        "deployments": len(snapshot.deployments),
        "pvcs": len(snapshot.pvcs),
        "pods_on_nodes": len(snapshot.pods_on_nodes),
    }
    logger.info(
        "Replaced per-cluster inventory cluster=%s idx=%s last_update=%s "
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
