"""Admin API: SQLite → PostgreSQL migration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import PROJECT_ROOT, AppSettings
from backend.app.db.database import resolve_database_path
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.sqlite_pg_migrate import run_migration, validate_postgres_url

router = APIRouter(tags=["admin-migrate"])

SCHEMA_PATH = PROJECT_ROOT / "backend" / "app" / "db" / "schema.postgres.sql"


class MigrateSqliteToPostgresRequest(BaseModel):
    database_url: str = Field(min_length=1, description="postgresql://user:pass@host:port/db")
    execute: bool = False
    truncate_target: bool = True
    apply_schema: bool = True
    import_mynote_files: bool = True
    include_inventory: bool = True
    sqlite_path: str | None = None


class MigrateSqliteToPostgresResponse(BaseModel):
    ok: bool
    dry_run: bool
    migratable_rows: int
    migrated_rows: int
    mynote_files: int
    log: str
    error: str | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


@router.post(
    "/admin/migrate-sqlite-to-postgres",
    response_model=MigrateSqliteToPostgresResponse,
)
async def migrate_sqlite_to_postgres(
    payload: MigrateSqliteToPostgresRequest,
    request: Request,
) -> MigrateSqliteToPostgresResponse:
    _require_admin(request)

    try:
        database_url = validate_postgres_url(payload.database_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = AppSettings()
    raw_sqlite = payload.sqlite_path or settings.database_path or "data/app.db"
    sqlite_path = resolve_database_path(raw_sqlite)
    if not sqlite_path.is_absolute():
        sqlite_path = PROJECT_ROOT / sqlite_path

    if not sqlite_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"SQLite 파일을 찾을 수 없습니다: {sqlite_path}",
        )

    result = run_migration(
        sqlite_path=sqlite_path,
        database_url=database_url,
        execute=bool(payload.execute),
        truncate_target=bool(payload.truncate_target),
        apply_schema=bool(payload.apply_schema),
        import_mynote_files=bool(payload.import_mynote_files),
        include_inventory=bool(payload.include_inventory),
        project_root=PROJECT_ROOT,
        schema_path=SCHEMA_PATH,
    )

    return MigrateSqliteToPostgresResponse(
        ok=result.ok,
        dry_run=result.dry_run,
        migratable_rows=result.migratable_rows,
        migrated_rows=result.migrated_rows,
        mynote_files=result.mynote_files,
        log=result.log,
        error=result.error,
        tables=result.tables,
    )
