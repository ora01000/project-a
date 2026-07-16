import logging
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.db.inventory_records import (
    CHUNK_TYPE_CUSTOM,
    CHUNK_TYPE_ROW,
    DB_TYPE_TABLE,
    DB_TYPE_VECTOR,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_N_RESULTS,
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
from backend.app.db.inventory_table_import import (
    drop_inventory_data_table,
    import_csv_to_sqlite_table,
    table_name_from_filename,
)

router = APIRouter(tags=["inventory"])
logger = logging.getLogger(__name__)

MAX_INVENTORY_UPLOAD_BYTES = 100 * 1024 * 1024


class InventoryRecordResponse(BaseModel):
    idx: int
    inventory_name: str
    inventory_file: str
    file_ext: str
    chunk_type: int
    chunk_size: int
    chunk_overlap: int
    n_results: int
    db_type: str
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
            chunk_overlap=record.chunk_overlap,
            n_results=record.n_results,
            db_type=record.effective_db_type,
            modified=record.modified,
        )


class UpdateInventoryRecordRequest(BaseModel):
    inventory_name: str = Field(min_length=1, max_length=100)
    chunk_type: int
    chunk_size: int = 0
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    n_results: int = DEFAULT_N_RESULTS
    db_type: str = DB_TYPE_VECTOR


def _normalize_db_type(db_type: str | None) -> str:
    value = (db_type or DB_TYPE_VECTOR).strip().lower()
    if value not in {DB_TYPE_TABLE, DB_TYPE_VECTOR}:
        raise HTTPException(status_code=400, detail="db_type must be 'table' or 'vector'")
    return value


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


def _validate_upload_size(content: bytes) -> None:
    if len(content) > MAX_INVENTORY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail="업로드 가능한 최대 파일 크기(100MB)를 초과했습니다.",
        )


def _validate_chunk_settings(
    *,
    chunk_type: int,
    chunk_size: int,
    chunk_overlap: int,
    n_results: int,
) -> None:
    if chunk_type not in {CHUNK_TYPE_ROW, CHUNK_TYPE_CUSTOM}:
        raise HTTPException(status_code=400, detail="chunk_type must be 1 (row) or 2 (custom size)")
    if chunk_overlap < 0:
        raise HTTPException(status_code=400, detail="chunk_overlap must be greater than or equal to 0")
    if n_results <= 0:
        raise HTTPException(status_code=400, detail="n_results must be greater than 0")
    if chunk_type == CHUNK_TYPE_CUSTOM:
        if chunk_size <= 0:
            raise HTTPException(status_code=400, detail="chunk_size must be greater than 0 for custom chunking")
        if chunk_overlap >= chunk_size:
            raise HTTPException(status_code=400, detail="chunk_overlap must be less than chunk_size")


