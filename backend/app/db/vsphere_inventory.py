"""Persist vSphere inventory into per-cluster dynamic tables.

Layout (infra_type=vSphere):
  {cluster_name}_vsphere_cluster
  {cluster_name}_vsphere_hosts          (cluster_id → vsphere_cluster.cluster_id)
  {cluster_name}_vsphere_vms_on_host

vCenter mapping source:
  - Clusters: GET /api/vcenter/cluster (cluster, name, ha_enabled, drs_enabled)
  - Host↔cluster: GET /api/vcenter/host?clusters=<cluster_id>
    (standalone ESXi hosts have NULL cluster_id)

Backups: {table}_{YYYYMMDD_HHMMSS} (keep newest 4 stamp sets).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.db.introspection import (
    ensure_table_idx_serial,
    list_table_columns,
    pk_autoincrement_sql,
)
from backend.app.db.k8s_inventory import (
    MAX_INVENTORY_BACKUP_GENERATIONS,
    _BACKUP_STAMP_SUFFIX_RE,
    _list_user_tables,
    _quote_ident,
    format_backup_stamp,
    touch_k8s_cluster_last_update,
    validate_cluster_name,
)

logger = logging.getLogger(__name__)

VSPHERE_INVENTORY_SUFFIXES = (
    "vsphere_cluster",
    "vsphere_hosts",
    "vsphere_vms_on_host",
)


@dataclass
class VsphereComputeClusterRow:
    """One vCenter ClusterComputeResource (not infra_cluster registry)."""

    cluster_id: str
    cluster_name: str | None = None
    ha_enabled: bool | None = None
    drs_enabled: bool | None = None


@dataclass
class VsphereHostRow:
    host_id: str
    host_name: str | None = None
    connection_state: str | None = None
    power_state: str | None = None
    cluster_id: str | None = None


@dataclass
class VsphereVmOnHostRow:
    vm_id: str
    host_id: str
    vm_name: str | None = None
    power_state: str | None = None
    cpu_count: int | None = None
    memory_mib: int | None = None


@dataclass
class VsphereClusterSnapshot:
    cluster_name: str
    compute_clusters: list[VsphereComputeClusterRow] = field(default_factory=list)
    hosts: list[VsphereHostRow] = field(default_factory=list)
    vms_on_host: list[VsphereVmOnHostRow] = field(default_factory=list)


def vsphere_inventory_table(cluster_name: str, suffix: str) -> str:
    name = validate_cluster_name(cluster_name)
    if suffix not in VSPHERE_INVENTORY_SUFFIXES:
        raise ValueError(f"unknown vsphere inventory suffix: {suffix}")
    return f"{name}_{suffix}"


def vsphere_inventory_tables(cluster_name: str) -> tuple[str, ...]:
    return tuple(
        vsphere_inventory_table(cluster_name, suffix)
        for suffix in VSPHERE_INVENTORY_SUFFIXES
    )


def _ensure_hosts_cluster_id_column(connection, hosts_table: str) -> None:
    columns = list_table_columns(connection, hosts_table)
    if "cluster_id" not in columns:
        connection.execute(
            f"ALTER TABLE {_quote_ident(hosts_table)} "
            "ADD COLUMN cluster_id VARCHAR(30)"
        )
        logger.info("Added %s.cluster_id", hosts_table)


def ensure_vsphere_inventory_tables(
    connection,
    cluster_name: str,
) -> dict[str, str]:
    name = validate_cluster_name(cluster_name)
    tables = _list_user_tables(connection)
    clusters_t = vsphere_inventory_table(name, "vsphere_cluster")
    hosts_t = vsphere_inventory_table(name, "vsphere_hosts")
    vms_t = vsphere_inventory_table(name, "vsphere_vms_on_host")

    if clusters_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(clusters_t)} (
                {pk_autoincrement_sql(connection)},
                cluster_id VARCHAR(30) NOT NULL,
                cluster_name VARCHAR(100),
                ha_enabled INTEGER,
                drs_enabled INTEGER
            )
            """
        )
    if hosts_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(hosts_t)} (
                {pk_autoincrement_sql(connection)},
                host_id VARCHAR(30) NOT NULL,
                host_name VARCHAR(100),
                connection_state VARCHAR(30),
                power_state VARCHAR(30),
                cluster_id VARCHAR(30)
            )
            """
        )
    else:
        _ensure_hosts_cluster_id_column(connection, hosts_t)
    if vms_t not in tables:
        connection.execute(
            f"""
            CREATE TABLE {_quote_ident(vms_t)} (
                {pk_autoincrement_sql(connection)},
                vm_id VARCHAR(30) NOT NULL,
                host_id VARCHAR(30) NOT NULL,
                vm_name VARCHAR(100),
                power_state VARCHAR(30),
                cpu_count INTEGER,
                memory_mib INTEGER
            )
            """
        )
    for table_name in (clusters_t, hosts_t, vms_t):
        ensure_table_idx_serial(connection, table_name)
    return {
        "clusters": clusters_t,
        "hosts": hosts_t,
        "vms_on_host": vms_t,
    }


def drop_vsphere_inventory_tables(connection, cluster_name: str) -> list[str]:
    """Drop live + backup tables for a vSphere cluster."""
    name = validate_cluster_name(cluster_name)
    tables = _list_user_tables(connection)
    dropped: list[str] = []
    for live_table in vsphere_inventory_tables(name):
        prefix = f"{live_table}_"
        for table_name in sorted(tables):
            if table_name == live_table or table_name.startswith(prefix):
                connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
                dropped.append(table_name)
    if dropped:
        logger.info("Dropped vsphere inventory tables for %s: %s", name, dropped)
    return dropped


def rename_vsphere_inventory_tables(
    connection,
    old_name: str,
    new_name: str,
) -> list[tuple[str, str]]:
    old = validate_cluster_name(old_name)
    new = validate_cluster_name(new_name)
    if old == new:
        return []
    tables = _list_user_tables(connection)
    renamed: list[tuple[str, str]] = []
    for suffix in VSPHERE_INVENTORY_SUFFIXES:
        old_live = vsphere_inventory_table(old, suffix)
        new_live = vsphere_inventory_table(new, suffix)
        candidates = [old_live] + [
            table_name
            for table_name in tables
            if table_name.startswith(f"{old_live}_")
        ]
        for old_table in candidates:
            if old_table not in tables:
                continue
            stamp = old_table[len(old_live) :]  # '' or '_YYYYMMDD_HHMMSS'
            new_table = f"{new_live}{stamp}"
            if new_table in tables:
                connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(new_table)}")
            connection.execute(
                f"ALTER TABLE {_quote_ident(old_table)} RENAME TO {_quote_ident(new_table)}"
            )
            renamed.append((old_table, new_table))
    return renamed


def backup_vsphere_inventory_tables(
    connection,
    cluster_name: str,
    *,
    stamp: str,
) -> list[str]:
    created: list[str] = []
    safe_stamp = re.sub(r"[^0-9_]", "", stamp) or format_backup_stamp(None)
    tables = _list_user_tables(connection)
    for table_name in vsphere_inventory_tables(cluster_name):
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
        logger.info("Backed up vsphere cluster=%s -> %s", cluster_name, created)
    return created


def _backup_stamp_from_table(live_table: str, table_name: str) -> str | None:
    prefix = f"{live_table}_"
    if not table_name.startswith(prefix):
        return None
    stamp = table_name[len(prefix) :]
    if _BACKUP_STAMP_SUFFIX_RE.fullmatch(stamp):
        return stamp
    return None


def list_vsphere_inventory_backup_stamps(connection, cluster_name: str) -> list[str]:
    stamps: set[str] = set()
    tables = _list_user_tables(connection)
    for live_table in vsphere_inventory_tables(cluster_name):
        for table_name in tables:
            stamp = _backup_stamp_from_table(live_table, table_name)
            if stamp:
                stamps.add(stamp)
    return sorted(stamps, reverse=True)


def prune_vsphere_inventory_backups(
    connection,
    cluster_name: str,
    *,
    keep: int = MAX_INVENTORY_BACKUP_GENERATIONS,
) -> list[str]:
    keep_n = max(0, int(keep))
    stamps = list_vsphere_inventory_backup_stamps(connection, cluster_name)
    stale_stamps = set(stamps[keep_n:])
    if not stale_stamps:
        return []

    dropped: list[str] = []
    tables = _list_user_tables(connection)
    for live_table in vsphere_inventory_tables(cluster_name):
        for table_name in sorted(tables):
            stamp = _backup_stamp_from_table(live_table, table_name)
            if stamp and stamp in stale_stamps:
                connection.execute(f"DROP TABLE IF EXISTS {_quote_ident(table_name)}")
                dropped.append(table_name)
    if dropped:
        logger.info(
            "Pruned vsphere inventory backups cluster=%s dropped=%s",
            cluster_name,
            dropped,
        )
    return dropped


def _as_int_flag(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def replace_vsphere_snapshot(
    database_path: str | Path,
    snapshot: VsphereClusterSnapshot,
    *,
    cluster_idx: int,
) -> dict[str, Any]:
    cluster_name = validate_cluster_name(snapshot.cluster_name)

    with get_connection(database_path) as connection:
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

        stamp = format_backup_stamp(previous_last_update)
        backups = backup_vsphere_inventory_tables(
            connection, cluster_name, stamp=stamp
        )
        pruned = prune_vsphere_inventory_backups(connection, cluster_name)
        table_map = ensure_vsphere_inventory_tables(connection, cluster_name)
        clusters_t = table_map["clusters"]
        hosts_t = table_map["hosts"]
        vms_t = table_map["vms_on_host"]

        connection.execute(f"DELETE FROM {_quote_ident(vms_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(hosts_t)}")
        connection.execute(f"DELETE FROM {_quote_ident(clusters_t)}")

        for compute in snapshot.compute_clusters:
            connection.execute(
                f"""
                INSERT INTO {_quote_ident(clusters_t)} (
                    cluster_id, cluster_name, ha_enabled, drs_enabled
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    compute.cluster_id[:30],
                    (compute.cluster_name or None) and compute.cluster_name[:100],
                    _as_int_flag(compute.ha_enabled),
                    _as_int_flag(compute.drs_enabled),
                ),
            )

        for host in snapshot.hosts:
            connection.execute(
                f"""
                INSERT INTO {_quote_ident(hosts_t)} (
                    host_id, host_name, connection_state, power_state, cluster_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    host.host_id[:30],
                    (host.host_name or None) and host.host_name[:100],
                    (host.connection_state or None) and host.connection_state[:30],
                    (host.power_state or None) and host.power_state[:30],
                    (host.cluster_id or None) and host.cluster_id[:30],
                ),
            )

        for vm in snapshot.vms_on_host:
            connection.execute(
                f"""
                INSERT INTO {_quote_ident(vms_t)} (
                    vm_id, host_id, vm_name, power_state, cpu_count, memory_mib
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    vm.vm_id[:30],
                    vm.host_id[:30],
                    (vm.vm_name or None) and vm.vm_name[:100],
                    (vm.power_state or None) and vm.power_state[:30],
                    vm.cpu_count,
                    vm.memory_mib,
                ),
            )

        last_update = touch_k8s_cluster_last_update(connection, cluster_id)
        connection.commit()

    return {
        "last_update": last_update,
        "clusters": len(snapshot.compute_clusters),
        "hosts": len(snapshot.hosts),
        "vms": len(snapshot.vms_on_host),
        "backup_tables": backups,
        "pruned_backup_tables": pruned,
    }
