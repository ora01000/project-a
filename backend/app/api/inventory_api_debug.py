"""Admin debug proxy for the remote inventory-api service."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.config import resolve_inventory_api_base_url
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.inventory_external import (
    InventoryExternalApiError,
    call_inventory_api,
)

router = APIRouter(tags=["debug"])


class InventoryApiConfigResponse(BaseModel):
    base_url: str


class InventoryApiTransferRequest(BaseModel):
    filename: str = Field(min_length=1)
    tablename: str = Field(min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=200)
    created_by: int | None = None
    base_url: str | None = None


class InventoryApiSqlRequest(BaseModel):
    sql: str = Field(min_length=1)
    base_url: str | None = None


class InventoryApiRetrieveRequest(BaseModel):
    api_url: str = Field(min_length=1)
    api_key: str | None = None
    auth_type: int = Field(default=1, ge=1, le=2)
    base_url: str | None = None


class InventoryApiTestRequest(BaseModel):
    url: str = Field(min_length=1)
    token: str | None = None
    auth_type: int = Field(default=1, ge=1, le=2)
    base_url: str | None = None


class InventoryApiTransferJsonRequest(BaseModel):
    response_json: Any
    tablename: str = Field(min_length=1, max_length=50)
    base_url: str | None = None


class InventoryApiAddInventoryRequest(BaseModel):
    table_name: str = Field(min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=200)
    created_by: int | None = None
    origin_csv: str | None = Field(default=None, max_length=100)
    origin_type: int | None = None
    origin_api_url: str | None = Field(default=None, max_length=500)
    origin_api_auth_type: int | None = None
    origin_api_key: str | None = Field(default=None, max_length=500)
    is_scheduled: bool = False
    api_crawling_cron: str | None = Field(default=None, max_length=100)
    base_url: str | None = None


class InventoryApiAddApiRequest(BaseModel):
    api_name: str = Field(min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=200)
    created_by: int | None = None
    table_name: str = Field(min_length=1, max_length=50)
    where_exp: str | None = Field(default=None, max_length=500)
    select_exp: str | None = Field(default=None, max_length=500)
    param_columns: str | None = Field(default=None, max_length=500)
    base_url: str | None = None


class InventoryApiUpdateApiRequest(BaseModel):
    api_name: str = Field(min_length=1, max_length=50)
    table_name: str | None = Field(default=None, max_length=50)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=200)
    where_exp: str | None = Field(default=None, max_length=500)
    select_exp: str | None = Field(default=None, max_length=500)
    param_columns: str | None = Field(default=None, max_length=500)
    base_url: str | None = None


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(int(viewer.role)):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _body_without_base(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(exclude_none=True)
    payload.pop("base_url", None)
    return payload


@router.get("/debug/inventory-api/config", response_model=InventoryApiConfigResponse)
async def api_inventory_api_debug_config(request: Request) -> InventoryApiConfigResponse:
    _require_admin(request)
    return InventoryApiConfigResponse(base_url=resolve_inventory_api_base_url())


@router.post("/debug/inventory-api/uploadCSV")
async def api_inventory_api_debug_upload_csv(
    request: Request,
    file: UploadFile = File(...),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    name = (file.filename or "upload.csv").strip() or "upload.csv"
    try:
        return await call_inventory_api(
            method="POST",
            path="/uploadCSV",
            base_url=base_url,
            files={"file": (name, content, file.content_type or "text/csv")},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/transferCSV2Table")
async def api_inventory_api_debug_transfer(
    body: InventoryApiTransferRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    payload: dict[str, object] = {
        "filename": body.filename.strip(),
        "tablename": body.tablename.strip(),
    }
    if body.display_name is not None:
        payload["display_name"] = body.display_name
    if body.description is not None:
        payload["description"] = body.description
    if body.created_by is not None:
        payload["created_by"] = body.created_by
    try:
        return await call_inventory_api(
            method="POST",
            path="/transferCSV2Table",
            base_url=body.base_url,
            json_body=payload,
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/debug/inventory-api/getInventoryList")
async def api_inventory_api_debug_list(
    request: Request,
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="GET",
            path="/getInventoryList",
            base_url=base_url,
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/debug/inventory-api/getInventorySchema")
async def api_inventory_api_debug_schema(
    request: Request,
    inventory: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="GET",
            path="/getInventorySchema",
            base_url=base_url,
            params={"inventory": inventory},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/debug/inventory-api/getRecordsWithRows")
async def api_inventory_api_debug_records(
    request: Request,
    table: str = Query(min_length=1),
    startrow: int = Query(ge=1),
    endrow: int = Query(ge=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    if endrow < startrow:
        raise HTTPException(status_code=400, detail="endrow는 startrow 이상이어야 합니다.")
    try:
        return await call_inventory_api(
            method="GET",
            path="/getRecordsWithRows",
            base_url=base_url,
            params={"table": table, "startrow": startrow, "endrow": endrow},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/debug/inventory-api/getCount")
async def api_inventory_api_debug_count(
    request: Request,
    table: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="GET",
            path="/getCount",
            base_url=base_url,
            params={"table": table},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/removeInventory")
async def api_inventory_api_debug_remove(
    request: Request,
    table: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/removeInventory",
            base_url=base_url,
            params={"table": table},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/debug/inventory-api/getInventoryAPIList")
async def api_inventory_api_debug_api_list(
    request: Request,
    tablename: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="GET",
            path="/getInventoryAPIList",
            base_url=base_url,
            params={"tablename": tablename},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/sql")
async def api_inventory_api_debug_sql(
    body: InventoryApiSqlRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/sql",
            base_url=body.base_url,
            json_body={"sql": body.sql},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/retrieve")
async def api_inventory_api_debug_retrieve(
    body: InventoryApiRetrieveRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/retrieve",
            base_url=body.base_url,
            json_body=_body_without_base(body),
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/testAPI")
async def api_inventory_api_debug_test_api(
    body: InventoryApiTestRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/testAPI",
            base_url=body.base_url,
            json_body=_body_without_base(body),
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/transferJSON2Table")
async def api_inventory_api_debug_transfer_json(
    body: InventoryApiTransferJsonRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/transferJSON2Table",
            base_url=body.base_url,
            json_body=_body_without_base(body),
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/addInventory")
async def api_inventory_api_debug_add_inventory(
    body: InventoryApiAddInventoryRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/addInventory",
            base_url=body.base_url,
            json_body=_body_without_base(body),
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/removeTempTable")
async def api_inventory_api_debug_remove_temp_table(
    request: Request,
    tablename: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/removeTempTable",
            base_url=base_url,
            params={"tablename": tablename},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/addInventoryAPI")
async def api_inventory_api_debug_add_api(
    body: InventoryApiAddApiRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/addInventoryAPI",
            base_url=body.base_url,
            json_body=_body_without_base(body),
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/updateInventoryAPI")
async def api_inventory_api_debug_update_api(
    body: InventoryApiUpdateApiRequest,
    request: Request,
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/updateInventoryAPI",
            base_url=body.base_url,
            json_body=_body_without_base(body),
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/removeInventoryAPI")
async def api_inventory_api_debug_remove_api(
    request: Request,
    tablename: str = Query(min_length=1),
    api_name: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/removeInventoryAPI",
            base_url=base_url,
            params={"tablename": tablename, "api_name": api_name},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/debug/inventory-api/reloadAPI")
async def api_inventory_api_debug_reload_api(
    request: Request,
    tablename: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="POST",
            path="/reloadAPI",
            base_url=base_url,
            params={"tablename": tablename},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/debug/inventory-api/getAllDataInColumn")
async def api_inventory_api_debug_all_data_in_column(
    request: Request,
    tablename: str = Query(min_length=1),
    columnname: str = Query(min_length=1),
    base_url: str | None = Query(default=None),
) -> dict[str, Any]:
    _require_admin(request)
    try:
        return await call_inventory_api(
            method="GET",
            path="/getAllDataInColumn",
            base_url=base_url,
            params={"tablename": tablename, "columnname": columnname},
        )
    except InventoryExternalApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
