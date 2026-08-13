"""APIs for received_mail rows and attachment download (JOB_DECISION_AGENT TBD)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from backend.app.db.received_mail import (
    VALID_DECISION_TYPES,
    get_received_mail_by_uuid,
    list_received_mail,
    update_decision_type,
)
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.received_mail_attachments import resolve_attachment_file

router = APIRouter(tags=["received-mail"])


class ReceivedMailResponse(BaseModel):
    idx: int
    uuid: str
    decision_type: int
    message_id: str
    imap_uid: int | None = None
    mailbox: str
    subject: str
    from_address: str
    to_addresses: str
    cc_addresses: str
    body_text: str
    received_at: str
    fetched_at: str
    attachment_count: int
    attachment_names: list[str] = Field(default_factory=list)


class ReceivedMailDecisionUpdate(BaseModel):
    """0=pending, 5=insufficient, 10=job, 11=non-job."""

    decision_type: int

    @model_validator(mode="after")
    def validate_decision_type(self) -> "ReceivedMailDecisionUpdate":
        if self.decision_type not in VALID_DECISION_TYPES:
            raise ValueError(
                "decision_type은 0(대기), 5(자료부족), 10(작업), 11(비작업)만 허용됩니다."
            )
        return self


def _to_response(record) -> ReceivedMailResponse:
    return ReceivedMailResponse(
        idx=record.idx,
        uuid=record.uuid,
        decision_type=record.decision_type,
        message_id=record.message_id,
        imap_uid=record.imap_uid,
        mailbox=record.mailbox,
        subject=record.subject,
        from_address=record.from_address,
        to_addresses=record.to_addresses,
        cc_addresses=record.cc_addresses,
        body_text=record.body_text,
        received_at=record.received_at,
        fetched_at=record.fetched_at,
        attachment_count=record.attachment_count,
        attachment_names=list(record.attachment_names),
    )


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


@router.get("/received-mail", response_model=list[ReceivedMailResponse])
async def api_list_received_mail(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision_type: int | None = Query(default=None),
) -> list[ReceivedMailResponse]:
    _require_admin(request)
    if decision_type is not None and decision_type not in VALID_DECISION_TYPES:
        raise HTTPException(status_code=400, detail="decision_type 값이 올바르지 않습니다.")
    records = list_received_mail(
        request.app.state.database_path,
        limit=limit,
        offset=offset,
        decision_type=decision_type,
    )
    return [_to_response(record) for record in records]


@router.get("/received-mail/{mail_uuid}", response_model=ReceivedMailResponse)
async def api_get_received_mail(request: Request, mail_uuid: str) -> ReceivedMailResponse:
    _require_admin(request)
    record = get_received_mail_by_uuid(request.app.state.database_path, mail_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="수신 메일을 찾을 수 없습니다.")
    return _to_response(record)


@router.patch("/received-mail/{mail_uuid}/decision", response_model=ReceivedMailResponse)
async def api_update_received_mail_decision(
    request: Request,
    mail_uuid: str,
    payload: ReceivedMailDecisionUpdate,
) -> ReceivedMailResponse:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 변경할 수 있습니다.")
    try:
        record = update_decision_type(
            request.app.state.database_path,
            mail_uuid,
            payload.decision_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="수신 메일을 찾을 수 없습니다.")
    return _to_response(record)


@router.get("/received-mail/{mail_uuid}/attachments/{filename}")
async def api_download_received_mail_attachment(
    request: Request,
    mail_uuid: str,
    filename: str,
) -> FileResponse:
    """Download a stored attachment. Path layout: {home}/{uuid}/{filename}."""
    _require_admin(request)
    record = get_received_mail_by_uuid(request.app.state.database_path, mail_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="수신 메일을 찾을 수 없습니다.")

    safe_requested = filename.strip()
    if safe_requested not in record.attachment_names:
        raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다.")

    try:
        path = resolve_attachment_file(record.uuid, safe_requested)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not path.is_file():
        raise HTTPException(status_code=404, detail="첨부 파일이 디스크에 없습니다.")

    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
    )
