"""Pre-resolve inventory snapshot generations for INFRA_GAP_ANALYSIS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection, resolve_database_path
from backend.app.db.k8s_inventory import (
    DEFAULT_INFRA_TYPE,
    INFRA_TYPE_VSPHERE,
    _list_user_tables,
    cluster_inventory_tables,
    list_cluster_inventory_backup_stamps,
    validate_cluster_name,
    validate_infra_type,
)
from backend.app.db.kubevirt_inventory import (
    KUBEVIRT_INVENTORY_SUFFIXES,
    kubevirt_inventory_table,
    list_kubevirt_inventory_backup_stamps,
)
from backend.app.db.vsphere_inventory import (
    VSPHERE_INVENTORY_SUFFIXES,
    list_vsphere_inventory_backup_stamps,
    vsphere_inventory_table,
)

GAP_ANALYSIS_ALLOWED_TOOLS: frozenset[str] = frozenset({"query_readonly"})
GAP_ANALYSIS_BACKUP_LIMIT = 2

KUBEVIRT_GAP_EXCLUDED_SUFFIXES = frozenset({"kubevirt_vm_volumes"})
VSPHERE_GAP_EXCLUDED_SUFFIXES = frozenset({"vsphere_datastores"})


@dataclass(frozen=True)
class GapGenerationPoint:
    label: str
    stamp: str | None
    tables: dict[str, str]


@dataclass(frozen=True)
class GapAnalysisGenerationContext:
    cluster_name: str
    infra_type: str
    generations: tuple[GapGenerationPoint, ...]


def _gap_live_tables(cluster_name: str, infra_type: str) -> tuple[str, ...]:
    name = validate_cluster_name(cluster_name)
    infra = validate_infra_type(infra_type)
    if infra == DEFAULT_INFRA_TYPE:
        return cluster_inventory_tables(name)
    if infra == "kubevirt":
        return tuple(
            kubevirt_inventory_table(name, suffix)
            for suffix in KUBEVIRT_INVENTORY_SUFFIXES
            if suffix not in KUBEVIRT_GAP_EXCLUDED_SUFFIXES
        )
    if infra == INFRA_TYPE_VSPHERE:
        return tuple(
            vsphere_inventory_table(name, suffix)
            for suffix in VSPHERE_INVENTORY_SUFFIXES
            if suffix not in VSPHERE_GAP_EXCLUDED_SUFFIXES
        )
    raise ValueError(f"지원하지 않는 infra_type 입니다: {infra}")


def _list_backup_stamps(connection, cluster_name: str, infra_type: str) -> list[str]:
    if infra_type == DEFAULT_INFRA_TYPE:
        return list_cluster_inventory_backup_stamps(connection, cluster_name)
    if infra_type == "kubevirt":
        return list_kubevirt_inventory_backup_stamps(connection, cluster_name)
    if infra_type == INFRA_TYPE_VSPHERE:
        return list_vsphere_inventory_backup_stamps(connection, cluster_name)
    return []


def _live_table_suffix(cluster_name: str, live_table: str) -> str:
    prefix = f"{cluster_name}_"
    if not live_table.startswith(prefix):
        return live_table
    return live_table[len(prefix) :]


def _generation_tables(
    *,
    cluster_name: str,
    live_tables: tuple[str, ...],
    stamp: str | None,
    tables_in_db: set[str],
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for live_table in live_tables:
        if stamp is None:
            if live_table in tables_in_db:
                resolved[_live_table_suffix(cluster_name, live_table)] = live_table
            continue
        backup_name = f"{live_table}_{stamp}"
        if backup_name in tables_in_db:
            resolved[_live_table_suffix(cluster_name, live_table)] = backup_name
    return resolved


def resolve_gap_analysis_generations(
    *,
    cluster_name: str,
    infra_type: str,
    database_path: str | Path | None = None,
) -> GapAnalysisGenerationContext:
    name = validate_cluster_name(cluster_name)
    infra = validate_infra_type(infra_type)
    db_path = resolve_database_path(database_path)
    live_tables = _gap_live_tables(name, infra)

    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT cluster_name FROM infra_cluster WHERE cluster_name = ?",
            (name,),
        ).fetchone()
        if row is None:
            raise ValueError(f"등록되지 않은 cluster_name 입니다: {name}")

        tables_in_db = set(_list_user_tables(connection))
        stamps = _list_backup_stamps(connection, name, infra)[:GAP_ANALYSIS_BACKUP_LIMIT]

        generations: list[GapGenerationPoint] = []
        for stamp in reversed(stamps):
            table_map = _generation_tables(
                cluster_name=name,
                live_tables=live_tables,
                stamp=stamp,
                tables_in_db=tables_in_db,
            )
            if table_map:
                generations.append(
                    GapGenerationPoint(label=stamp, stamp=stamp, tables=table_map)
                )

        latest_map = _generation_tables(
            cluster_name=name,
            live_tables=live_tables,
            stamp=None,
            tables_in_db=tables_in_db,
        )
        if latest_map:
            generations.append(
                GapGenerationPoint(label="latest", stamp=None, tables=latest_map)
            )

    if not generations:
        raise ValueError(
            f"cluster_name={name} infra_type={infra} 에 대한 인벤토리 테이블을 찾을 수 없습니다."
        )

    return GapAnalysisGenerationContext(
        cluster_name=name,
        infra_type=infra,
        generations=tuple(generations),
    )


def format_generation_context_block(context: GapAnalysisGenerationContext) -> str:
    lines = [
        "Pre-resolved snapshot generations (oldest → newest).",
        "Use ONLY these table names with the query_readonly MCP tool.",
        "Do NOT call list_schemas, list_tables, or describe_table.",
        "",
    ]
    for index, generation in enumerate(context.generations, start=1):
        if generation.stamp:
            lines.append(f"Generation {index} (backup stamp {generation.stamp}):")
        else:
            lines.append(f"Generation {index} (latest):")
        for suffix in sorted(generation.tables):
            lines.append(f"  - {suffix}: {generation.tables[suffix]}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_gap_analysis_user_message(
    *,
    cluster_name: str,
    infra_type: str,
    database_path: str | Path | None = None,
) -> str:
    context = resolve_gap_analysis_generations(
        cluster_name=cluster_name,
        infra_type=infra_type,
        database_path=database_path,
    )
    generation_block = format_generation_context_block(context)
    return (
        f"cluster_name: {context.cluster_name}\n"
        f"infra_type: {context.infra_type}\n\n"
        f"{generation_block}\n\n"
        "Perform infrastructure inventory gap analysis using the pre-resolved generations above. "
        "Compare inventory rows between consecutive generations with query_readonly only. "
        "Report added, removed, and changed resources with count trends. "
        "Follow the system prompt output format."
    )
