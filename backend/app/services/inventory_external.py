"""Client for the external inventory-api mock/service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from backend.app.config import (
    resolve_inventory_api_base_url,
    resolve_inventory_csv_transfer_url,
    resolve_inventory_csv_upload_url,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0


class InventoryExternalApiError(Exception):
    """Raised when an external inventory-api call fails."""


class InventoryExternalUploadError(InventoryExternalApiError):
    """Raised when the external inventory CSV upload fails."""


def _normalize_base_url(base_url: str | None) -> str:
    raw = (base_url or "").strip()
    if raw:
        return raw.rstrip("/")
    return resolve_inventory_api_base_url()


def _join_url(base_url: str, path: str) -> str:
    base = base_url if base_url.endswith("/") else f"{base_url}/"
    return urljoin(base, path.lstrip("/"))


async def call_inventory_api(
    *,
    method: str,
    path: str,
    base_url: str | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call a remote inventory-api endpoint and return a debug-friendly payload."""
    url = _join_url(_normalize_base_url(base_url), path)
    upper = (method or "GET").upper()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.request(
                upper,
                url,
                params=params,
                json=json_body,
                files=files,
            )
    except httpx.TimeoutException as exc:
        raise InventoryExternalApiError(f"인벤토리 API 요청이 시간 초과되었습니다: {url}") from exc
    except httpx.RequestError as exc:
        raise InventoryExternalApiError(f"인벤토리 API 연결에 실패했습니다: {exc}") from exc

    body_text = response.text or ""
    parsed: Any
    try:
        parsed = response.json()
    except ValueError:
        parsed = body_text

    result: dict[str, Any] = {
        "ok": response.status_code < 400,
        "status_code": response.status_code,
        "url": str(response.request.url),
        "method": upper,
        "body": parsed,
        "raw_body": body_text,
    }
    if response.status_code >= 400:
        detail = body_text.strip()
        if len(detail) > 400:
            detail = detail[:400] + "…"
        result["error"] = (
            f"HTTP {response.status_code}" + (f": {detail}" if detail else "")
        )
    return result


