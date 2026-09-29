"""Shared recipient resolution for markdown email APIs."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator

from backend.app.db.roles import ROLE_PENDING
from backend.app.db.users import get_user_by_idx


class SendMarkdownEmailResponse(BaseModel):
    sent_count: int
    failed_recipients: list[str] = Field(default_factory=list)
    message: str


class SendEmailRecipientsRequest(BaseModel):
    recipient_user_idxs: list[int] = Field(default_factory=list)
    cc_user_idxs: list[int] = Field(default_factory=list)
    bcc_user_idxs: list[int] = Field(default_factory=list)
    to_emails: list[str] = Field(default_factory=list)
    cc_emails: list[str] = Field(default_factory=list)
    bcc_emails: list[str] = Field(default_factory=list)
    include_requester: bool = False
    subject: str | None = Field(default=None, max_length=300)
    forward_message: str = ""

    @model_validator(mode="after")
    def validate_recipients(self) -> "SendEmailRecipientsRequest":
        if (
            not self.include_requester
            and not self.recipient_user_idxs
            and not self.to_emails
        ):
            raise ValueError("수신자를 한 명 이상 선택해 주세요.")
        return self


@dataclass(frozen=True)
class ResolvedEmailRecipients:
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]


def _resolve_user_email(database_path, user_idx: int) -> str:
    user = get_user_by_idx(database_path, user_idx)
    if user is None:
        raise ValueError(f"사용자를 찾을 수 없습니다 (idx={user_idx}).")
    if user.role == ROLE_PENDING:
        raise ValueError(f"보류 상태 사용자는 수신자로 선택할 수 없습니다: {user.username}({user.userid})")
    email = user.email.strip()
    if not email or "@" not in email:
        raise ValueError(f"유효한 이메일이 없는 사용자입니다: {user.username}({user.userid})")
    return email


def _normalize_freeform_email(raw: str) -> str:
    email = raw.strip()
    if not email:
        raise ValueError("빈 이메일 주소는 사용할 수 없습니다.")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError(f"유효하지 않은 이메일 주소입니다: {email}")
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError(f"유효하지 않은 이메일 주소입니다: {email}")
    return email


def _unique_emails(addresses: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for address in addresses:
        normalized = address.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def resolve_email_recipients(
    database_path,
    body: SendEmailRecipientsRequest,
    *,
    requester_email: str | None = None,
) -> ResolvedEmailRecipients:
    to_addresses: list[str] = []
    if body.include_requester:
        normalized_requester = (requester_email or "").strip()
        if not normalized_requester or "@" not in normalized_requester:
            raise ValueError("SR 기안자 이메일이 유효하지 않습니다.")
        to_addresses.append(normalized_requester)

    for user_idx in body.recipient_user_idxs:
        to_addresses.append(_resolve_user_email(database_path, user_idx))
    for raw in body.to_emails:
        to_addresses.append(_normalize_freeform_email(raw))

    cc_addresses = [_resolve_user_email(database_path, user_idx) for user_idx in body.cc_user_idxs]
    cc_addresses.extend(_normalize_freeform_email(raw) for raw in body.cc_emails)

    bcc_addresses = [_resolve_user_email(database_path, user_idx) for user_idx in body.bcc_user_idxs]
    bcc_addresses.extend(_normalize_freeform_email(raw) for raw in body.bcc_emails)

    return ResolvedEmailRecipients(
        to_addresses=_unique_emails(to_addresses),
        cc_addresses=_unique_emails(cc_addresses),
        bcc_addresses=_unique_emails(bcc_addresses),
    )


def resolve_recipient_emails(
    database_path,
    body: SendEmailRecipientsRequest,
    *,
    requester_email: str | None = None,
) -> list[str]:
    """Backward-compatible helper returning all TO addresses."""
    resolved = resolve_email_recipients(database_path, body, requester_email=requester_email)
    return resolved.to_addresses
