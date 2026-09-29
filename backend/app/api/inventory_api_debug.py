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


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(int(viewer.role)):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


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