async def upload_csv_to_external_inventory_api(
    content: bytes,
    *,
    filename: str,
    upload_url: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, object]:
    """POST multipart ``file`` to external ``/uploadCSV``.

    Expected success payload example::

        {"filename": "t.csv", "stored_path": "/data/csv/t.csv", "size_bytes": 18}
    """
    name = Path((filename or "upload.csv").strip()).name or "upload.csv"
    if not name.lower().endswith(".csv"):
        name = f"{name}.csv"

    if upload_url:
        url = upload_url.strip()
    elif base_url:
        url = f"{_normalize_base_url(base_url)}/uploadCSV"
    else:
        url = resolve_inventory_csv_upload_url()
    if not url:
        raise InventoryExternalUploadError("인벤토리 CSV 업로드 URL이 설정되지 않았습니다.")

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                url,
                files={"file": (name, content, "text/csv")},
            )
    except httpx.TimeoutException as exc:
        raise InventoryExternalUploadError("외부 인벤토리 CSV 업로드가 시간 초과되었습니다.") from exc
    except httpx.RequestError as exc:
        raise InventoryExternalUploadError(
            f"외부 인벤토리 CSV 업로드 연결에 실패했습니다: {exc}"
        ) from exc

    if response.status_code >= 400:
        detail = (response.text or "").strip()
        if len(detail) > 300:
            detail = detail[:300] + "…"
        raise InventoryExternalUploadError(
            f"외부 인벤토리 CSV 업로드 실패 (HTTP {response.status_code})"
            + (f": {detail}" if detail else "")
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise InventoryExternalUploadError(
            "외부 인벤토리 CSV 업로드 응답이 JSON이 아닙니다."
        ) from exc

    if not isinstance(payload, dict):
        raise InventoryExternalUploadError("외부 인벤토리 CSV 업로드 응답 형식이 올바르지 않습니다.")

    remote_name = Path(str(payload.get("filename") or name)).name
    if not remote_name:
        raise InventoryExternalUploadError("외부 업로드 응답에 filename이 없습니다.")
    payload["filename"] = remote_name
    logger.info(
        "inventory csv uploaded to external api filename=%s size=%s url=%s",
        remote_name,
        payload.get("size_bytes"),
        url,
    )
    return payload


async def transfer_csv_to_external_table(
    *,
    filename: str,
    tablename: str,
    display_name: str | None = None,
    description: str | None = None,
    created_by: int | None = None,
    transfer_url: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, object]:
    """POST ``{filename, tablename, ...}`` to external ``/transferCSV2Table``."""
    name = Path((filename or "").strip()).name
    if not name:
        raise InventoryExternalUploadError("transferCSV2Table 에 필요한 filename이 없습니다.")
    table = (tablename or "").strip()
    if not table:
        raise InventoryExternalUploadError("transferCSV2Table 에 필요한 tablename이 없습니다.")
    if len(table) > 50:
        raise InventoryExternalUploadError("tablename은 50자를 넘을 수 없습니다.")

    if transfer_url:
        url = transfer_url.strip()
    elif base_url:
        url = f"{_normalize_base_url(base_url)}/transferCSV2Table"
    else:
        url = resolve_inventory_csv_transfer_url()
    if not url:
        raise InventoryExternalUploadError("인벤토리 CSV 전환 URL이 설정되지 않았습니다.")

    body: dict[str, object] = {"filename": name, "tablename": table}
    if display_name is not None:
        body["display_name"] = display_name[:100]
    if description is not None:
        body["description"] = description[:200]
    if created_by is not None:
        body["created_by"] = int(created_by)

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=body)
    except httpx.TimeoutException as exc:
        raise InventoryExternalUploadError("외부 CSV→테이블 전환이 시간 초과되었습니다.") from exc
    except httpx.RequestError as exc:
        raise InventoryExternalUploadError(
            f"외부 CSV→테이블 전환 연결에 실패했습니다: {exc}"
        ) from exc

    if response.status_code >= 400:
        detail = (response.text or "").strip()
        if len(detail) > 300:
            detail = detail[:300] + "…"
        raise InventoryExternalUploadError(
            f"외부 CSV→테이블 전환 실패 (HTTP {response.status_code})"
            + (f": {detail}" if detail else "")
        )

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if not isinstance(payload, dict):
        payload = {"result": payload}

    logger.info(
        "inventory csv transferred to table filename=%s tablename=%s url=%s",
        name,
        table,
        url,
    )
    return payload


def _raise_if_api_error(result: dict[str, Any], *, action: str) -> Any:
    if not result.get("ok"):
        detail = str(result.get("error") or result.get("raw_body") or "알 수 없는 오류")
        raise InventoryExternalApiError(f"{action} 실패: {detail}")
    return result.get("body")


def _stringify_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_row(row: object, columns: list[str]) -> dict[str, str]:
    if isinstance(row, dict):
        return {col: _stringify_cell(row.get(col)) for col in columns}
    if isinstance(row, (list, tuple)):
        return {
            col: _stringify_cell(row[index] if index < len(row) else "")
            for index, col in enumerate(columns)
        }
    return {col: "" for col in columns}


