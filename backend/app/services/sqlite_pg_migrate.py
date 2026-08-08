"""SQLite → PostgreSQL one-shot data migration.

CLI: ``uv run scripts/migrate_sqlite_to_postgres.py``
Admin API: ``POST /api/admin/migrate-sqlite-to-postgres``
"""

from __future__ import annotations

import io
import re
import sqlite3
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Core tables: FK-safe insert order. Values = preferred PG table name.
# ---------------------------------------------------------------------------
CORE_TABLE_MAP: list[tuple[str, str]] = [
    ("users", "users"),
    ("agentruntime", "agentruntime"),
    ("signup_notifications", "signup_notifications"),
    ("notice_board", "notice_board"),
    ("jobs", "jobs"),
    ("jobs_result", "jobs_result"),
    ("mynotes", "mynotes"),
    ("mynote_contents", "mynote_contents"),
    ("infra_cluster", "infra_cluster"),
    ("k8s_cluster", "infra_cluster"),  # legacy → infra_cluster
]

# Inventory / backup table name patterns (SQLite user tables).
_INVENTORY_RE = re.compile(
    r"^.+_(?:k8s|kubevirt)_(?:nodes|namespaces|deployments|pvcs|vms|vm_volumes)"
    r"(?:_\d{8}_\d{6})?$"
)

_SKIP_SQLITE = frozenset({"sqlite_sequence"})


@dataclass
class TablePlan:
    sqlite_name: str
    postgres_name: str
    kind: str  # core | inventory | skip
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class MigrationResult:
    ok: bool
    dry_run: bool
    migratable_rows: int
    migrated_rows: int
    mynote_files: int
    log: str
    error: str | None = None
    tables: list[dict[str, Any]] = field(default_factory=list)


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite file not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _list_sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(r["name"]) for r in rows]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    return [str(r["name"]) for r in rows]


