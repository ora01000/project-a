"""Inventory management APIs — CSV upload, preview, metadata CRUD, and dynamic query APIs."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.db.inventory import (
    compare_csv_columns,
    create_inventory,
    delete_inventory,
    get_inventory_by_idx,
    list_inventories,
    preview_inventory_csv,
    save_inventory_csv,
    update_inventory,
    validate_and_parse_csv,
)
from backend.app.db.inventory_api import (
    create_inventory_api,
    delete_inventory_api,
    execute_inventory_api_query,
    get_inventory_api_by_idx,
    get_inventory_api_by_name,
    get_inventory_table_columns,
    list_inventory_apis_by_table,
    update_inventory_api,
)
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user

router = APIRouter(tags=["inventory"])
logger = logging.getLogger(__name__)


class InventoryResponse(BaseModel):
    idx: int
    table_name: str = ""
    display_name: str
    description: str = ""
    created_by: int = 0
    created_by_username: str = ""
    origin_csv: str = ""


class InventoryCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)
    origin_csv: str = Field(min_length=1, max_length=100)
    table_name: str = Field(min_length=1, max_length=50)


class InventoryUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)
    origin_csv: str | None = Field(default=None, max_length=100)


class InventoryCsvPreviewResponse(BaseModel):
    filename: str
    columns: list[str]
    labels: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]]
    offset: int = 0
    limit: int = 50
    total_rows: int = 0
    has_more: bool = False
    columns_compatible: bool | None = None
    compatibility_error: str | None = None


class InventoryApiResponse(BaseModel):
    idx: int
    api_name: str
    display_name: str
    description: str = ""
    api_fullpath: str
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
    param_columns: str = Field(min_length=1, max_length=500)


class InventoryApiUpdateRequest(BaseModel):
    api_name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)
    where_exp: str = Field(min_length=1, max_length=500)
    select_exp: str = Field(min_length=1, max_length=500)
    param_columns: str = Field(min_length=1, max_length=500)


def _to_response(record) -> InventoryResponse:
    return InventoryResponse(
        idx=record.idx,
        table_name=record.table_name,
        display_name=record.display_name,
        description=record.description,
        created_by=record.created_by,
        created_by_username=record.created_by_username,
        origin_csv=record.origin_csv,
    )


def _to_api_response(record) -> InventoryApiResponse:
    return InventoryApiResponse(
        idx=record.idx,
        api_name=record.api_name,
        display_name=record.display_name,
        description=record.description,
        api_fullpath=record.api_fullpath,
        created_by=record.created_by,
        created_by_username=record.created_by_username,
        table_name=record.table_name,
        where_exp=record.where_exp,
        select_exp=record.select_exp,
        param_columns=record.param_columns,
    )


def _can_edit(record, auth_user) -> bool:
    return int(record.created_by) == int(auth_user.idx) or is_admin_role(int(auth_user.role))


@router.get("/inventories", response_model=list[InventoryResponse])
async def api_list_inventories(request: Request) -> list[InventoryResponse]:
    get_request_auth_user(request)
    records = list_inventories(request.app.state.database_path)
    return [_to_response(row) for row in records]


@router.post("/inventories/csv/upload", response_model=InventoryCsvPreviewResponse)
async def api_upload_inventory_csv(
    request: Request,
    file: UploadFile = File(...),
    compare_to: str | None = Query(default=None),
) -> InventoryCsvPreviewResponse:
    get_request_auth_user(request)
    raw_name = (file.filename or "upload.csv").strip()
    if not raw_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        validate_and_parse_csv(content)
        stored = save_inventory_csv(content, original_filename=raw_name)
        preview = preview_inventory_csv(stored, offset=0, limit=50)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    columns_compatible: bool | None = None
    compatibility_error: str | None = None
    baseline = (compare_to or "").strip()
    if baseline:
        try:
            compare_csv_columns(baseline, stored)
            columns_compatible = True
        except (ValueError, FileNotFoundError) as exc:
            columns_compatible = False
            compatibility_error = str(exc)

    return InventoryCsvPreviewResponse(
        **preview,
        columns_compatible=columns_compatible,
        compatibility_error=compatibility_error,
    )


@router.get(
    "/inventories/csv/{filename}/preview",
    response_model=InventoryCsvPreviewResponse,
)
async def api_preview_inventory_csv(
    filename: str,
    request: Request,
    offset: int = 0,
    limit: int = 50,
) -> InventoryCsvPreviewResponse:
    get_request_auth_user(request)
    try:
        preview = preview_inventory_csv(filename, offset=offset, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InventoryCsvPreviewResponse(**preview)


@router.post("/inventories", response_model=InventoryResponse, status_code=201)
async def api_create_inventory(
    body: InventoryCreateRequest,
    request: Request,
) -> InventoryResponse:
    auth_user = get_request_auth_user(request)
    try:
        record = create_inventory(
            request.app.state.database_path,
            display_name=body.display_name,
            description=body.description,
            created_by=int(auth_user.idx),
            origin_csv=body.origin_csv,
            table_name=body.table_name,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(record)


@router.get("/inventory-data/{api_name}")
async def api_execute_inventory_data(api_name: str, request: Request) -> list[dict[str, object]]:
    get_request_auth_user(request)
    record = get_inventory_api_by_name(request.app.state.database_path, api_name)
    if record is None:
        raise HTTPException(status_code=404, detail="API를 찾을 수 없습니다.")
    params = {key: str(value) for key, value in request.query_params.items()}
    try:
        return execute_inventory_api_query(request.app.state.database_path, record, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/inventories/{inventory_idx}/columns", response_model=list[str])
async def api_list_inventory_columns(inventory_idx: int, request: Request) -> list[str]:
    get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    if not record.table_name:
        raise HTTPException(status_code=400, detail="인벤토리 테이블이 없습니다.")
    try:
        return get_inventory_table_columns(request.app.state.database_path, record.table_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/inventories/{inventory_idx}/apis", response_model=list[InventoryApiResponse])
async def api_list_inventory_apis(inventory_idx: int, request: Request) -> list[InventoryApiResponse]:
    get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    if not record.table_name:
        return []
    rows = list_inventory_apis_by_table(request.app.state.database_path, record.table_name)
    return [_to_api_response(row) for row in rows]


@router.post(
    "/inventories/{inventory_idx}/apis",
    response_model=InventoryApiResponse,
    status_code=201,
)
async def api_create_inventory_api(
    inventory_idx: int,
    body: InventoryApiCreateRequest,
    request: Request,
) -> InventoryApiResponse:
    auth_user = get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    if not _can_edit(record, auth_user):
        raise HTTPException(status_code=403, detail="이 인벤토리의 API를 생성할 권한이 없습니다.")
    if not record.table_name:
        raise HTTPException(status_code=400, detail="인벤토리 테이블이 없습니다.")
    try:
        created = create_inventory_api(
            request.app.state.database_path,
            api_name=body.api_name,
            display_name=body.display_name,
            description=body.description,
            table_name=record.table_name,
            where_exp=body.where_exp,
            select_exp=body.select_exp,
            param_columns=body.param_columns,
            created_by=int(auth_user.idx),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_api_response(created)


@router.put(
    "/inventories/{inventory_idx}/apis/{api_idx}",
    response_model=InventoryApiResponse,
)
async def api_update_inventory_api(
    inventory_idx: int,
    api_idx: int,
    body: InventoryApiUpdateRequest,
    request: Request,
) -> InventoryApiResponse:
    auth_user = get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    api_record = get_inventory_api_by_idx(request.app.state.database_path, api_idx)
    if api_record is None or api_record.table_name != record.table_name:
        raise HTTPException(status_code=404, detail="API를 찾을 수 없습니다.")
    if not _can_edit(record, auth_user):
        raise HTTPException(status_code=403, detail="이 API를 수정할 권한이 없습니다.")
    try:
        updated = update_inventory_api(
            request.app.state.database_path,
            api_idx,
            api_name=body.api_name,
            display_name=body.display_name,
            description=body.description,
            where_exp=body.where_exp,
            select_exp=body.select_exp,
            param_columns=body.param_columns,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_api_response(updated)


@router.delete("/inventories/{inventory_idx}/apis/{api_idx}")
async def api_delete_inventory_api(
    inventory_idx: int,
    api_idx: int,
    request: Request,
) -> dict[str, object]:
    auth_user = get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    api_record = get_inventory_api_by_idx(request.app.state.database_path, api_idx)
    if api_record is None or api_record.table_name != record.table_name:
        raise HTTPException(status_code=404, detail="API를 찾을 수 없습니다.")
    if not _can_edit(record, auth_user):
        raise HTTPException(status_code=403, detail="이 API를 삭제할 권한이 없습니다.")
    delete_inventory_api(request.app.state.database_path, api_idx)
    return {"ok": True, "idx": api_idx}


@router.put("/inventories/{inventory_idx}", response_model=InventoryResponse)
async def api_update_inventory(
    inventory_idx: int,
    body: InventoryUpdateRequest,
    request: Request,
) -> InventoryResponse:
    auth_user = get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    if not _can_edit(record, auth_user):
        raise HTTPException(status_code=403, detail="이 인벤토리를 수정할 권한이 없습니다.")
    try:
        updated = update_inventory(
            request.app.state.database_path,
            inventory_idx,
            display_name=body.display_name,
            description=body.description,
            origin_csv=body.origin_csv,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(updated)


@router.get("/inventories/{inventory_idx}", response_model=InventoryResponse)
async def api_get_inventory(inventory_idx: int, request: Request) -> InventoryResponse:
    get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    return _to_response(record)


@router.delete("/inventories/{inventory_idx}")
async def api_delete_inventory(inventory_idx: int, request: Request) -> dict[str, object]:
    auth_user = get_request_auth_user(request)
    record = get_inventory_by_idx(request.app.state.database_path, inventory_idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리를 찾을 수 없습니다.")
    if not _can_edit(record, auth_user):
        raise HTTPException(status_code=403, detail="이 인벤토리를 삭제할 권한이 없습니다.")
    delete_inventory(request.app.state.database_path, inventory_idx)
    return {"ok": True, "idx": inventory_idx}
