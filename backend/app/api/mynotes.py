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
    touch_mynote_last_update,
    update_mynote_name,
)
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.notifications.email_recipients import (
    SendEmailRecipientsRequest,
    SendMarkdownEmailResponse,
    resolve_recipient_emails,
)
from backend.app.notifications.email_sender import send_job_report_emails
from backend.app.services.mynote_content_store import (
    delete_mynote_content_from_redis,
    hydrate_mynote_content,
    rename_mynote_content_in_redis,
    set_mynote_content_in_redis,
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


class SendMyNoteEmailRequest(SendEmailRecipientsRequest):
    userid: str = Field(min_length=1, max_length=50)


async def _load_mynote_content(record: MyNoteRecord, database_path) -> str:
    file_content = read_mynote_content(record, database_path=database_path)
    return await hydrate_mynote_content(record, file_content=file_content)


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
        await set_mynote_content_in_redis(record.userid, record.note_name, "")
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
    content = await _load_mynote_content(record, database_path)
    return MyNoteDetailResponse.from_record(record, content=content)


@router.put("/mynotes/{idx}/content", response_model=MyNoteResponse)
async def save_my_note_content(
    request: Request,
    idx: int,
    body: SaveMyNoteContentRequest,
) -> MyNoteResponse:
    database_path = request.app.state.database_path
    existing = get_mynote_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if existing.userid != body.userid.strip():
        raise HTTPException(status_code=403, detail="Note does not belong to this user")

    try:
        await set_mynote_content_in_redis(existing.userid, existing.note_name, body.content)
        record = touch_mynote_last_update(
            database_path,
            idx,
            userid=body.userid,
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
    existing = get_mynote_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if existing.userid != body.userid.strip():
        raise HTTPException(status_code=403, detail="Note does not belong to this user")

    old_note_name = existing.note_name
    try:
        await hydrate_mynote_content(
            existing,
            file_content=read_mynote_content(existing, database_path=database_path),
        )
        record = update_mynote_name(
            database_path,
            idx,
            userid=body.userid,
            note_name=body.note_name,
        )
        await rename_mynote_content_in_redis(
            existing.userid,
            old_note_name=old_note_name,
            new_note_name=record.note_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("My note rename failed")
        raise HTTPException(status_code=500, detail="Failed to rename note") from exc
    return MyNoteResponse.from_record(record)


@router.post("/mynotes/{idx}/send-email", response_model=SendMarkdownEmailResponse)
async def send_my_note_email(
    request: Request,
    idx: int,
    body: SendMyNoteEmailRequest,
) -> SendMarkdownEmailResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_mynote_by_idx(database_path, idx)
    if record is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if record.userid != body.userid.strip():
        raise HTTPException(status_code=403, detail="Note does not belong to this user")

    content = await _load_mynote_content(record, database_path)
    if not content.strip():
        raise HTTPException(status_code=400, detail="노트 내용이 비어 있습니다.")

    try:
        recipient_emails = resolve_recipient_emails(database_path, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        sent_count, failed = await send_job_report_emails(
            database_path=database_path,
            recipient_emails=recipient_emails,
            subject=record.note_name.strip(),
            markdown_body=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("My note email send failed for note=%s", idx)
        raise HTTPException(status_code=502, detail="메일 전송에 실패했습니다.") from exc

    if sent_count == 0:
        raise HTTPException(
            status_code=502,
            detail=f"메일 전송에 실패했습니다: {', '.join(failed)}",
        )

    message = f"{sent_count}명에게 메일을 전송했습니다."
    if failed:
        message = f"{message} (실패: {', '.join(failed)})"
    return SendMarkdownEmailResponse(
        sent_count=sent_count,
        failed_recipients=failed,
        message=message,
    )


@router.delete("/mynotes/{idx}", status_code=204)
async def delete_my_note(
    request: Request,
    idx: int,
    userid: str = Query(min_length=1, max_length=50),
) -> None:
    database_path = request.app.state.database_path
    existing = get_mynote_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if existing.userid != userid.strip():
        raise HTTPException(status_code=403, detail="Note does not belong to this user")

    try:
        await delete_mynote_content_from_redis(existing.userid, existing.note_name)
        delete_mynote(database_path, idx, userid=userid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("My note delete failed")
        raise HTTPException(status_code=500, detail="Failed to delete note") from exc