def _table_column_types(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    rows = conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    out: list[tuple[str, str]] = []
    for r in rows:
        name = str(r["name"])
        decl = str(r["type"] or "TEXT").upper()
        out.append((name, decl))
    return out


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {_quote_ident(table)}").fetchone()
    return int(row["c"] if row else 0)


def _sqlite_type_to_pg(decl: str, col_name: str) -> str:
    d = decl.upper()
    if col_name == "idx" or col_name.endswith("_id") or col_name == "note_idx":
        if "INT" in d:
            return "BIGINT"
    if "INT" in d:
        return "BIGINT"
    if "REAL" in d or "FLOA" in d or "DOUB" in d:
        return "DOUBLE PRECISION"
    if "BLOB" in d:
        return "BYTEA"
    # VARCHAR(n) keep loosely
    m = re.search(r"VARCHAR\s*\(\s*(\d+)\s*\)", d)
    if m:
        return f"VARCHAR({m.group(1)})"
    return "TEXT"


def build_plans(sqlite_conn: sqlite3.Connection) -> list[TablePlan]:
    existing = set(_list_sqlite_tables(sqlite_conn))
    plans: list[TablePlan] = []
    claimed: set[str] = set()

    # Core (and legacy rename) first — preserve map order, skip missing.
    seen_pg: set[str] = set()
    for sqlite_name, pg_name in CORE_TABLE_MAP:
        if sqlite_name not in existing:
            continue
        if sqlite_name in claimed:
            continue
        # Prefer infra_cluster over k8s_cluster if both exist.
        if pg_name in seen_pg and sqlite_name == "k8s_cluster":
            plans.append(
                TablePlan(
                    sqlite_name=sqlite_name,
                    postgres_name=pg_name,
                    kind="skip",
                    notes=["skipped: infra_cluster already planned"],
                )
            )
            claimed.add(sqlite_name)
            continue

        cols = _table_columns(sqlite_conn, sqlite_name)
        count = _row_count(sqlite_conn, sqlite_name)
        notes: list[str] = []
        if sqlite_name != pg_name:
            notes.append(f"rename {sqlite_name} → {pg_name}")
        if pg_name == "infra_cluster" and "infra_type" not in cols:
            notes.append("will default infra_type='k8s', cron=0, cron_expr='0 23 * * 6'")
        plans.append(
            TablePlan(
                sqlite_name=sqlite_name,
                postgres_name=pg_name,
                kind="core",
                row_count=count,
                columns=cols,
                notes=notes,
            )
        )
        claimed.add(sqlite_name)
        seen_pg.add(pg_name)

    for name in sorted(existing - claimed):
        if name in _SKIP_SQLITE:
            continue
        cols = _table_columns(sqlite_conn, name)
        count = _row_count(sqlite_conn, name)
        if _INVENTORY_RE.match(name):
            plans.append(
                TablePlan(
                    sqlite_name=name,
                    postgres_name=name,
                    kind="inventory",
                    row_count=count,
                    columns=cols,
                )
            )
        else:
            plans.append(
                TablePlan(
                    sqlite_name=name,
                    postgres_name=name,
                    kind="skip",
                    row_count=count,
                    columns=cols,
                    notes=["unrecognized table — not migrated"],
                )
            )
    return plans


def print_plan(plans: list[TablePlan], *, sqlite_path: Path, database_url: str) -> None:
    print("=" * 72)
    print("SQLite → PostgreSQL migration plan")
    print("=" * 72)
    print(f"source : {sqlite_path}")
    # redact password in URL for display
    safe_url = re.sub(r":([^:@/]+)@", ":***@", database_url)
    print(f"target : {safe_url}")
    print()
    for plan in plans:
        flag = {
            "core": "CORE",
            "inventory": "INV ",
            "skip": "SKIP",
        }.get(plan.kind, plan.kind)
        print(
            f"[{flag}] {plan.sqlite_name} → {plan.postgres_name} "
            f"rows={plan.row_count} cols={len(plan.columns)}"
        )
        if plan.notes:
            for note in plan.notes:
                print(f"         · {note}")
    total = sum(p.row_count for p in plans if p.kind != "skip")
    skipped = sum(p.row_count for p in plans if p.kind == "skip")
    print()
    print(f"migratable rows: {total}")
    print(f"skipped rows   : {skipped}")
    print("=" * 72)


def _pg_connect(database_url: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(database_url, row_factory=dict_row)


def _fetch_all_dicts(sqlite_conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = sqlite_conn.execute(f"SELECT * FROM {_quote_ident(table)}").fetchall()
    return [{k: row[k] for k in row.keys()} for row in rows]


def _normalize_infra_cluster_row(row: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    out = dict(row)
    if "cron" not in out:
        out["cron"] = 0
    if "cron_expr" not in out or out["cron_expr"] in (None, ""):
        out["cron_expr"] = "0 23 * * 6"
    if "infra_type" not in out or out["infra_type"] in (None, ""):
        out["infra_type"] = "k8s"
    return out


def _ensure_core_schema(pg_conn, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    pg_conn.execute(sql)
    pg_conn.commit()


def _create_inventory_table(
    pg_conn,
    sqlite_conn: sqlite3.Connection,
    table: str,
) -> list[str]:
    col_types = _table_column_types(sqlite_conn, table)
    cols_sql = []
    col_names: list[str] = []
    for name, decl in col_types:
        col_names.append(name)
        pg_type = _sqlite_type_to_pg(decl, name)
        # primary key heuristic
        if name == "idx":
            cols_sql.append(f"{_quote_ident(name)} BIGSERIAL PRIMARY KEY")
        else:
            cols_sql.append(f"{_quote_ident(name)} {pg_type}")
    ddl = (
        f"CREATE TABLE IF NOT EXISTS {_quote_ident(table)} (\n  "
        + ",\n  ".join(cols_sql)
        + "\n)"
    )
    pg_conn.execute(ddl)
    return col_names


def _truncate_table(pg_conn, table: str) -> None:
    pg_conn.execute(f"TRUNCATE TABLE {_quote_ident(table)} CASCADE")


def _insert_rows(
    pg_conn,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> int:
    if not rows:
        return 0
    # Only columns present in both plan and first row keys (intersection)
    usable = [c for c in columns if c in rows[0]]
    if not usable:
        # widen: use all keys from row that are in columns list if columns empty
        usable = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(usable))
    col_list = ", ".join(_quote_ident(c) for c in usable)
    sql = (
        f"INSERT INTO {_quote_ident(table)} ({col_list}) "
        f"VALUES ({placeholders})"
    )
    values = [tuple(row.get(c) for c in usable) for row in rows]
    if dry_run:
        return len(values)
    with pg_conn.cursor() as cur:
        cur.executemany(sql, values)
    return len(values)


def _reset_serial(pg_conn, table: str, pk: str = "idx") -> None:
    # Only if column exists and is numeric
    pg_conn.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', '{pk}'),
            COALESCE((SELECT MAX({_quote_ident(pk)}) FROM {_quote_ident(table)}), 1),
            true
        )
        """
    )


def _import_mynote_files(
    sqlite_conn: sqlite3.Connection,
    pg_conn: Any | None,
    *,
    project_root: Path,
    dry_run: bool,
) -> int:
    """Load file contents into mynote_contents when missing."""
    if "mynotes" not in set(_list_sqlite_tables(sqlite_conn)):
        return 0
    notes = _fetch_all_dicts(sqlite_conn, "mynotes")
    imported = 0
    for note in notes:
        idx = int(note["idx"])
        origin = str(note.get("origin_file") or "")
        path = Path(origin)
        if not path.is_absolute():
            path = project_root / path
        if not path.is_file():
            continue
        if dry_run:
            imported += 1
            continue
        if pg_conn is None:
            raise RuntimeError("pg_conn required when dry_run=False")
        content = path.read_text(encoding="utf-8")
        updated_at = str(note.get("last_update") or note.get("create_date") or "")
        pg_conn.execute(
            """
            INSERT INTO mynote_contents (note_idx, content, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (note_idx) DO UPDATE SET
                content = EXCLUDED.content,
                updated_at = EXCLUDED.updated_at
            """,
            (idx, content, updated_at),
        )
        imported += 1
    return imported


def validate_postgres_url(database_url: str) -> str:
    text = (database_url or "").strip()
    if not text:
        raise ValueError("PostgreSQL 접속 문자열이 비어 있습니다.")
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"postgres", "postgresql"}:
        raise ValueError("접속 문자열은 postgresql:// 또는 postgres:// 로 시작해야 합니다.")
    if not parsed.hostname:
        raise ValueError("접속 문자열에 호스트가 없습니다.")
    if not (parsed.path or "").strip("/"):
        raise ValueError("접속 문자열에 데이터베이스 이름(path)이 필요합니다. 예: .../axit")
    return text


def migrate(
    *,
    sqlite_path: Path,
    database_url: str,
    execute: bool,
    truncate_target: bool,
    apply_schema: bool,
    import_mynote_files: bool,
    include_inventory: bool,
    project_root: Path,
    schema_path: Path,
) -> int:
    """CLI-compatible entry. Returns 0 on success, 1 on failure."""
    result = run_migration(
        sqlite_path=sqlite_path,
        database_url=database_url,
        execute=execute,
        truncate_target=truncate_target,
        apply_schema=apply_schema,
        import_mynote_files=import_mynote_files,
        include_inventory=include_inventory,
        project_root=project_root,
        schema_path=schema_path,
    )
    print(result.log, end="" if result.log.endswith("\n") else "\n")
    if result.error:
        print(f"ERROR: {result.error}", flush=True)
    return 0 if result.ok else 1


def run_migration(
    *,
    sqlite_path: Path,
    database_url: str,
    execute: bool,
    truncate_target: bool,
    apply_schema: bool,
    import_mynote_files: bool,
    include_inventory: bool,
    project_root: Path,
    schema_path: Path,
) -> MigrationResult:
    dry_run = not execute
    database_url = validate_postgres_url(database_url)

    buf = io.StringIO()
    migratable = 0
    migrated = 0
    mynote_count = 0
    table_summaries: list[dict[str, Any]] = []

    try:
        with redirect_stdout(buf):
            sqlite_conn = _connect_sqlite(sqlite_path)
            try:
                plans = build_plans(sqlite_conn)
                print_plan(plans, sqlite_path=sqlite_path, database_url=database_url)
                migratable = sum(p.row_count for p in plans if p.kind != "skip")
                table_summaries = [
                    {
                        "sqlite_name": p.sqlite_name,
                        "postgres_name": p.postgres_name,
                        "kind": p.kind,
                        "row_count": p.row_count,
                        "notes": list(p.notes),
                    }
                    for p in plans
                ]

                if dry_run:
                    print("\n[dry-run] No writes performed. Re-run with execute=true to migrate.\n")
                    if import_mynote_files:
                        mynote_count = _import_mynote_files(
                            sqlite_conn, None, project_root=project_root, dry_run=True
                        )
                        print(
                            f"[dry-run] would import ~{mynote_count} mynote file(s) into mynote_contents"
                        )
                    return MigrationResult(
                        ok=True,
                        dry_run=True,
                        migratable_rows=migratable,
                        migrated_rows=0,
                        mynote_files=mynote_count,
                        log=buf.getvalue(),
                        tables=table_summaries,
                    )

                pg_conn = _pg_connect(database_url)
                try:
                    if apply_schema:
                        print(f"Applying schema: {schema_path}")
                        _ensure_core_schema(pg_conn, schema_path)

                    for plan in plans:
                        if plan.kind == "skip":
                            continue
                        if plan.kind == "inventory" and not include_inventory:
                            print(f"skip inventory (flag off): {plan.sqlite_name}")
                            continue

                        if plan.kind == "inventory":
                            cols = _create_inventory_table(
                                pg_conn, sqlite_conn, plan.sqlite_name
                            )
                        else:
                            cols = list(plan.columns)
                            if plan.postgres_name == "infra_cluster":
                                for extra in ("cron", "cron_expr", "infra_type"):
                                    if extra not in cols:
                                        cols.append(extra)

                        if truncate_target:
                            try:
                                _truncate_table(pg_conn, plan.postgres_name)
                                print(f"truncate {plan.postgres_name}")
                            except Exception as exc:
                                print(f"truncate skip {plan.postgres_name}: {exc}")
                                pg_conn.rollback()

                        rows = _fetch_all_dicts(sqlite_conn, plan.sqlite_name)
                        if plan.postgres_name == "infra_cluster":
                            rows = [_normalize_infra_cluster_row(r, cols) for r in rows]

                        n = _insert_rows(
                            pg_conn,
                            plan.postgres_name,
                            cols,
                            rows,
                            dry_run=False,
                        )
                        pg_conn.commit()
                        if plan.kind == "core" and "idx" in cols:
                            try:
                                _reset_serial(pg_conn, plan.postgres_name, "idx")
                                pg_conn.commit()
                            except Exception as exc:
                                print(f"serial reset skip {plan.postgres_name}: {exc}")
                                pg_conn.rollback()
                        print(f"inserted {n} → {plan.postgres_name}")
                        migrated += n

                    if import_mynote_files:
                        mynote_count = _import_mynote_files(
                            sqlite_conn,
                            pg_conn,
                            project_root=project_root,
                            dry_run=False,
                        )
                        pg_conn.commit()
                        print(f"imported mynote files → mynote_contents: {mynote_count}")

                    print(f"\nDone. Migrated row operations: {migrated}")
                finally:
                    pg_conn.close()
            finally:
                sqlite_conn.close()
    except Exception as exc:
        return MigrationResult(
            ok=False,
            dry_run=dry_run,
            migratable_rows=migratable,
            migrated_rows=migrated,
            mynote_files=mynote_count,
            log=buf.getvalue(),
            error=str(exc),
            tables=table_summaries,
        )

    return MigrationResult(
        ok=True,
        dry_run=False,
        migratable_rows=migratable,
        migrated_rows=migrated,
        mynote_files=mynote_count,
        log=buf.getvalue(),
        tables=table_summaries,
    )
