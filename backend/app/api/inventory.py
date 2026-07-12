from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.db.inventory_records import (
    CHUNK_TYPE_CUSTOM,
    CHUNK_TYPE_ROW,
    MODIFIED_EMBEDDED,
    MODIFIED_NEEDS_EMBED,
    StoredInventory,
    create_inventory_record,
    delete_inventory_records,
    extract_file_ext,
    get_stored_inventory_by_idx,
    list_stored_inventory,
    update_inventory_modified,
    update_inventory_record,
)

router = APIRouter(tags=["inventory"])


class InventoryRecordResponse(BaseModel):
    idx: int
    inventory_name: str
    inventory_file: str
    file_ext: str
    chunk_type: int
    chunk_size: int
    modified: int

    @classmethod
    def from_stored_inventory(cls, record: StoredInventory) -> "InventoryRecordResponse":
        return cls(
            idx=record.idx,
            inventory_name=record.inventory_name,
            inventory_file=record.inventory_file,
            file_ext=record.file_ext,
            chunk_type=record.chunk_type,
            chunk_size=record.chunk_size,
            modified=record.modified,
        )


class UpdateInventoryRecordRequest(BaseModel):
    inventory_name: str = Field(min_length=1, max_length=100)
    chunk_type: int
    chunk_size: int = 0


class DeleteInventoryRecordsRequest(BaseModel):
    idx_list: list[int] = Field(min_length=1)


class InventoryEmbedResponse(BaseModel):
    status: str
    embedded_rows: int
    document_count: int
    modified: int


def _get_inventory_service(request: Request):
    service = getattr(request.app.state, "inventory_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Inventory service is not initialized")
    return service


def _validate_chunk_settings(*, chunk_type: int, chunk_size: int) -> None:
    if chunk_type not in {CHUNK_TYPE_ROW, CHUNK_TYPE_CUSTOM}:
        raise HTTPException(status_code=400, detail="chunk_type must be 1 (row) or 2 (custom size)")
    if chunk_type == CHUNK_TYPE_CUSTOM and chunk_size <= 0:
        raise HTTPException(status_code=400, detail="chunk_size must be greater than 0 for custom chunking")


def _needs_reembed(
    existing: StoredInventory,
    *,
    inventory_file: str | None,
    chunk_type: int,
    chunk_size: int,
) -> bool:
    if inventory_file is not None and inventory_file != existing.inventory_file:
        return True
    if chunk_type != existing.chunk_type:
        return True
    return chunk_type == CHUNK_TYPE_CUSTOM and chunk_size != existing.chunk_size


@router.get("/inventory/records", response_model=list[InventoryRecordResponse])
async def get_inventory_records(request: Request) -> list[InventoryRecordResponse]:
    database_path = request.app.state.database_path
    return [
        InventoryRecordResponse.from_stored_inventory(record)
        for record in list_stored_inventory(database_path)
    ]


