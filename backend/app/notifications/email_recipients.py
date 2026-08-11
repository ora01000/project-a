"""Shared recipient resolution for markdown email APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from backend.app.db.users import get_user_by_idx


class SendMarkdownEmailResponse(BaseModel):
    sent_count: int
    failed_recipients: list[str] = Field(default_factory=list)
    message: str


class SendEmailRecipientsRequest(BaseModel):
    recipient_user_idxs: list[int] = Field(default_factory=list)
    include_requester: bool = False

    @model_validator(mode="after")
    def validate_recipients(self) -> "SendEmailRecipientsRequest":
        if not self.include_requester and not self.recipient_user_idxs:
            raise ValueError("수신자를 한 명 이상 선택해 주세요.")
        return self


def resolve_recipient_emails(
    database_path,
    body: SendEmailRecipientsRequest,
    *,
    requester_email: str | None = None,
) -> list[str]:
    recipient_emails: list[str] = []
    if body.include_requester:
        normalized_requester = (requester_email or "").strip()
        if not normalized_requester or "@" not in normalized_requester:
            raise ValueError("SR 기안자 이메일이 유효하지 않습니다.")
        recipient_emails.append(normalized_requester)

    for user_idx in body.recipient_user_idxs:
        user = get_user_by_idx(database_path, user_idx)
        if user is None:
            raise ValueError(f"사용자를 찾을 수 없습니다 (idx={user_idx}).")
        email = user.email.strip()
        if not email or "@" not in email:
            raise ValueError(f"유효한 이메일이 없는 사용자입니다: {user.username}({user.userid})")
        recipient_emails.append(email)

    return recipient_emails
