from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.job_datetime import normalize_job_datetime, now_job_datetime
from backend.app.db.notice_board import (
    Notice,
    create_notice,
    delete_notices,
    get_notice_by_idx,
    list_notices,
    update_notice,
    update_notice_welcome_popup,
)
from backend.app.db.roles import ROLE_ADMIN
from backend.app.db.users import build_userid_username_map, get_user_by_userid, resolve_username

router = APIRouter(tags=["notices"])


class NoticeResponse(BaseModel):
    idx: int
    writer: str
    writer_name: str | None = None
    write_date: str
    from_date: str
    until_date: str
    title: str
    notice: str
    welcome_popup: bool

    @classmethod
    def from_notice(
        cls,
        notice: Notice,
        *,
        username_by_key: dict[str, str] | None = None,
    ) -> "NoticeResponse":
        writer_name = notice.writer
        if username_by_key is not None:
            writer_name = resolve_username(notice.writer, username_by_key)
        return cls(
            idx=notice.idx,
            writer=notice.writer,
            writer_name=writer_name,
            write_date=notice.write_date,
            from_date=notice.from_date,
            until_date=notice.until_date,
            title=notice.title,
            notice=notice.notice,
            welcome_popup=notice.welcome_popup,
        )


class CreateNoticeRequest(BaseModel):
    writer: str = Field(min_length=1, max_length=50)
    from_date: str = Field(min_length=1)
    until_date: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    notice: str = ""
    welcome_popup: bool = False
    viewer_role: int


class UpdateNoticeRequest(BaseModel):
    from_date: str = Field(min_length=1)
    until_date: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    notice: str = ""
    welcome_popup: bool = False
    viewer_role: int


class WelcomePopupUpdateRequest(BaseModel):
    welcome_popup: bool
    viewer_role: int


class DeleteNoticesRequest(BaseModel):
    idx_list: list[int] = Field(min_length=1)
    viewer_role: int


def _require_admin(viewer_role: int) -> None:
    if viewer_role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _username_map(request: Request) -> dict[str, str]:
    return build_userid_username_map(request.app.state.database_path)


def _normalize_period(value: str) -> str:
    try:
        return normalize_job_datetime(value, default_time="00:00:00")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"날짜/시간 형식이 올바르지 않습니다: {value}") from exc


@router.get("/notices", response_model=list[NoticeResponse])
async def get_notices(request: Request) -> list[NoticeResponse]:
    database_path = request.app.state.database_path
    username_by_key = _username_map(request)
    return [
        NoticeResponse.from_notice(notice, username_by_key=username_by_key)
        for notice in list_notices(database_path)
    ]


@router.get("/notices/{idx}", response_model=NoticeResponse)
async def get_notice(idx: int, request: Request) -> NoticeResponse:
    database_path = request.app.state.database_path
    notice = get_notice_by_idx(database_path, idx)
    if notice is None:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")
    return NoticeResponse.from_notice(notice, username_by_key=_username_map(request))


@router.post("/notices", response_model=NoticeResponse, status_code=201)
async def add_notice(payload: CreateNoticeRequest, request: Request) -> NoticeResponse:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    writer = payload.writer.strip()
    if get_user_by_userid(database_path, writer) is None:
        raise HTTPException(status_code=400, detail="작성자 userid를 확인할 수 없습니다.")

    notice = create_notice(
        database_path,
        writer=writer,
        write_date=now_job_datetime(),
        from_date=_normalize_period(payload.from_date),
        until_date=_normalize_period(payload.until_date),
        title=payload.title,
        notice=payload.notice,
        welcome_popup=payload.welcome_popup,
    )
    return NoticeResponse.from_notice(notice, username_by_key=_username_map(request))


@router.put("/notices/{idx}", response_model=NoticeResponse)
async def modify_notice(idx: int, payload: UpdateNoticeRequest, request: Request) -> NoticeResponse:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    existing = get_notice_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")

    updated = update_notice(
        database_path,
        idx,
        writer=existing.writer,
        write_date=existing.write_date,
        from_date=_normalize_period(payload.from_date),
        until_date=_normalize_period(payload.until_date),
        title=payload.title,
        notice=payload.notice,
        welcome_popup=payload.welcome_popup,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")
    return NoticeResponse.from_notice(updated, username_by_key=_username_map(request))


@router.patch("/notices/{idx}/welcome-popup", response_model=NoticeResponse)
async def patch_welcome_popup(
    idx: int,
    payload: WelcomePopupUpdateRequest,
    request: Request,
) -> NoticeResponse:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    updated = update_notice_welcome_popup(
        database_path,
        idx,
        welcome_popup=payload.welcome_popup,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")
    return NoticeResponse.from_notice(updated, username_by_key=_username_map(request))


@router.delete("/notices")
async def remove_notices(
    request: Request,
    payload: DeleteNoticesRequest = Body(...),
) -> dict[str, int]:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    deleted = delete_notices(database_path, payload.idx_list)
    return {"deleted": deleted}