async def get_external_inventory_schema(
    inventory: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """GET ``/getInventorySchema?inventory=...``."""
    name = (inventory or "").strip()
    if not name:
        raise InventoryExternalApiError("inventory(테이블) 이름이 필요합니다.")
    result = await call_inventory_api(
        method="GET",
        path="/getInventorySchema",
        base_url=base_url,
        params={"inventory": name},
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 스키마 조회")
    if not isinstance(body, dict):
        raise InventoryExternalApiError("인벤토리 스키마 응답 형식이 올바르지 않습니다.")
    return body


async def get_external_inventory_count(
    table: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> int:
    """GET ``/getCount?table=...`` → row count."""
    name = (table or "").strip()
    if not name:
        raise InventoryExternalApiError("table 이름이 필요합니다.")
    result = await call_inventory_api(
        method="GET",
        path="/getCount",
        base_url=base_url,
        params={"table": name},
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 건수 조회")
    if isinstance(body, dict):
        for key in ("count", "total", "total_rows", "row_count"):
            if key in body:
                try:
                    return max(0, int(body[key]))
                except (TypeError, ValueError) as exc:
                    raise InventoryExternalApiError(
                        f"인벤토리 건수 응답이 올바르지 않습니다: {body.get(key)!r}"
                    ) from exc
    if isinstance(body, (int, float)):
        return max(0, int(body))
    raise InventoryExternalApiError("인벤토리 건수 응답에서 count를 찾지 못했습니다.")


async def get_external_inventory_records(
    table: str,
    *,
    startrow: int,
    endrow: int,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """GET ``/getRecordsWithRows`` (startrow/endrow are 1-based inclusive)."""
    name = (table or "").strip()
    if not name:
        raise InventoryExternalApiError("table 이름이 필요합니다.")
    start = int(startrow)
    end = int(endrow)
    if start < 1:
        raise InventoryExternalApiError("startrow는 1 이상이어야 합니다.")
    if end < start:
        raise InventoryExternalApiError("endrow는 startrow 이상이어야 합니다.")
    result = await call_inventory_api(
        method="GET",
        path="/getRecordsWithRows",
        base_url=base_url,
        params={"table": name, "startrow": start, "endrow": end},
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 행 조회")
    if not isinstance(body, dict):
        raise InventoryExternalApiError("인벤토리 행 조회 응답 형식이 올바르지 않습니다.")
    return body


async def preview_external_inventory_table(
    table: str,
    *,
    startrow: int = 1,
    endrow: int = 50,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, object]:
    """Build a spreadsheet-friendly preview from remote schema/count/rows APIs."""
    name = (table or "").strip()
    if not name:
        raise InventoryExternalApiError("table 이름이 필요합니다.")
    start = max(1, int(startrow or 1))
    end = max(start, int(endrow or start))

    total_rows = await get_external_inventory_count(
        name, base_url=base_url, timeout_seconds=timeout_seconds
    )
    if total_rows == 0 or start > total_rows:
        schema = await get_external_inventory_schema(
            name, base_url=base_url, timeout_seconds=timeout_seconds
        )
        columns = _columns_from_schema(schema)
        return {
            "table_name": name,
            "columns": columns,
            "labels": columns,
            "rows": [],
            "startrow": start,
            "endrow": end,
            "total_rows": total_rows,
            "has_more": False,
        }

    capped_end = min(end, total_rows)
    records = await get_external_inventory_records(
        name,
        startrow=start,
        endrow=capped_end,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    columns = _columns_from_records(records)
    if not columns:
        schema = await get_external_inventory_schema(
            name, base_url=base_url, timeout_seconds=timeout_seconds
        )
        columns = _columns_from_schema(schema)

    raw_rows = records.get("rows")
    if not isinstance(raw_rows, list):
        raw_rows = []
    rows = [_normalize_row(row, columns) for row in raw_rows]
    return {
        "table_name": name,
        "columns": columns,
        "labels": columns,
        "rows": rows,
        "startrow": start,
        "endrow": capped_end,
        "total_rows": total_rows,
        "has_more": capped_end < total_rows,
    }


def _columns_from_schema(schema: dict[str, Any]) -> list[str]:
    raw = schema.get("columns")
    if not isinstance(raw, list):
        return []
    columns: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("column") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name not in columns:
            columns.append(name)
    return columns


def _columns_from_records(records: dict[str, Any]) -> list[str]:
    raw = records.get("columns")
    if isinstance(raw, list) and raw:
        columns: list[str] = []
        for item in raw:
            name = str(item or "").strip()
            if name and name not in columns:
                columns.append(name)
        return columns
    rows = records.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return [str(key) for key in rows[0].keys()]
    return []


async def list_external_inventories(
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    result = await call_inventory_api(
        method="GET",
        path="/getInventoryList",
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 목록 조회")
    if isinstance(body, dict):
        for key in ("inventories", "items", "data"):
            if key not in body:
                continue
            rows = body.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    raise InventoryExternalApiError("인벤토리 목록 응답 형식이 올바르지 않습니다.")


async def add_external_inventory(
    *,
    table_name: str,
    origin_csv: str,
    display_name: str | None = None,
    description: str | None = None,
    created_by: int | None = None,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    body: dict[str, object] = {
        "table_name": table_name,
        "origin_csv": origin_csv,
    }
    if display_name is not None:
        body["display_name"] = display_name
    if description is not None:
        body["description"] = description
    if created_by is not None:
        body["created_by"] = int(created_by)
    result = await call_inventory_api(
        method="POST",
        path="/addInventory",
        base_url=base_url,
        json_body=body,
        timeout_seconds=timeout_seconds,
    )
    payload = _raise_if_api_error(result, action="인벤토리 등록")
    return payload if isinstance(payload, dict) else {"result": payload}


async def remove_external_inventory(
    table: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    result = await call_inventory_api(
        method="POST",
        path="/removeInventory",
        base_url=base_url,
        params={"table": table},
        timeout_seconds=timeout_seconds,
    )
    payload = _raise_if_api_error(result, action="인벤토리 삭제")
    return payload if isinstance(payload, dict) else {"result": payload}


async def remove_external_temp_table(
    tablename: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    result = await call_inventory_api(
        method="POST",
        path="/removeTempTable",
        base_url=base_url,
        params={"tablename": tablename},
        timeout_seconds=timeout_seconds,
    )
    payload = _raise_if_api_error(result, action="임시 테이블 삭제")
    return payload if isinstance(payload, dict) else {"result": payload}


async def list_external_inventory_apis(
    tablename: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    result = await call_inventory_api(
        method="GET",
        path="/getInventoryAPIList",
        base_url=base_url,
        params={"tablename": tablename},
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 API 목록 조회")
    if isinstance(body, dict):
        for key in ("apis", "items", "data"):
            if key not in body:
                continue
            rows = body.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        # Some payloads may nest under a single inventory object.
        nested = body.get("inventory")
        if isinstance(nested, dict) and isinstance(nested.get("apis"), list):
            return [row for row in nested["apis"] if isinstance(row, dict)]
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    raise InventoryExternalApiError("인벤토리 API 목록 응답 형식이 올바르지 않습니다.")


async def add_external_inventory_api(
    payload: dict[str, Any],
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    result = await call_inventory_api(
        method="POST",
        path="/addInventoryAPI",
        base_url=base_url,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 API 생성")
    return body if isinstance(body, dict) else {"result": body}


async def update_external_inventory_api(
    payload: dict[str, Any],
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    result = await call_inventory_api(
        method="POST",
        path="/updateInventoryAPI",
        base_url=base_url,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 API 수정")
    return body if isinstance(body, dict) else {"result": body}


async def remove_external_inventory_api(
    *,
    tablename: str,
    api_name: str,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    result = await call_inventory_api(
        method="POST",
        path="/removeInventoryAPI",
        base_url=base_url,
        params={"tablename": tablename, "api_name": api_name},
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 API 삭제")
    return body if isinstance(body, dict) else {"result": body}


async def reload_external_inventory_api(
    tablename: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    result = await call_inventory_api(
        method="POST",
        path="/reloadAPI",
        base_url=base_url,
        params={"tablename": tablename},
        timeout_seconds=timeout_seconds,
    )
    body = _raise_if_api_error(result, action="인벤토리 API reload")
    return body if isinstance(body, dict) else {"result": body}


async def execute_external_inventory_api(
    *,
    table_name: str,
    api_name: str,
    params: dict[str, Any] | None = None,
    base_url: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> Any:
    result = await call_inventory_api(
        method="GET",
        path=f"/inv/{table_name}/{api_name}",
        base_url=base_url,
        params=params,
        timeout_seconds=timeout_seconds,
    )
    return _raise_if_api_error(result, action="인벤토리 API 실행")
