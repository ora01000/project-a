"""Admin API for SMTP/IMAP/POP3 mailserver_config and test send."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from backend.app.config import EmailNotificationSettings, resolve_agent_runtime_mode
from backend.app.db.mailserver_config import (
    RECEIVE_PROTOCOL_IMAP,
    RECEIVE_PROTOCOL_POP3,
    VALID_RECEIVE_PROTOCOLS,
    get_mailserver_config,
    normalized_receive_protocol,
    save_mailserver_config,
)
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.notifications.email_sender import send_test_email
from backend.app.services.agent_runtime_client import normalize_runtime_mode

router = APIRouter(tags=["mailserver"])


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _suggested_profile() -> str:
    mode = normalize_runtime_mode(resolve_agent_runtime_mode())
    if mode in {"mock", "local"}:
        return "gmail"
    return "internal"


class MailserverConfigResponse(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    from_address: str = ""
    smtp_auth: bool = True
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 30.0
    receive_enabled: bool = False
    receive_protocol: str = RECEIVE_PROTOCOL_IMAP
    imap_host: str = ""
    imap_port: int = 993
    imap_use_ssl: bool = True
    pop3_host: str = ""
    pop3_port: int = 995
    pop3_use_ssl: bool = True
    pop3_leave_on_server: bool = True
    updated_at: str = ""
    has_password: bool = False
    suggested_profile: str = "gmail"
    """gmail (mock/local) or internal (http)."""


class MailserverConfigUpdateRequest(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    """Empty password keeps the stored value."""
    smtp_password: str | None = None
    from_address: str = ""
    smtp_auth: bool = True
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = Field(default=30.0, gt=0)
    receive_enabled: bool = False
    receive_protocol: str = RECEIVE_PROTOCOL_IMAP
    imap_host: str = ""
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_use_ssl: bool = True
    pop3_host: str = ""
    pop3_port: int = Field(default=995, ge=1, le=65535)
    pop3_use_ssl: bool = True
    pop3_leave_on_server: bool = True

    @field_validator("receive_protocol")
    @classmethod
    def validate_receive_protocol(cls, value: str) -> str:
        protocol = normalized_receive_protocol(value)
        if protocol not in VALID_RECEIVE_PROTOCOLS:
            raise ValueError("receive_protocol은 imap 또는 pop3만 허용됩니다.")
        return protocol


class MailTestRequest(BaseModel):
    to_address: str = Field(min_length=3)
    subject: str = "AX 인프라 운영 콘솔 테스트 메일"
    body: str = "메일 서버 설정 테스트입니다."


class MailTestResponse(BaseModel):
    ok: bool
    message: str


def _to_response(row) -> MailserverConfigResponse:
    profile = _suggested_profile()
    if row is None:
        if profile == "gmail":
            return MailserverConfigResponse(
                enabled=False,
                smtp_host="smtp.gmail.com",
                smtp_port=587,
                smtp_auth=True,
                use_tls=True,
                use_ssl=False,
                receive_enabled=False,
                receive_protocol=RECEIVE_PROTOCOL_IMAP,
                imap_host="imap.gmail.com",
                imap_port=993,
                imap_use_ssl=True,
                suggested_profile=profile,
            )
        return MailserverConfigResponse(
            enabled=False,
            smtp_host="",
            smtp_port=587,
            smtp_auth=True,
            use_tls=True,
            use_ssl=False,
            receive_enabled=False,
            receive_protocol=RECEIVE_PROTOCOL_IMAP,
            imap_host="",
            imap_port=993,
            imap_use_ssl=True,
            suggested_profile=profile,
        )
    return MailserverConfigResponse(
        enabled=row.enabled,
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_username=row.smtp_username,
        from_address=row.from_address,
        smtp_auth=row.smtp_auth,
        use_tls=row.use_tls,
        use_ssl=row.use_ssl,
        timeout_seconds=row.timeout_seconds,
        receive_enabled=row.receive_enabled,
        receive_protocol=row.receive_protocol,
        imap_host=row.imap_host,
        imap_port=row.imap_port,
        imap_use_ssl=row.imap_use_ssl,
        pop3_host=row.pop3_host,
        pop3_port=row.pop3_port,
        pop3_use_ssl=row.pop3_use_ssl,
        pop3_leave_on_server=row.pop3_leave_on_server,
        updated_at=row.updated_at,
        has_password=row.has_password,
        suggested_profile=profile,
    )


@router.get("/admin/mailserver-config", response_model=MailserverConfigResponse)
async def admin_get_mailserver_config(request: Request) -> MailserverConfigResponse:
    _require_admin(request)
    row = get_mailserver_config(request.app.state.database_path)
    return _to_response(row)


@router.put("/admin/mailserver-config", response_model=MailserverConfigResponse)
async def admin_put_mailserver_config(
    request: Request,
    payload: MailserverConfigUpdateRequest,
) -> MailserverConfigResponse:
    _require_admin(request)
    if not payload.smtp_host.strip():
        raise HTTPException(status_code=400, detail="SMTP 호스트를 입력해 주세요.")
    if not payload.from_address.strip():
        raise HTTPException(status_code=400, detail="발신 주소를 입력해 주세요.")
    if payload.smtp_auth and not payload.smtp_username.strip():
        raise HTTPException(status_code=400, detail="SMTP 인증 사용 시 사용자명을 입력해 주세요.")
    if payload.receive_enabled and not payload.smtp_username.strip():
        raise HTTPException(status_code=400, detail="메일 수신 활성화 시 계정 사용자명을 입력해 주세요.")

    protocol = normalized_receive_protocol(payload.receive_protocol)
    if payload.receive_enabled and protocol == RECEIVE_PROTOCOL_IMAP and not payload.imap_host.strip():
        raise HTTPException(status_code=400, detail="IMAP 수신 시 IMAP 호스트를 입력해 주세요.")
    if payload.receive_enabled and protocol == RECEIVE_PROTOCOL_POP3 and not payload.pop3_host.strip():
        raise HTTPException(status_code=400, detail="POP3 수신 시 POP3 호스트를 입력해 주세요.")

    row = save_mailserver_config(
        request.app.state.database_path,
        enabled=payload.enabled,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        smtp_username=payload.smtp_username,
        smtp_password=payload.smtp_password,
        from_address=payload.from_address,
        smtp_auth=payload.smtp_auth,
        use_tls=payload.use_tls,
        use_ssl=payload.use_ssl,
        timeout_seconds=payload.timeout_seconds,
        receive_enabled=payload.receive_enabled,
        receive_protocol=protocol,
        imap_host=payload.imap_host,
        imap_port=payload.imap_port,
        imap_use_ssl=payload.imap_use_ssl,
        pop3_host=payload.pop3_host,
        pop3_port=payload.pop3_port,
        pop3_use_ssl=payload.pop3_use_ssl,
        pop3_leave_on_server=payload.pop3_leave_on_server,
    )
    return _to_response(row)


@router.post("/admin/mailserver-test", response_model=MailTestResponse)
async def admin_mailserver_test(
    request: Request,
    payload: MailTestRequest,
) -> MailTestResponse:
    _require_admin(request)
    to_address = payload.to_address.strip()
    if "@" not in to_address:
        raise HTTPException(status_code=400, detail="수신 이메일 주소가 올바르지 않습니다.")

    row = get_mailserver_config(request.app.state.database_path)
    if row is None:
        raise HTTPException(status_code=400, detail="메일 서버 설정이 없습니다. 먼저 저장해 주세요.")

    settings = EmailNotificationSettings(
        enabled=True,
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_username=row.smtp_username,
        smtp_password=row.smtp_password,
        from_address=row.from_address,
        smtp_auth=row.smtp_auth,
        use_tls=row.use_tls,
        use_ssl=row.use_ssl,
        timeout_seconds=row.timeout_seconds,
    )
    ok, message = await send_test_email(
        settings=settings,
        to_address=to_address,
        subject=payload.subject.strip() or "AX 인프라 운영 콘솔 테스트 메일",
        body=payload.body.strip() or "메일 서버 설정 테스트입니다.",
    )
    if not ok:
        raise HTTPException(status_code=502, detail=message)
    return MailTestResponse(ok=True, message=message)
