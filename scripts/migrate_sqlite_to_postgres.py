#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "psycopg[binary]>=3.2.0",
# ]
# ///
"""CLI wrapper for SQLite → PostgreSQL migration.

구현은 ``backend.app.services.sqlite_pg_migrate`` 에 있으며,
관리자 UI(환경설정 > 관리자 작업)에서도 동일 로직을 호출합니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `uv run scripts/...` without installing the package on PYTHONPATH.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.app.services.sqlite_pg_migrate import migrate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    root = _ROOT
    parser = argparse.ArgumentParser(
        description="Migrate AX Platform SQLite data to PostgreSQL (dry-run by default)."
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=root / "data" / "app.db",
        help="Source SQLite path (default: data/app.db)",
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="Target PostgreSQL URL, e.g. postgresql://user:pass@host:5432/db",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write to PostgreSQL (default is dry-run)",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="TRUNCATE each target table before insert (CASCADE)",
    )
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Apply backend/app/db/schema.postgres.sql before insert",
    )
    parser.add_argument(
        "--no-inventory",
        action="store_true",
        help="Skip dynamic {cluster}_k8s_* / kubevirt_* tables",
    )
    parser.add_argument(
        "--import-mynote-files",
        action="store_true",
        help="Copy data/mynotes files into mynote_contents",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=root / "backend" / "app" / "db" / "schema.postgres.sql",
        help="Postgres schema SQL path",
    )
    args = parser.parse_args(argv)

    try:
        return migrate(
            sqlite_path=args.sqlite.resolve(),
            database_url=args.database_url,
            execute=bool(args.execute),
            truncate_target=bool(args.truncate_target),
            apply_schema=bool(args.apply_schema),
            import_mynote_files=bool(args.import_mynote_files),
            include_inventory=not bool(args.no_inventory),
            project_root=root,
            schema_path=args.schema.resolve(),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