@router.post("/inventory/records", response_model=InventoryRecordResponse, status_code=201)
async def create_inventory_record_with_upload(
    request: Request,
    inventory_name: str = Form(...),
    chunk_type: int = Form(...),
    chunk_size: int = Form(0),
    file: UploadFile = File(...),
) -> InventoryRecordResponse:
    database_path = request.app.state.database_path
    service = _get_inventory_service(request)
    _validate_chunk_settings(chunk_type=chunk_type, chunk_size=chunk_size)

    if not file.filename:
        raise HTTPException(status_code=400, detail="업로드할 파일을 선택해 주세요.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="업로드할 파일이 비어 있습니다.")

    try:
        saved_filename = service.save_uploaded_file(filename=file.filename, content=content)
        record = create_inventory_record(
            database_path,
            inventory_name=inventory_name,
            inventory_file=saved_filename,
            file_ext=extract_file_ext(saved_filename),
            chunk_type=chunk_type,
            chunk_size=chunk_size if chunk_type == CHUNK_TYPE_CUSTOM else 0,
            modified=MODIFIED_NEEDS_EMBED,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return InventoryRecordResponse.from_stored_inventory(record)


@router.put("/inventory/records/{idx}", response_model=InventoryRecordResponse)
async def update_inventory_metadata(
    idx: int,
    payload: UpdateInventoryRecordRequest,
    request: Request,
) -> InventoryRecordResponse:
    database_path = request.app.state.database_path
    existing = get_stored_inventory_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    _validate_chunk_settings(chunk_type=payload.chunk_type, chunk_size=payload.chunk_size)

    next_chunk_size = payload.chunk_size if payload.chunk_type == CHUNK_TYPE_CUSTOM else 0
    next_modified = existing.modified
    if _needs_reembed(
        existing,
        inventory_file=None,
        chunk_type=payload.chunk_type,
        chunk_size=next_chunk_size,
    ):
        next_modified = MODIFIED_NEEDS_EMBED

    updated = update_inventory_record(
        database_path,
        idx,
        inventory_name=payload.inventory_name,
        chunk_type=payload.chunk_type,
        chunk_size=next_chunk_size,
        modified=next_modified,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    return InventoryRecordResponse.from_stored_inventory(updated)


@router.post("/inventory/records/{idx}/upload", response_model=InventoryRecordResponse)
async def upload_inventory_file(
    idx: int,
    request: Request,
    inventory_name: str = Form(...),
    chunk_type: int = Form(...),
    chunk_size: int = Form(0),
    file: UploadFile | None = File(None),
) -> InventoryRecordResponse:
    database_path = request.app.state.database_path
    service = _get_inventory_service(request)
    existing = get_stored_inventory_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    _validate_chunk_settings(chunk_type=chunk_type, chunk_size=chunk_size)
    next_chunk_size = chunk_size if chunk_type == CHUNK_TYPE_CUSTOM else 0

    next_inventory_file = existing.inventory_file
    next_file_ext = existing.file_ext
    next_modified = existing.modified

    if file is not None and file.filename:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="업로드할 파일이 비어 있습니다.")

        if existing.inventory_file and existing.inventory_file != Path(file.filename).name:
            service.delete_uploaded_file(existing.inventory_file)

        try:
            next_inventory_file = service.save_uploaded_file(filename=file.filename, content=content)
            next_file_ext = extract_file_ext(next_inventory_file)
            next_modified = MODIFIED_NEEDS_EMBED
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif _needs_reembed(
        existing,
        inventory_file=None,
        chunk_type=chunk_type,
        chunk_size=next_chunk_size,
    ):
        next_modified = MODIFIED_NEEDS_EMBED

    updated = update_inventory_record(
        database_path,
        idx,
        inventory_name=inventory_name,
        inventory_file=next_inventory_file,
        file_ext=next_file_ext,
        chunk_type=chunk_type,
        chunk_size=next_chunk_size,
        modified=next_modified,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    return InventoryRecordResponse.from_stored_inventory(updated)


@router.post("/inventory/records/{idx}/embed", response_model=InventoryEmbedResponse)
async def embed_inventory_record(idx: int, request: Request) -> InventoryEmbedResponse:
    database_path = request.app.state.database_path
    service = _get_inventory_service(request)
    record = get_stored_inventory_by_idx(database_path, idx)
    if record is None:
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    if record.modified != MODIFIED_NEEDS_EMBED:
        raise HTTPException(status_code=400, detail="임베딩이 필요한 상태가 아닙니다.")

    try:
        embedded_rows = service.embed_inventory_record(
            inventory_idx=record.idx,
            filename=record.inventory_file,
            chunk_type=record.chunk_type,
            chunk_size=record.chunk_size,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = update_inventory_modified(database_path, idx, MODIFIED_EMBEDDED)
    if updated is None:
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    return InventoryEmbedResponse(
        status="ok",
        embedded_rows=embedded_rows,
        document_count=service.document_count,
        modified=updated.modified,
    )


@router.delete("/inventory/records")
async def remove_inventory_records(
    request: Request,
    payload: DeleteInventoryRecordsRequest = Body(...),
) -> dict[str, int]:
    database_path = request.app.state.database_path
    service = _get_inventory_service(request)
    deleted_records = delete_inventory_records(database_path, payload.idx_list)

    for record in deleted_records:
        service.delete_inventory_embeddings(record.idx)
        service.delete_uploaded_file(record.inventory_file)

    service.refresh_document_count()
    return {"deleted": len(deleted_records)}


@router.get("/inventory/status")
async def inventory_status(request: Request) -> dict:
    service = _get_inventory_service(request)
    return service.get_status_info()


@router.post("/inventory/reload")
async def reload_inventory(request: Request) -> dict:
    service = _get_inventory_service(request)
    loaded = service.reload_csv()
    return {
        "status": "ok",
        "loaded_rows": loaded,
        "document_count": service.document_count,
    }
