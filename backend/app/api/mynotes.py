"""Personal notes API for the job notes workspace."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.app.db.mynotes import (
    MyNoteRecord,
    create_mynote,
    delete_mynote,
    get_mynote_by_idx,
    list_mynotes,
    read_mynote_content,
    save_mynote_content,
    update_mynote_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mynotes"])


class MyNoteResponse(BaseModel):
    idx: int
    userid: str
    note_name: str
    create_date: str
    origin_file: str
    last_update: str

    @classmethod
    def from_record(cls, record: MyNoteRecord) -> "MyNoteResponse":
        return cls(
            idx=record.idx,
            userid=record.userid,
            note_name=record.note_name,
            create_date=record.create_date,
            origin_file=record.origin_file,
            last_update=record.last_update,
        )


class MyNoteDetailResponse(MyNoteResponse):
    content: str

    @classmethod
    def from_record(cls, record: MyNoteRecord, *, content: str) -> "MyNoteDetailResponse":
        return cls(
            idx=record.idx,
            userid=record.userid,
            note_name=record.note_name,
            create_date=record.create_date,
            origin_file=record.origin_file,
            last_update=record.last_update,
            content=content,
        )


class CreateMyNoteRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    note_name: str | None = Field(default=None, max_length=50)


class RenameMyNoteRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    note_name: str = Field(min_length=1, max_length=50)


class SaveMyNoteContentRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    content: str = ""


@router.get("/mynotes", response_model=list[MyNoteResponse])
async def list_my_notes(
    request: Request,
    userid: str = Query(min_length=1, max_length=50),
) -> list[MyNoteResponse]:
    database_path = request.app.state.database_path
    records = list_mynotes(database_path, userid=userid)
    return [MyNoteResponse.from_record(record) for record in records]


@router.post("/mynotes", response_model=MyNoteDetailResponse, status_code=201)
async def create_my_note(
    request: Request,
    body: CreateMyNoteRequest,
) -> MyNoteDetailResponse:
    database_path = request.app.state.database_path
    try:
        record = create_mynote(
            database_path,
            userid=body.userid,
            note_name=body.note_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("My note create failed")
        raise HTTPException(status_code=500, detail="Failed to create note") from exc
    return MyNoteDetailResponse.from_record(record, content="")


@router.get("/mynotes/{idx}", response_model=MyNoteDetailResponse)
async def get_my_note(
    request: Request,
    idx: int,
    userid: str = Query(min_length=1, max_length=50),
) -> MyNoteDetailResponse:
    database_path = request.app.state.database_path
    record = get_mynote_by_idx(database_path, idx)
    if record is None or record.userid != userid.strip():
        raise HTTPException(status_code=404, detail="Note not found")
    content = read_mynote_content(record)
    return MyNoteDetailResponse.from_record(record, content=content)


@router.put("/mynotes/{idx}/content", response_model=MyNoteResponse)
async def save_my_note_content(
    request: Request,
    idx: int,
    body: SaveMyNoteContentRequest,
) -> MyNoteResponse:
    database_path = request.app.state.database_path
    try:
        record = save_mynote_content(
            database_path,
            idx,
            userid=body.userid,
            content=body.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("My note content save failed")
        raise HTTPException(status_code=500, detail="Failed to save note content") from exc
    return MyNoteResponse.from_record(record)


@router.patch("/mynotes/{idx}", response_model=MyNoteResponse)
async def rename_my_note(
    request: Request,
    idx: int,
    body: RenameMyNoteRequest,
) -> MyNoteResponse:
    database_path = request.app.state.database_path
    try:
        record = update_mynote_name(
            database_path,
            idx,
            userid=body.userid,
            note_name=body.note_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("My note rename failed")
        raise HTTPException(status_code=500, detail="Failed to rename note") from exc
    return MyNoteResponse.from_record(record)


@router.delete("/mynotes/{idx}", status_code=204)
async def delete_my_note(
    request: Request,
    idx: int,
    userid: str = Query(min_length=1, max_length=50),
) -> None:
    database_path = request.app.state.database_path
    try:
        delete_mynote(database_path, idx, userid=userid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("My note delete failed")
        raise HTTPException(status_code=500, detail="Failed to delete note") from exc
