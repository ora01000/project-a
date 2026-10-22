"""Infra dictionary: summarize infra_cluster + latest inventory into Redis for job-intake helper."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.db.introspection import list_table_columns
from backend.app.db.k8s_inventory import (
    DEFAULT_INFRA_TYPE,
    INFRA_TYPE_VSPHERE,
    cluster_inventory_table,
    list_infra_clusters,
    _list_user_tables,
    _quote_ident,
)
from backend.app.db.kubevirt_inventory import kubevirt_inventory_table
from backend.app.db.vsphere_inventory import vsphere_inventory_table
from backend.app.services.redis_client import get_redis
from backend.app.timezone import format_display_datetime, now_display_datetime

logger = logging.getLogger(__name__)

REDIS_KEY_INFRA_TYPE = "infra_dict:infra_type"
REDIS_KEY_K8S_NODES = "infra_dict:k8s_cluster_nodes"
REDIS_KEY_K8S_NAMESPACES = "infra_dict:k8s_cluster_namespaces"
REDIS_KEY_K8S_DEPLOYMENTS = "infra_dict:k8s_cluster_deployments"
REDIS_KEY_KUBEVIRT_NODES = "infra_dict:kubevirt_cluster_nodes"
REDIS_KEY_KUBEVIRT_NAMESPACES = "infra_dict:kubevirt_cluster_namespaces"
REDIS_KEY_KUBEVIRT_DEPLOYMENTS = "infra_dict:kubevirt_cluster_deployments"
REDIS_KEY_KUBEVIRT_VMS = "infra_dict:kubevirt_cluster_vms"
REDIS_KEY_VSPHERE_VMS = "infra_dict:vsphere_cluster_vms"
REDIS_KEY_LOADED_AT = "infra_dict:meta:loaded_at"

INFRA_TYPE_KUBEVIRT = "kubevirt"

# PLAN: k8s + kubevirt + vSphere (VM names) for now.
_SUPPORTED_LOAD_TYPES = frozenset(
    {DEFAULT_INFRA_TYPE, INFRA_TYPE_KUBEVIRT, INFRA_TYPE_VSPHERE}
)

def _column_values(connection, table: str, column: str) -> list[str]:
    tables = _list_user_tables(connection)
    if table not in tables:
        return []
    try:
        col = _quote_ident(column)
        rows = connection.execute(
            f"SELECT DISTINCT {col} AS v "
            f"FROM {_quote_ident(table)} "
            f"WHERE {col} IS NOT NULL "
            f"AND TRIM({col}::text) <> '' "
            f"ORDER BY 1"
        ).fetchall()
    except Exception:
        logger.exception("infra_dictionary query failed table=%s column=%s", table, column)
        return []
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = str(row["v"] or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def _namespace_display_values(connection, table: str) -> list[str]:
    """Return namespace labels; append (okd_display_name) when present."""
    tables = _list_user_tables(connection)
    if table not in tables:
        return []
    columns = list_table_columns(connection, table)
    has_display = "okd_display_name" in columns
    try:
        if has_display:
            rows = connection.execute(
                f"""
                SELECT DISTINCT
                    {_quote_ident("namespace")} AS ns,
                    {_quote_ident("okd_display_name")} AS disp
                FROM {_quote_ident(table)}
                WHERE {_quote_ident("namespace")} IS NOT NULL
                  AND TRIM({_quote_ident("namespace")}::text) <> ''
                ORDER BY 1
                """
            ).fetchall()
        else:
            return _column_values(connection, table, "namespace")
    except Exception:
        logger.exception("infra_dictionary namespace query failed table=%s", table)
        return []

    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        ns = str(row["ns"] or "").strip()
        if not ns:
            continue
        disp = str(row["disp"] or "").strip()
        label = f"{ns} ({disp})" if disp else ns
        if label in seen:
            continue
        seen.add(label)
        values.append(label)
    return values


def build_infra_dictionary_payload(database_path: str | Path) -> dict[str, Any]:
    """Build redis-ready maps from Postgres (k8s + kubevirt + vSphere VMs)."""
    type_to_clusters: dict[str, list[str]] = {}
    k8s_nodes: dict[str, list[str]] = {}
    k8s_namespaces: dict[str, list[str]] = {}
    k8s_deployments: dict[str, list[str]] = {}
    kv_nodes: dict[str, list[str]] = {}
    kv_namespaces: dict[str, list[str]] = {}
    kv_deployments: dict[str, list[str]] = {}
    kv_vms: dict[str, list[str]] = {}
    vs_vms: dict[str, list[str]] = {}

    clusters = list_infra_clusters(database_path)
    with get_connection(database_path) as connection:
        for record in clusters:
            infra_type = (record.infra_type or DEFAULT_INFRA_TYPE).strip() or DEFAULT_INFRA_TYPE
            name = (record.cluster_name or "").strip()
            if not name:
                continue
            display = (record.display_name or "").strip()
            cluster_label = f"{name} ({display})" if display else name
            type_to_clusters.setdefault(infra_type, [])
            if cluster_label not in type_to_clusters[infra_type]:
                type_to_clusters[infra_type].append(cluster_label)

            if infra_type not in _SUPPORTED_LOAD_TYPES:
                continue

            if infra_type == DEFAULT_INFRA_TYPE:
                nodes_t = cluster_inventory_table(name, "k8s_nodes")
                ns_t = cluster_inventory_table(name, "k8s_namespaces")
                dep_t = cluster_inventory_table(name, "k8s_deployments")
                k8s_nodes[name] = _column_values(connection, nodes_t, "node_name")
                k8s_namespaces[name] = _namespace_display_values(connection, ns_t)
                k8s_deployments[name] = _column_values(connection, dep_t, "name")
            elif infra_type == INFRA_TYPE_KUBEVIRT:
                nodes_t = kubevirt_inventory_table(name, "kubevirt_nodes")
                ns_t = kubevirt_inventory_table(name, "kubevirt_namespaces")
                dep_t = kubevirt_inventory_table(name, "kubevirt_deployments")
                vms_t = kubevirt_inventory_table(name, "kubevirt_vms")
                kv_nodes[name] = _column_values(connection, nodes_t, "node_name")
                kv_namespaces[name] = _namespace_display_values(connection, ns_t)
                kv_deployments[name] = _column_values(connection, dep_t, "name")
                kv_vms[name] = _column_values(connection, vms_t, "name")
            elif infra_type == INFRA_TYPE_VSPHERE:
                vms_t = vsphere_inventory_table(name, "vsphere_vms_on_host")
                vs_vms[name] = _column_values(connection, vms_t, "vm_name")

    for names in type_to_clusters.values():
        names.sort()

    return {
        "infra_type": type_to_clusters,
        "k8s_cluster_nodes": k8s_nodes,
        "k8s_cluster_namespaces": k8s_namespaces,
        "k8s_cluster_deployments": k8s_deployments,
        "kubevirt_cluster_nodes": kv_nodes,
        "kubevirt_cluster_namespaces": kv_namespaces,
        "kubevirt_cluster_deployments": kv_deployments,
        "kubevirt_cluster_vms": kv_vms,
        "vsphere_cluster_vms": vs_vms,
    }


async def _replace_hash(redis, key: str, mapping: dict[str, list[str]]) -> None:
    await redis.delete(key)
    if not mapping:
        return
    payload = {field: json.dumps(values, ensure_ascii=False) for field, values in mapping.items()}
    await redis.hset(key, mapping=payload)


async def refresh_infra_dictionary(
    database_path: str | Path,
    *,
    reason: str = "manual",
) -> dict[str, Any]:
    """Load infra dictionary into Redis. Logs elapsed time for debugging."""
    started = time.perf_counter()
    payload = await asyncio.to_thread(build_infra_dictionary_payload, database_path)
    redis = get_redis()
    await _replace_hash(redis, REDIS_KEY_INFRA_TYPE, payload["infra_type"])
    await _replace_hash(redis, REDIS_KEY_K8S_NODES, payload["k8s_cluster_nodes"])
    await _replace_hash(redis, REDIS_KEY_K8S_NAMESPACES, payload["k8s_cluster_namespaces"])
    await _replace_hash(redis, REDIS_KEY_K8S_DEPLOYMENTS, payload["k8s_cluster_deployments"])
    await _replace_hash(redis, REDIS_KEY_KUBEVIRT_NODES, payload["kubevirt_cluster_nodes"])
    await _replace_hash(redis, REDIS_KEY_KUBEVIRT_NAMESPACES, payload["kubevirt_cluster_namespaces"])
    await _replace_hash(
        redis, REDIS_KEY_KUBEVIRT_DEPLOYMENTS, payload["kubevirt_cluster_deployments"]
    )
    await _replace_hash(redis, REDIS_KEY_KUBEVIRT_VMS, payload["kubevirt_cluster_vms"])
    await _replace_hash(redis, REDIS_KEY_VSPHERE_VMS, payload["vsphere_cluster_vms"])
    loaded_at = format_display_datetime(now_display_datetime())
    await redis.set(REDIS_KEY_LOADED_AT, loaded_at)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    cluster_count = sum(len(v) for v in payload["infra_type"].values())
    logger.info(
        "infra_dictionary redis loaded reason=%s loaded_at=%s elapsed_ms=%.1f "
        "types=%s clusters=%s",
        reason,
        loaded_at,
        elapsed_ms,
        sorted(payload["infra_type"].keys()),
        cluster_count,
    )
    return {
        "loaded_at": loaded_at,
        "elapsed_ms": round(elapsed_ms, 1),
        "infra_type": payload["infra_type"],
        "reason": reason,
    }


async def _hash_as_lists(redis, key: str) -> dict[str, list[str]]:
    raw = await redis.hgetall(key)
    result: dict[str, list[str]] = {}
    for field, value in (raw or {}).items():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            result[str(field)] = [str(item) for item in parsed]
        else:
            result[str(field)] = []
    return result


async def read_infra_dictionary() -> dict[str, Any]:
    """Read dictionary maps from Redis for the job-intake helper API."""
    redis = get_redis()
    loaded_at = await redis.get(REDIS_KEY_LOADED_AT)
    return {
        "loaded_at": loaded_at or "",
        "infra_type": await _hash_as_lists(redis, REDIS_KEY_INFRA_TYPE),
        "k8s_cluster_nodes": await _hash_as_lists(redis, REDIS_KEY_K8S_NODES),
        "k8s_cluster_namespaces": await _hash_as_lists(redis, REDIS_KEY_K8S_NAMESPACES),
        "k8s_cluster_deployments": await _hash_as_lists(redis, REDIS_KEY_K8S_DEPLOYMENTS),
        "kubevirt_cluster_nodes": await _hash_as_lists(redis, REDIS_KEY_KUBEVIRT_NODES),
        "kubevirt_cluster_namespaces": await _hash_as_lists(redis, REDIS_KEY_KUBEVIRT_NAMESPACES),
        "kubevirt_cluster_deployments": await _hash_as_lists(
            redis, REDIS_KEY_KUBEVIRT_DEPLOYMENTS
        ),
        "kubevirt_cluster_vms": await _hash_as_lists(redis, REDIS_KEY_KUBEVIRT_VMS),
        "vsphere_cluster_vms": await _hash_as_lists(redis, REDIS_KEY_VSPHERE_VMS),
    }
