"""Inventory management APIs — proxy to remote inventory-api service."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.db.inventory import (
    assert_csv_columns_compatible,
    preview_inventory_csv,
    rewrite_csv_with_normalized_headers,
    save_inventory_csv,
    temp_table_name_for,
    validate_inventory_table_name,
    validate_preview_table_name,
)
from backend.app.db.roles import is_admin_role
from backend.app.db.users import get_user_by_idx
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.inventory_external import (
    InventoryExternalApiError,
    InventoryExternalUploadError,
    add_external_inventory,
    add_external_inventory_api,
    execute_external_inventory_api,
    get_external_inventory_count,
    get_external_inventory_schema,
    list_external_inventories,
    list_external_inventory_apis,
    preview_external_inventory_table,
    reload_external_inventory_api,
    remove_external_inventory,
    remove_external_inventory_api,
    remove_external_temp_table,
    retrieve_origin_api_via_inventory_api,
    test_origin_api_via_inventory_api,
    transfer_csv_to_external_table,
    transfer_json_to_external_table,
    update_external_inventory_api,
    upload_csv_to_external_inventory_api,
    validate_origin_api_key_format,
)
from backend.app.services.inventory_temp_session import (
    clear_inventory_temp_tables,
    register_inventory_temp_table,
    unregister_inventory_temp_table,
)

router = APIRouter(tags=["inventory"])
logger = logging.getLogger(__name__)


class InventoryResponse(BaseModel):
    idx: int = 0
    table_name: str = ""
    display_name: str = ""
    description: str = ""
    created_by: int = 0
    created_by_username: str = ""
    origin_csv: str = ""
    created_at: str = ""
    origin_type: int = 1
    origin_api_url: str = ""
    origin_api_auth_type: int = 1
    has_api_key: bool = False
    is_scheduled: bool = False
    api_crawling_cron: str = ""


class InventoryStatsRow(BaseModel):
    table_name: str
    display_name: str = ""
    description: str = ""
    origin_csv: str = ""
    created_at: str = ""
    created_by: int = 0
    created_by_username: str = ""
    row_count: int = 0
    column_count: int = 0
    error: str | None = None
    origin_type: int = 1
    origin_api_url: str = ""
    origin_api_auth_type: int = 1
    has_api_key: bool = False
    is_scheduled: bool = False
    api_crawling_cron: str = ""


class InventoryApiStatsRow(BaseModel):
    """Flattened inventory-api registry row for the idle dashboard."""

    api_name: str
    table_name: str = ""
    display_name: str = ""
    api_fullpath: str = ""
    created_by: int = 0
    created_by_username: str = ""
    description: str = ""
    error: str | None = None


class InventoryCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)
    origin_csv: str | None = Field(default=None, max_length=100)
    table_name: str = Field(min_length=1, max_length=50)
    temp_table_name: str | None = Field(default=None, max_length=50)
    origin_type: int = Field(default=1)
    origin_api_url: str | None = Field(default=None, max_length=500)
    origin_api_key: str | None = Field(default=None, max_length=500)
    origin_api_auth_type: int = Field(default=1)
    is_scheduled: bool = False
    api_crawling_cron: str | None = Field(default=None, max_length=100)
    # Transfer filename after CSV upload (origin_type=1).
    transfer_filename: str | None = Field(default=None, max_length=100)
    # JSON payload from apicall/retrieve (origin_type=2 save via transferJSON2Table).
    response_json: Any | None = None

    @field_validator("origin_type")
    @classmethod
    def _origin_type_ok(cls, value: int) -> int:
        if value not in (1, 2):
            raise ValueError("origin_type은 1(csv) 또는 2(api)여야 합니다.")
        return value

    @model_validator(mode="after")
    def _validate_origin_fields(self) -> InventoryCreateRequest:
        if self.origin_type == 1:
            if not (self.origin_csv or "").strip():
                raise ValueError("origin_type=1 에는 origin_csv가 필요합니다.")
            if self.is_scheduled:
                raise ValueError("is_scheduled는 origin_type=2 에서만 허용됩니다.")
        else:
            url = (self.origin_api_url or "").strip()
            if not url:
                raise ValueError("origin_type=2 에는 origin_api_url이 필요합니다.")
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError("invalid_api_url")
            try:
                validate_origin_api_key_format(self.origin_api_auth_type, self.origin_api_key)
            except InventoryExternalApiError as exc:
                raise ValueError(str(exc)) from exc
            if self.is_scheduled and not (self.api_crawling_cron or "").strip():
                raise ValueError("is_scheduled=true 에는 api_crawling_cron이 필요합니다.")
            if self.is_scheduled:
                _validate_inventory_cron(self.api_crawling_cron or "")
        return self


class InventoryUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)
    origin_csv: str | None = Field(default=None, max_length=100)
    temp_table_name: str | None = Field(default=None, max_length=50)
    origin_type: int | None = Field(default=None)
    origin_api_url: str | None = Field(default=None, max_length=500)
    origin_api_key: str | None = Field(default=None, max_length=500)
    origin_api_auth_type: int | None = Field(default=None)
    is_scheduled: bool | None = None
    api_crawling_cron: str | None = Field(default=None, max_length=100)
    transfer_filename: str | None = Field(default=None, max_length=100)
    response_json: Any | None = None


class InventoryApiCallRetrieveRequest(BaseModel):
    table_name: str = Field(min_length=1, max_length=50)
    api_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    auth_type: int = Field(default=1)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("api_url")
    @classmethod
    def _api_url_ok(cls, value: str) -> str:
        text = (value or "").strip()
        if not text.lower().startswith(("http://", "https://")):
            raise ValueError("invalid_api_url")
        return text

    @model_validator(mode="after")
    def _auth_ok(self) -> InventoryApiCallRetrieveRequest:
        try:
            validate_origin_api_key_format(self.auth_type, self.api_key)
        except InventoryExternalApiError as exc:
            raise ValueError(str(exc)) from exc
        return self


class InventoryApiCallTestRequest(BaseModel):
    api_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    auth_type: int = Field(default=1)

    @field_validator("api_url")
    @classmethod
    def _api_url_ok(cls, value: str) -> str:
        text = (value or "").strip()
        if not text.lower().startswith(("http://", "https://")):
            raise ValueError("invalid_api_url")
        return text

    @model_validator(mode="after")
    def _auth_ok(self) -> InventoryApiCallTestRequest:
        try:
            validate_origin_api_key_format(self.auth_type, self.api_key)
        except InventoryExternalApiError as exc:
            raise ValueError(str(exc)) from exc
        return self


class InventoryApiCallTestResponse(BaseModel):
    url: str = ""
    ok: bool = False
    status_code: int | None = None
    elapsed_ms: int | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    is_json: bool | None = None
    row_count: int | None = None
    columns: list[str] = Field(default_factory=list)
    error: str | None = None
    message: str | None = None


def _validate_inventory_cron(cron_expr: str) -> str:
    text = (cron_expr or "").strip()
    if not text:
        raise ValueError("invalid_cron")
    if len(text) > 100:
        raise ValueError("invalid_cron")
    if len(text.split()) != 5:
        raise ValueError("invalid_cron")
    try:
        from croniter import croniter

        if not croniter.is_valid(text):
            raise ValueError("invalid_cron")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("invalid_cron") from exc
    return text


class InventoryCsvPreviewResponse(BaseModel):
    filename: str = ""
    table_name: str = ""
    temp_table_name: str = ""
    columns: list[str]
    labels: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]]
    offset: int = 0
    limit: int = 50
    startrow: int = 1
    endrow: int = 50
    total_rows: int = 0
    has_more: bool = False
    columns_compatible: bool | None = None
    compatibility_error: str | None = None
    transfer_ok: bool | None = None
    transfer_result: dict[str, object] | None = None
    response_json: Any | None = None


class InventoryTablePreviewResponse(BaseModel):
    table_name: str
    columns: list[str]
    labels: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]]
    startrow: int = 1
    endrow: int = 50
    total_rows: int = 0
    has_more: bool = False


class InventoryApiResponse(BaseModel):
    idx: int = 0
    api_name: str
    display_name: str = ""
    description: str = ""
    api_fullpath: str = ""
    created_by: int = 0
    created_by_username: str = ""
    table_name: str = ""
    where_exp: str = ""
    select_exp: str = ""
    param_columns: str = ""


class InventoryApiCreateRequest(BaseModel):
    api_name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)
    where_exp: str = Field(min_length=1, max_length=500)
    select_exp: str = Field(min_length=1, max_length=500)
    param_columns: str = Field(default="", max_length=500)


class InventoryApiUpdateRequest(BaseModel):
    api_name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)
    where_exp: str = Field(min_length=1, max_length=500)
    select_exp: str = Field(min_length=1, max_length=500)
    param_columns: str = Field(default="", max_length=500)


def _created_at_from_row(row: dict[str, Any]) -> str:
    for key in (
        "created_at",
        "created_date",
        "registered_date",
        "registered_at",
        "create_date",
        "created",
    ):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _column_names_from_schema(schema: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    raw = schema.get("columns")
    if not isinstance(raw, list):
        return columns
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("column") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name not in columns:
            columns.append(name)
    return columns


def _username_for(database_path: str, created_by: int | None) -> str:
    if not created_by:
        return ""
    user = get_user_by_idx(database_path, int(created_by))
    if user is None:
        return ""
    return (user.username or user.userid or "").strip()


def _origin_fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_type = row.get("origin_type")
    try:
        origin_type = int(raw_type) if raw_type is not None else 1
    except (TypeError, ValueError):
        origin_type = 1
    if origin_type not in (1, 2):
        origin_type = 1
    has_key = row.get("has_api_key")
    if has_key is None:
        has_key = bool(str(row.get("origin_api_key") or "").strip())
    raw_auth = row.get("origin_api_auth_type")
    try:
        auth_type = int(raw_auth) if raw_auth is not None else 1
    except (TypeError, ValueError):
        auth_type = 1
    if auth_type not in (1, 2):
        auth_type = 1
    return {
        "origin_type": origin_type,
        "origin_api_url": str(row.get("origin_api_url") or ""),
        "origin_api_auth_type": auth_type,
        "has_api_key": bool(has_key),
        "is_scheduled": bool(row.get("is_scheduled")),
        "api_crawling_cron": str(row.get("api_crawling_cron") or ""),
    }


def _to_inventory_response(row: dict[str, Any], *, database_path: str) -> InventoryResponse:
    created_by = int(row.get("created_by") or 0)
    return InventoryResponse(
        idx=int(row.get("idx") or 0),
        table_name=str(row.get("table_name") or ""),
        display_name=str(row.get("display_name") or row.get("table_name") or ""),
        description=str(row.get("description") or ""),
        created_by=created_by,
        created_by_username=_username_for(database_path, created_by),
        origin_csv=str(row.get("origin_csv") or ""),
        created_at=_created_at_from_row(row),
        **_origin_fields_from_row(row),
    )


def _api_fullpath(table_name: str, api_name: str, raw: object = None) -> str:
    text = str(raw or "").strip()
    if text:
        return text
    return f"/inv/{table_name}/{api_name}"


def _to_api_response(
    row: dict[str, Any],
    *,
    table_name: str,
    database_path: str,
    index: int = 0,
) -> InventoryApiResponse:
    api_name = str(row.get("api_name") or "")
    created_by = int(row.get("created_by") or 0)
    resolved_table = str(row.get("table_name") or table_name)
    return InventoryApiResponse(
        idx=int(row.get("idx") or index),
        api_name=api_name,
        display_name=str(row.get("display_name") or api_name),
        description=str(row.get("description") or ""),
        api_fullpath=_api_fullpath(resolved_table, api_name, row.get("api_fullpath")),
        created_by=created_by,
        created_by_username=_username_for(database_path, created_by),
        table_name=resolved_table,
        where_exp=str(row.get("where_exp") or ""),
        select_exp=str(row.get("select_exp") or ""),
        param_columns=str(row.get("param_columns") or row.get("input_columns") or ""),
    )


def _can_edit_created_by(created_by: int, auth_user) -> bool:
    return int(created_by) == int(auth_user.idx) or is_admin_role(int(auth_user.role))


def _session_token(request: Request) -> str | None:
    return getattr(request.state, "auth_token", None)


async def _cleanup_temp(token: str | None, temp_table: str | None) -> None:
    name = (temp_table or "").strip()
    if not name:
        return
    try:
        await remove_external_temp_table(name)
    except InventoryExternalApiError as exc:
        logger.warning("removeTempTable failed table=%s err=%s", name, exc)
    if token:
        await unregister_inventory_temp_table(token, name)


@router.get("/inventories", response_model=list[InventoryResponse])
async def api_list_inventories(request: Request) -> list[InventoryResponse]:
    get_request_auth_user(request)
    try:
        rows = await list_external_inventories()
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    database_path = request.app.state.database_path
    return [_to_inventory_response(row, database_path=database_path) for row in rows]


@router.get("/inventories/stats", response_model=list[InventoryStatsRow])
async def api_inventory_stats(request: Request) -> list[InventoryStatsRow]:
    """Overview stats for the idle inventory dashboard (list + count + schema)."""
    get_request_auth_user(request)
    try:
        rows = await list_external_inventories()
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    database_path = request.app.state.database_path
    base_items = [_to_inventory_response(row, database_path=database_path) for row in rows]

    async def _one(item: InventoryResponse) -> InventoryStatsRow:
        table = (item.table_name or "").strip()
        if not table:
            return InventoryStatsRow(
                table_name="",
                display_name=item.display_name,
                description=item.description,
                origin_csv=item.origin_csv,
                created_at=item.created_at,
                created_by=item.created_by,
                created_by_username=item.created_by_username,
                origin_type=item.origin_type,
                origin_api_url=item.origin_api_url,
                origin_api_auth_type=item.origin_api_auth_type,
                has_api_key=item.has_api_key,
                is_scheduled=item.is_scheduled,
                api_crawling_cron=item.api_crawling_cron,
                error="table_name 없음",
            )
        try:
            count_task = get_external_inventory_count(table)
            schema_task = get_external_inventory_schema(table)
            row_count, schema = await asyncio.gather(count_task, schema_task)
            columns = _column_names_from_schema(schema)
            return InventoryStatsRow(
                table_name=table,
                display_name=item.display_name or table,
                description=item.description,
                origin_csv=item.origin_csv,
                created_at=item.created_at,
                created_by=item.created_by,
                created_by_username=item.created_by_username,
                row_count=int(row_count),
                column_count=len(columns),
                origin_type=item.origin_type,
                origin_api_url=item.origin_api_url,
                origin_api_auth_type=item.origin_api_auth_type,
                has_api_key=item.has_api_key,
                is_scheduled=item.is_scheduled,
                api_crawling_cron=item.api_crawling_cron,
            )
        except InventoryExternalApiError as exc:
            logger.warning("inventory stats failed table=%s err=%s", table, exc)
            return InventoryStatsRow(
                table_name=table,
                display_name=item.display_name or table,
                description=item.description,
                origin_csv=item.origin_csv,
                created_at=item.created_at,
                created_by=item.created_by,
                created_by_username=item.created_by_username,
                origin_type=item.origin_type,
                origin_api_url=item.origin_api_url,
                origin_api_auth_type=item.origin_api_auth_type,
                has_api_key=item.has_api_key,
                is_scheduled=item.is_scheduled,
                api_crawling_cron=item.api_crawling_cron,
                error=str(exc),
            )

    return list(await asyncio.gather(*[_one(item) for item in base_items]))


@router.get("/inventories/api-stats", response_model=list[InventoryApiStatsRow])
async def api_inventory_api_stats(request: Request) -> list[InventoryApiStatsRow]:
    """Flattened API registry across all inventory tables for the idle dashboard."""
    get_request_auth_user(request)
    try:
        inventory_rows = await list_external_inventories()
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    database_path = request.app.state.database_path
    tables: list[str] = []
    seen: set[str] = set()
    for row in inventory_rows:
        table = str(row.get("table_name") or "").strip()
        if table and table not in seen:
            seen.add(table)
            tables.append(table)

    async def _apis_for_table(table: str) -> list[InventoryApiStatsRow]:
        try:
            rows = await list_external_inventory_apis(table)
        except InventoryExternalApiError as exc:
            logger.warning("inventory api-stats failed table=%s err=%s", table, exc)
            return [
                InventoryApiStatsRow(
                    api_name="",
                    table_name=table,
                    error=str(exc),
                )
            ]
        result: list[InventoryApiStatsRow] = []
        for index, row in enumerate(rows):
            mapped = _to_api_response(
                row,
                table_name=table,
                database_path=database_path,
                index=index + 1,
            )
            result.append(
                InventoryApiStatsRow(
                    api_name=mapped.api_name,
                    table_name=mapped.table_name or table,
                    display_name=mapped.display_name,
                    api_fullpath=mapped.api_fullpath,
                    created_by=mapped.created_by,
                    created_by_username=mapped.created_by_username,
                    description=mapped.description,
                )
            )
        return result

    if not tables:
        return []

    nested = await asyncio.gather(*[_apis_for_table(table) for table in tables])
    flattened: list[InventoryApiStatsRow] = []
    for group in nested:
        flattened.extend(group)
    flattened.sort(key=lambda item: (item.table_name, item.api_name))
    return flattened


@router.post("/inventories/csv/upload", response_model=InventoryCsvPreviewResponse)
async def api_upload_inventory_csv(
    request: Request,
    file: UploadFile = File(...),
    compare_to_table: str | None = Query(default=None),
    table_name: str | None = Query(default=None),
    display_name: str | None = Query(default=None),
    description: str | None = Query(default=None),
) -> InventoryCsvPreviewResponse:
    auth_user = get_request_auth_user(request)
    token = _session_token(request)
    raw_name = (file.filename or "upload.csv").strip()
    if not raw_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    try:
        table = validate_inventory_table_name(table_name or "")
        temp_table = temp_table_name_for(table)
        normalized_content, columns, _labels = rewrite_csv_with_normalized_headers(content)
        stem = Path(raw_name).stem
        unique_name = f"{stem}_{uuid.uuid4().hex[:10]}.csv"
        remote = await upload_csv_to_external_inventory_api(
            normalized_content,
            filename=unique_name,
        )
        remote_filename = str(remote.get("filename") or unique_name)
        transfer_result = await transfer_csv_to_external_table(
            filename=remote_filename,
            tablename=temp_table,
            display_name=(display_name or "").strip() or None,
            description=(description or "").strip() or None,
            created_by=int(auth_user.idx),
        )
        if token:
            await register_inventory_temp_table(token, temp_table)
        stored = save_inventory_csv(
            normalized_content,
            original_filename=raw_name,
            stored_filename=remote_filename,
        )
        local_preview = preview_inventory_csv(stored, offset=0, limit=50)
        try:
            remote_preview = await preview_external_inventory_table(
                temp_table, startrow=1, endrow=50
            )
        except InventoryExternalApiError as exc:
            logger.warning(
                "remote inventory preview failed after temp transfer table=%s err=%s",
                temp_table,
                exc,
            )
            remote_preview = None
    except InventoryExternalUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    columns_compatible: bool | None = None
    compatibility_error: str | None = None
    baseline_table = (compare_to_table or "").strip()
    if baseline_table:
        try:
            schema = await get_external_inventory_schema(baseline_table)
            expected = []
            raw_cols = schema.get("columns")
            if isinstance(raw_cols, list):
                for item in raw_cols:
                    if isinstance(item, dict):
                        name = str(item.get("name") or "").strip()
                    else:
                        name = str(item or "").strip()
                    if name:
                        expected.append(name)
            assert_csv_columns_compatible(expected, columns)
            columns_compatible = True
        except (InventoryExternalApiError, ValueError) as exc:
            columns_compatible = False
            compatibility_error = str(exc)

    if remote_preview is not None:
        return InventoryCsvPreviewResponse(
            filename=remote_filename,
            table_name=table,
            temp_table_name=temp_table,
            columns=list(remote_preview["columns"]),  # type: ignore[arg-type]
            labels=list(remote_preview.get("labels") or remote_preview["columns"]),  # type: ignore[arg-type]
            rows=list(remote_preview["rows"]),  # type: ignore[arg-type]
            offset=0,
            limit=50,
            startrow=int(remote_preview.get("startrow") or 1),
            endrow=int(remote_preview.get("endrow") or 50),
            total_rows=int(remote_preview.get("total_rows") or 0),
            has_more=bool(remote_preview.get("has_more")),
            columns_compatible=columns_compatible,
            compatibility_error=compatibility_error,
            transfer_ok=True,
            transfer_result=transfer_result,
        )

    return InventoryCsvPreviewResponse(
        **local_preview,
        table_name=table,
        temp_table_name=temp_table,
        startrow=1,
        endrow=min(50, int(local_preview.get("total_rows") or 0) or 50),
        columns_compatible=columns_compatible,
        compatibility_error=compatibility_error,
        transfer_ok=True,
        transfer_result=transfer_result,
    )


@router.get(
    "/inventories/tables/{table_name}/preview",
    response_model=InventoryTablePreviewResponse,
)
async def api_preview_inventory_table(
    table_name: str,
    request: Request,
    startrow: int = Query(default=1, ge=1),
    endrow: int = Query(default=50, ge=1),
) -> InventoryTablePreviewResponse:
    get_request_auth_user(request)
    if endrow < startrow:
        raise HTTPException(status_code=400, detail="endrow는 startrow 이상이어야 합니다.")
    if endrow - startrow + 1 > 500:
        raise HTTPException(status_code=400, detail="한 번에 최대 500행까지 조회할 수 있습니다.")
    try:
        table = validate_preview_table_name(table_name)
        preview = await preview_external_inventory_table(
            table, startrow=startrow, endrow=endrow
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InventoryTablePreviewResponse(
        table_name=str(preview["table_name"]),
        columns=list(preview["columns"]),  # type: ignore[arg-type]
        labels=list(preview.get("labels") or preview["columns"]),  # type: ignore[arg-type]
        rows=list(preview["rows"]),  # type: ignore[arg-type]
        startrow=int(preview.get("startrow") or startrow),
        endrow=int(preview.get("endrow") or endrow),
        total_rows=int(preview.get("total_rows") or 0),
        has_more=bool(preview.get("has_more")),
    )


@router.post("/inventories/temp/cleanup")
async def api_cleanup_inventory_temps(
    request: Request,
    tablename: str | None = Query(default=None),
) -> dict[str, object]:
    """Remove session-tracked temp tables (page leave / explicit cleanup)."""
    get_request_auth_user(request)
    token = _session_token(request)
    removed: list[str] = []
    explicit = (tablename or "").strip()
    if explicit:
        await _cleanup_temp(token, explicit)
        removed.append(explicit)
        return {"ok": True, "removed": removed}

    if not token:
        return {"ok": True, "removed": removed}
    for name in await clear_inventory_temp_tables(token):
        try:
            await remove_external_temp_table(name)
            removed.append(name)
        except InventoryExternalApiError as exc:
            logger.warning("removeTempTable failed table=%s err=%s", name, exc)
    return {"ok": True, "removed": removed}


@router.post("/inventories/apicall/test", response_model=InventoryApiCallTestResponse)
async def api_test_inventory_origin_api(
    body: InventoryApiCallTestRequest,
    request: Request,
) -> InventoryApiCallTestResponse:
    """Probe origin API via inventory-api ``/testAPI`` (no DB mutation)."""
    get_request_auth_user(request)
    try:
        payload = await test_origin_api_via_inventory_api(
            api_url=body.api_url,
            api_key=body.api_key,
            auth_type=body.auth_type,
        )
    except InventoryExternalApiError as exc:
        detail = str(exc)
        status = 400 if detail in {"invalid_api_url", "invalid_api_auth"} else 502
        raise HTTPException(status_code=status, detail=detail) from exc

    columns_raw = payload.get("columns")
    columns = (
        [str(item) for item in columns_raw if str(item).strip()]
        if isinstance(columns_raw, list)
        else []
    )
    status_raw = payload.get("status_code")
    try:
        status_code = int(status_raw) if status_raw is not None else None
    except (TypeError, ValueError):
        status_code = None
    elapsed_raw = payload.get("elapsed_ms")
    try:
        elapsed_ms = int(elapsed_raw) if elapsed_raw is not None else None
    except (TypeError, ValueError):
        elapsed_ms = None
    size_raw = payload.get("size_bytes")
    try:
        size_bytes = int(size_raw) if size_raw is not None else None
    except (TypeError, ValueError):
        size_bytes = None
    row_raw = payload.get("row_count")
    try:
        row_count = int(row_raw) if row_raw is not None else None
    except (TypeError, ValueError):
        row_count = None

    return InventoryApiCallTestResponse(
        url=str(payload.get("url") or body.api_url),
        ok=bool(payload.get("ok")),
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        content_type=(str(payload.get("content_type")) if payload.get("content_type") is not None else None),
        size_bytes=size_bytes,
        is_json=bool(payload["is_json"]) if payload.get("is_json") is not None else None,
        row_count=row_count,
        columns=columns,
        error=(str(payload.get("error")) if payload.get("error") is not None else None),
        message=(str(payload.get("message")) if payload.get("message") is not None else None),
    )


@router.post("/inventories/apicall/retrieve", response_model=InventoryCsvPreviewResponse)
async def api_retrieve_inventory_from_api(
    body: InventoryApiCallRetrieveRequest,
    request: Request,
) -> InventoryCsvPreviewResponse:
    """Delegate to inventory-api ``/retrieve`` + ``/transferJSON2Table``, return preview."""
    get_request_auth_user(request)
    token = _session_token(request)
    try:
        table = validate_inventory_table_name(body.table_name)
        temp_table = temp_table_name_for(table)
        retrieved = await retrieve_origin_api_via_inventory_api(
            api_url=body.api_url,
            api_key=body.api_key,
            auth_type=body.auth_type,
        )
        response_json = retrieved.get("response_json")
        transfer_result = await transfer_json_to_external_table(
            response_json=response_json,
            tablename=temp_table,
        )
        if token:
            await register_inventory_temp_table(token, temp_table)
        remote_preview = await preview_external_inventory_table(
            temp_table, startrow=1, endrow=50
        )
    except InventoryExternalUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except InventoryExternalApiError as exc:
        detail = str(exc)
        if detail in {"invalid_api_url", "invalid_api_auth", "invalid_json"}:
            status = 400
        elif detail == "retrieve_failed":
            status = 502
        else:
            status = 502
        raise HTTPException(status_code=status, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return InventoryCsvPreviewResponse(
        filename="",
        table_name=table,
        temp_table_name=temp_table,
        columns=list(remote_preview["columns"]),  # type: ignore[arg-type]
        labels=list(remote_preview.get("labels") or remote_preview["columns"]),  # type: ignore[arg-type]
        rows=list(remote_preview["rows"]),  # type: ignore[arg-type]
        offset=0,
        limit=50,
        startrow=int(remote_preview.get("startrow") or 1),
        endrow=int(remote_preview.get("endrow") or 50),
        total_rows=int(remote_preview.get("total_rows") or 0),
        has_more=bool(remote_preview.get("has_more")),
        transfer_ok=True,
        transfer_result=transfer_result if isinstance(transfer_result, dict) else None,
        response_json=response_json,
    )


@router.post("/inventories", response_model=InventoryResponse, status_code=201)
async def api_create_inventory(
    body: InventoryCreateRequest,
    request: Request,
) -> InventoryResponse:
    auth_user = get_request_auth_user(request)
    token = _session_token(request)
    try:
        table = validate_inventory_table_name(body.table_name)
        temp_table = (body.temp_table_name or "").strip() or temp_table_name_for(table)
        if body.origin_type == 2:
            if body.response_json is None:
                raise ValueError("API 조회 결과가 없습니다. API 조회를 먼저 수행하세요.")
            await transfer_json_to_external_table(
                response_json=body.response_json,
                tablename=table,
            )
        else:
            transfer_name = (
                (body.transfer_filename or "").strip()
                or (body.origin_csv or "").strip()
            )
            if not transfer_name:
                raise ValueError("테이블 전환용 파일명이 없습니다. CSV를 먼저 업로드하세요.")
            await transfer_csv_to_external_table(
                filename=transfer_name,
                tablename=table,
                display_name=body.display_name.strip(),
                description=body.description.strip(),
                created_by=int(auth_user.idx),
            )
        created = await add_external_inventory(
            table_name=table,
            origin_csv=(body.origin_csv or "").strip() or None,
            display_name=body.display_name.strip(),
            description=body.description.strip(),
            created_by=int(auth_user.idx),
            origin_type=body.origin_type,
            origin_api_url=(body.origin_api_url or "").strip() or None,
            origin_api_key=body.origin_api_key,
            origin_api_auth_type=body.origin_api_auth_type,
            is_scheduled=body.is_scheduled,
            api_crawling_cron=(body.api_crawling_cron or "").strip() or None,
        )
        await _cleanup_temp(token, temp_table)
    except InventoryExternalUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except InventoryExternalApiError as exc:
        detail = str(exc)
        status = 400 if detail in {"invalid_api_url", "invalid_api_auth"} else 502
        raise HTTPException(status_code=status, detail=detail) from exc
    except ValueError as exc:
        detail = str(exc)
        status = 400
        if detail in {"invalid_api_url", "invalid_api_auth", "invalid_cron"}:
            status = 400
        elif detail.startswith("origin_type") or "is_scheduled" in detail:
            status = 422
        raise HTTPException(status_code=status, detail=detail) from exc

    if isinstance(created, dict) and created.get("table_name"):
        return _to_inventory_response(created, database_path=request.app.state.database_path)
    return InventoryResponse(
        table_name=table,
        display_name=body.display_name.strip(),
        description=body.description.strip(),
        created_by=int(auth_user.idx),
        created_by_username=_username_for(request.app.state.database_path, int(auth_user.idx)),
        origin_csv=(body.origin_csv or "").strip() if body.origin_type == 1 else "",
        origin_type=body.origin_type,
        origin_api_url=(body.origin_api_url or "").strip() if body.origin_type == 2 else "",
        origin_api_auth_type=body.origin_api_auth_type if body.origin_type == 2 else 1,
        has_api_key=bool((body.origin_api_key or "").strip()) if body.origin_type == 2 else False,
        is_scheduled=bool(body.is_scheduled) if body.origin_type == 2 else False,
        api_crawling_cron=(body.api_crawling_cron or "").strip() if body.origin_type == 2 else "",
    )


@router.put("/inventories/{table_name}", response_model=InventoryResponse)
async def api_update_inventory(
    table_name: str,
    body: InventoryUpdateRequest,
    request: Request,
) -> InventoryResponse:
    auth_user = get_request_auth_user(request)
    token = _session_token(request)
    try:
        table = validate_inventory_table_name(table_name)
        origin = (body.origin_csv or body.transfer_filename or "").strip()
        temp_table = (body.temp_table_name or "").strip()
        origin_type = int(body.origin_type) if body.origin_type is not None else (
            2 if (body.origin_api_url or "").strip() else 1
        )
        if origin_type == 2 and body.response_json is not None:
            await transfer_json_to_external_table(
                response_json=body.response_json,
                tablename=table,
            )
            if temp_table:
                await _cleanup_temp(token, temp_table)
        elif temp_table and origin:
            await transfer_csv_to_external_table(
                filename=origin,
                tablename=table,
                display_name=body.display_name.strip(),
                description=body.description.strip(),
                created_by=int(auth_user.idx),
            )
            await _cleanup_temp(token, temp_table)
        # Remote API has no updateInventory; re-register metadata when origin is known.
        if origin or origin_type == 2:
            await add_external_inventory(
                table_name=table,
                origin_csv=(body.origin_csv or "").strip() or None,
                display_name=body.display_name.strip(),
                description=body.description.strip(),
                created_by=int(auth_user.idx),
                origin_type=origin_type,
                origin_api_url=(body.origin_api_url or "").strip() or None,
                origin_api_key=body.origin_api_key,
                origin_api_auth_type=body.origin_api_auth_type,
                is_scheduled=body.is_scheduled,
                api_crawling_cron=(body.api_crawling_cron or "").strip() or None,
            )
    except InventoryExternalUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except InventoryExternalApiError as exc:
        detail = str(exc)
        status = 400 if detail in {"invalid_api_url", "invalid_api_auth"} else 502
        raise HTTPException(status_code=status, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return InventoryResponse(
        table_name=table,
        display_name=body.display_name.strip(),
        description=body.description.strip(),
        created_by=int(auth_user.idx),
        created_by_username=_username_for(request.app.state.database_path, int(auth_user.idx)),
        origin_csv=(body.origin_csv or "").strip(),
        origin_type=int(body.origin_type) if body.origin_type is not None else 1,
        origin_api_url=(body.origin_api_url or "").strip(),
        origin_api_auth_type=int(body.origin_api_auth_type)
        if body.origin_api_auth_type is not None
        else 1,
        has_api_key=bool((body.origin_api_key or "").strip()),
        is_scheduled=bool(body.is_scheduled),
        api_crawling_cron=(body.api_crawling_cron or "").strip(),
    )


@router.delete("/inventories/{table_name}")
async def api_delete_inventory(table_name: str, request: Request) -> dict[str, object]:
    auth_user = get_request_auth_user(request)
    try:
        table = validate_inventory_table_name(table_name)
        rows = await list_external_inventories()
        target = next((row for row in rows if str(row.get("table_name") or "") == table), None)
        if target is None:
            raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
        created_by = int(target.get("created_by") or 0)
        if created_by and not _can_edit_created_by(created_by, auth_user):
            raise HTTPException(status_code=403, detail="이 인벤토리를 삭제할 권한이 없습니다.")
        await remove_external_inventory(table)
    except HTTPException:
        raise
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "table_name": table}


@router.get("/inventories/{table_name}/columns", response_model=list[str])
async def api_list_inventory_columns(table_name: str, request: Request) -> list[str]:
    get_request_auth_user(request)
    try:
        table = validate_inventory_table_name(table_name)
        schema = await get_external_inventory_schema(table)
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    columns: list[str] = []
    raw = schema.get("columns")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            else:
                name = str(item or "").strip()
            if name and name not in columns:
                columns.append(name)
    return columns


@router.get("/inventories/{table_name}/apis", response_model=list[InventoryApiResponse])
async def api_list_inventory_apis(table_name: str, request: Request) -> list[InventoryApiResponse]:
    get_request_auth_user(request)
    try:
        table = validate_inventory_table_name(table_name)
        rows = await list_external_inventory_apis(table)
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    database_path = request.app.state.database_path
    return [
        _to_api_response(row, table_name=table, database_path=database_path, index=index + 1)
        for index, row in enumerate(rows)
    ]


@router.post(
    "/inventories/{table_name}/apis",
    response_model=InventoryApiResponse,
    status_code=201,
)
async def api_create_inventory_api(
    table_name: str,
    body: InventoryApiCreateRequest,
    request: Request,
) -> InventoryApiResponse:
    auth_user = get_request_auth_user(request)
    try:
        table = validate_inventory_table_name(table_name)
        payload = {
            "api_name": body.api_name.strip().lower(),
            "display_name": body.display_name.strip(),
            "description": body.description.strip(),
            "created_by": int(auth_user.idx),
            "table_name": table,
            "where_exp": body.where_exp.strip(),
            "select_exp": body.select_exp.strip(),
            "param_columns": body.param_columns.strip(),
        }
        created = await add_external_inventory_api(payload)
        await reload_external_inventory_api(table)
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    merged = {**payload, **(created if isinstance(created, dict) else {})}
    return _to_api_response(
        merged,
        table_name=table,
        database_path=request.app.state.database_path,
    )


@router.put(
    "/inventories/{table_name}/apis/{api_name}",
    response_model=InventoryApiResponse,
)
async def api_update_inventory_api(
    table_name: str,
    api_name: str,
    body: InventoryApiUpdateRequest,
    request: Request,
) -> InventoryApiResponse:
    get_request_auth_user(request)
    try:
        table = validate_inventory_table_name(table_name)
        payload = {
            "api_name": body.api_name.strip().lower() or api_name.strip().lower(),
            "display_name": body.display_name.strip(),
            "description": body.description.strip(),
            "where_exp": body.where_exp.strip(),
            "select_exp": body.select_exp.strip(),
            "param_columns": body.param_columns.strip(),
        }
        updated = await update_external_inventory_api(payload)
        await reload_external_inventory_api(table)
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    merged = {
        "table_name": table,
        **payload,
        **(updated if isinstance(updated, dict) else {}),
    }
    return _to_api_response(
        merged,
        table_name=table,
        database_path=request.app.state.database_path,
    )


@router.delete("/inventories/{table_name}/apis/{api_name}")
async def api_delete_inventory_api(
    table_name: str,
    api_name: str,
    request: Request,
) -> dict[str, object]:
    get_request_auth_user(request)
    try:
        table = validate_inventory_table_name(table_name)
        name = (api_name or "").strip()
        if not name:
            raise ValueError("api_name이 필요합니다.")
        await remove_external_inventory_api(tablename=table, api_name=name)
        await reload_external_inventory_api(table)
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "table_name": table, "api_name": name}


@router.get("/inventories/{table_name}/apis/{api_name}/test")
async def api_test_inventory_api(
    table_name: str,
    api_name: str,
    request: Request,
) -> dict[str, Any]:
    get_request_auth_user(request)
    try:
        table = validate_inventory_table_name(table_name)
        name = (api_name or "").strip()
        if not name:
            raise ValueError("api_name이 필요합니다.")
        params = {key: str(value) for key, value in request.query_params.items()}
        body = await execute_external_inventory_api(
            table_name=table,
            api_name=name,
            params=params,
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(body, list):
        return {"columns": [], "rows": body, "row_count": len(body)}
    if isinstance(body, dict):
        rows = body.get("rows")
        if isinstance(rows, list):
            columns = body.get("columns")
            return {
                "columns": columns if isinstance(columns, list) else [],
                "rows": rows,
                "row_count": int(body.get("row_count") or len(rows)),
                "truncated": bool(body.get("truncated")),
            }
        return {"columns": [], "rows": [body], "row_count": 1}
    return {"columns": [], "rows": [{"value": body}], "row_count": 1}