def _needs_reembed(
    existing: StoredInventory,
    *,
    inventory_file: str | None,
    chunk_type: int,
    chunk_size: int,
    chunk_overlap: int,
) -> bool:
    if inventory_file is not None and inventory_file != existing.inventory_file:
        return True
    if chunk_type != existing.chunk_type:
        return True
    if chunk_type == CHUNK_TYPE_CUSTOM and (
        chunk_size != existing.chunk_size or chunk_overlap != existing.chunk_overlap
    ):
        return True
    return False


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
    db_type: str = Form(DB_TYPE_VECTOR),
    chunk_type: int = Form(CHUNK_TYPE_ROW),
    chunk_size: int = Form(0),
    chunk_overlap: int = Form(DEFAULT_CHUNK_OVERLAP),
    n_results: int = Form(DEFAULT_N_RESULTS),
    file: UploadFile = File(...),
) -> InventoryRecordResponse:
    database_path = request.app.state.database_path
    service = _get_inventory_service(request)
    normalized_db_type = _normalize_db_type(db_type)

    if not file.filename:
        raise HTTPException(status_code=400, detail="업로드할 파일을 선택해 주세요.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="업로드할 파일이 비어 있습니다.")
    _validate_upload_size(content)

    try:
        saved_filename = service.save_uploaded_file(filename=file.filename, content=content)

        if normalized_db_type == DB_TYPE_TABLE:
            if extract_file_ext(saved_filename) != "csv":
                service.delete_uploaded_file(saved_filename)
                raise HTTPException(status_code=400, detail="table 방식은 CSV 파일만 업로드할 수 있습니다.")

            table_name, inserted_rows = import_csv_to_sqlite_table(
                database_path,
                filename=saved_filename,
                content=content,
            )
            logger.info(
                "Inventory table import complete file=%s table=%s rows=%s",
                saved_filename,
                table_name,
                inserted_rows,
            )
            record = create_inventory_record(
                database_path,
                inventory_name=inventory_name,
                inventory_file=saved_filename,
                file_ext=extract_file_ext(saved_filename),
                chunk_type=CHUNK_TYPE_ROW,
                chunk_size=0,
                chunk_overlap=DEFAULT_CHUNK_OVERLAP,
                n_results=DEFAULT_N_RESULTS,
                db_type=DB_TYPE_TABLE,
                modified=MODIFIED_EMBEDDED,
            )
            return InventoryRecordResponse.from_stored_inventory(record)

        _validate_chunk_settings(
            chunk_type=chunk_type,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            n_results=n_results,
        )
        next_chunk_size = chunk_size if chunk_type == CHUNK_TYPE_CUSTOM else 0
        next_chunk_overlap = chunk_overlap if chunk_type == CHUNK_TYPE_CUSTOM else DEFAULT_CHUNK_OVERLAP
        record = create_inventory_record(
            database_path,
            inventory_name=inventory_name,
            inventory_file=saved_filename,
            file_ext=extract_file_ext(saved_filename),
            chunk_type=chunk_type,
            chunk_size=next_chunk_size,
            chunk_overlap=next_chunk_overlap,
            n_results=n_results,
            db_type=DB_TYPE_VECTOR,
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

    normalized_db_type = _normalize_db_type(payload.db_type or existing.effective_db_type)
    if existing.effective_db_type == DB_TYPE_TABLE or normalized_db_type == DB_TYPE_TABLE:
        updated = update_inventory_record(
            database_path,
            idx,
            inventory_name=payload.inventory_name,
            db_type=DB_TYPE_TABLE,
            modified=existing.modified,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")
        return InventoryRecordResponse.from_stored_inventory(updated)

    _validate_chunk_settings(
        chunk_type=payload.chunk_type,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        n_results=payload.n_results,
    )

    next_chunk_size = payload.chunk_size if payload.chunk_type == CHUNK_TYPE_CUSTOM else 0
    next_chunk_overlap = (
        payload.chunk_overlap if payload.chunk_type == CHUNK_TYPE_CUSTOM else DEFAULT_CHUNK_OVERLAP
    )
    next_modified = existing.modified
    if _needs_reembed(
        existing,
        inventory_file=None,
        chunk_type=payload.chunk_type,
        chunk_size=next_chunk_size,
        chunk_overlap=next_chunk_overlap,
    ):
        next_modified = MODIFIED_NEEDS_EMBED

    updated = update_inventory_record(
        database_path,
        idx,
        inventory_name=payload.inventory_name,
        chunk_type=payload.chunk_type,
        chunk_size=next_chunk_size,
        chunk_overlap=next_chunk_overlap,
        n_results=payload.n_results,
        db_type=DB_TYPE_VECTOR,
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
    db_type: str = Form(DB_TYPE_VECTOR),
    chunk_type: int = Form(CHUNK_TYPE_ROW),
    chunk_size: int = Form(0),
    chunk_overlap: int = Form(DEFAULT_CHUNK_OVERLAP),
    n_results: int = Form(DEFAULT_N_RESULTS),
    file: UploadFile | None = File(None),
) -> InventoryRecordResponse:
    database_path = request.app.state.database_path
    service = _get_inventory_service(request)
    existing = get_stored_inventory_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    normalized_db_type = _normalize_db_type(db_type or existing.effective_db_type)
    next_inventory_file = existing.inventory_file
    next_file_ext = existing.file_ext
    next_modified = existing.modified

    if normalized_db_type == DB_TYPE_TABLE:
        if file is not None and file.filename:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="업로드할 파일이 비어 있습니다.")
            _validate_upload_size(content)
            if extract_file_ext(file.filename) != "csv":
                raise HTTPException(status_code=400, detail="table 방식은 CSV 파일만 업로드할 수 있습니다.")

            old_table = table_name_from_filename(existing.inventory_file)
            if existing.inventory_file and existing.inventory_file != Path(file.filename).name:
                service.delete_uploaded_file(existing.inventory_file)
                drop_inventory_data_table(database_path, old_table)

            try:
                next_inventory_file = service.save_uploaded_file(filename=file.filename, content=content)
                next_file_ext = extract_file_ext(next_inventory_file)
                import_csv_to_sqlite_table(
                    database_path,
                    filename=next_inventory_file,
                    content=content,
                )
                next_modified = MODIFIED_EMBEDDED
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        updated = update_inventory_record(
            database_path,
            idx,
            inventory_name=inventory_name,
            inventory_file=next_inventory_file,
            file_ext=next_file_ext,
            chunk_type=CHUNK_TYPE_ROW,
            chunk_size=0,
            chunk_overlap=DEFAULT_CHUNK_OVERLAP,
            n_results=DEFAULT_N_RESULTS,
            db_type=DB_TYPE_TABLE,
            modified=next_modified,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")
        return InventoryRecordResponse.from_stored_inventory(updated)

    _validate_chunk_settings(
        chunk_type=chunk_type,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        n_results=n_results,
    )
    next_chunk_size = chunk_size if chunk_type == CHUNK_TYPE_CUSTOM else 0
    next_chunk_overlap = chunk_overlap if chunk_type == CHUNK_TYPE_CUSTOM else DEFAULT_CHUNK_OVERLAP

    if file is not None and file.filename:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="업로드할 파일이 비어 있습니다.")
        _validate_upload_size(content)

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
        chunk_overlap=next_chunk_overlap,
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
        chunk_overlap=next_chunk_overlap,
        n_results=n_results,
        db_type=DB_TYPE_VECTOR,
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
        logger.warning("Inventory embed rejected: record not found idx=%s", idx)
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    status_info = service.get_status_info()
    logger.info(
        "Inventory embed request idx=%s name=%s file=%s ext=%s chunk_type=%s chunk_size=%s "
        "chunk_overlap=%s modified=%s service_status=%s upload_path=%s chroma_path=%s document_count=%s",
        record.idx,
        record.inventory_name,
        record.inventory_file,
        record.file_ext,
        record.chunk_type,
        record.chunk_size,
        record.chunk_overlap,
        record.modified,
        status_info.get("status"),
        status_info.get("upload_path"),
        status_info.get("chroma_data_path"),
        status_info.get("document_count"),
    )

    if record.effective_db_type == DB_TYPE_TABLE:
        raise HTTPException(status_code=400, detail="table 방식 인벤토리는 Embedding을 지원하지 않습니다.")

    if record.modified != MODIFIED_NEEDS_EMBED:
        logger.warning(
            "Inventory embed rejected idx=%s modified=%s expected=%s",
            record.idx,
            record.modified,
            MODIFIED_NEEDS_EMBED,
        )
        raise HTTPException(status_code=400, detail="임베딩이 필요한 상태가 아닙니다.")

    try:
        embedded_rows = service.embed_inventory_record(
            inventory_idx=record.idx,
            filename=record.inventory_file,
            chunk_type=record.chunk_type,
            chunk_size=record.chunk_size,
            chunk_overlap=record.chunk_overlap,
        )
    except FileNotFoundError as exc:
        logger.error(
            "Inventory embed file missing idx=%s file=%s upload_path=%s detail=%s",
            record.idx,
            record.inventory_file,
            status_info.get("upload_path"),
            exc,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error(
            "Inventory embed validation failed idx=%s file=%s chunk_type=%s chunk_size=%s detail=%s",
            record.idx,
            record.inventory_file,
            record.chunk_type,
            record.chunk_size,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception(
            "Inventory embed service unavailable idx=%s file=%s service_status=%s service_error=%s",
            record.idx,
            record.inventory_file,
            status_info.get("status"),
            status_info.get("error"),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Inventory embed failed idx=%s file=%s chunk_type=%s chunk_size=%s "
            "upload_path=%s chroma_path=%s service_status=%s",
            record.idx,
            record.inventory_file,
            record.chunk_type,
            record.chunk_size,
            status_info.get("upload_path"),
            status_info.get("chroma_data_path"),
            status_info.get("status"),
        )
        raise HTTPException(status_code=500, detail=f"Embedding 실패: {exc}") from exc

    updated = update_inventory_modified(database_path, idx, MODIFIED_EMBEDDED)
    if updated is None:
        logger.error("Inventory embed DB update failed idx=%s embedded_rows=%s", idx, embedded_rows)
        raise HTTPException(status_code=404, detail="인벤토리 레코드를 찾을 수 없습니다.")

    logger.info(
        "Inventory embed completed idx=%s file=%s embedded_rows=%s document_count=%s",
        record.idx,
        record.inventory_file,
        embedded_rows,
        service.document_count,
    )

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
        if record.effective_db_type == DB_TYPE_TABLE:
            drop_inventory_data_table(database_path, table_name_from_filename(record.inventory_file))
        else:
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
