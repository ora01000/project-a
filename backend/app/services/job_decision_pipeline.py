"""After received_mail insert: evaluate pending rows and apply decision side effects."""

from __future__ import annotations

import logging
from email.utils import getaddresses
from pathlib import Path
from typing import Any

from backend.app.db.job_datetime import now_job_datetime
from backend.app.db.jobs import JOB_TYPE_AX_INFRA, JobIntakePayload, JobRecord, create_job_from_intake
from backend.app.db.received_mail import (
    DECISION_TYPE_INSUFFICIENT,
    DECISION_TYPE_JOB,
    DECISION_TYPE_NON_JOB,
    DECISION_TYPE_PENDING,
    ReceivedMailRecord,
    get_received_mail_by_uuid,
    list_pending_received_mail,
    update_decision_type,
)
from backend.app.db.roles import ROLE_ADMIN
from backend.app.db.users import list_users
from backend.app.job_decision_agent.agent import ParsedDecision, job_decision_agent_service
from backend.app.notifications.email_sender import send_job_supplement_request_email

logger = logging.getLogger(__name__)

UNKNOWN_DEPART = "확인 불가"
MAIL_TEAM_ID = "mail"
MAIL_CHANNEL_ID = "received_mail"


def extract_sender_email(from_address: str) -> str:
    for _name, addr in getaddresses([from_address or ""]):
        cleaned = (addr or "").strip()
        if "@" in cleaned and not cleaned.startswith("@") and not cleaned.endswith("@"):
            return cleaned
    return ""


def madang_id_from_email(email: str) -> str:
    local = (email or "").split("@", 1)[0].strip()
    return (local or "unknown")[:50]


def build_job_title(subject: str) -> str:
    title = (subject or "").strip() or "메일 작업 요청"
    return title[:300]


def build_job_content(record: ReceivedMailRecord, parsed: ParsedDecision) -> str:
    body = (record.body_text or "").strip() or "(empty)"
    lines = [
        body,
        "",
        "---",
        "[JOB_DECISION_AGENT]",
        f"infra: {parsed.infra}",
        f"job_kind: {parsed.job_kind}",
        f"summary: {parsed.summary}",
    ]
    if parsed.missing:
        lines.append("missing: " + ", ".join(parsed.missing))
    if record.unreadable_attachment_names:
        lines.append("unreadable_attachments: " + ", ".join(record.unreadable_attachment_names))
    return "\n".join(lines)


def create_job_from_received_mail(
    database_path: Path | str,
    record: ReceivedMailRecord,
    parsed: ParsedDecision,
) -> JobRecord:
    sender = extract_sender_email(record.from_address)
    if not sender:
        raise ValueError("sender email is required to create a job")
    payload = JobIntakePayload(
        job_title=build_job_title(record.subject),
        requester_name=sender[:100],
        requester_email=sender[:100],
        requester_depart=UNKNOWN_DEPART,
        job_content=build_job_content(record, parsed),
        request_date=now_job_datetime(),
        madang_id=madang_id_from_email(sender),
        team_id=MAIL_TEAM_ID,
        channel_id=MAIL_CHANNEL_ID,
        message_id=record.uuid[:50],
        job_type=JOB_TYPE_AX_INFRA,
    )
    return create_job_from_intake(database_path, payload)


def list_supplement_cc_emails(database_path: Path | str) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    for user in list_users(database_path, viewer_role=ROLE_ADMIN):
        if user.role != ROLE_ADMIN:
            continue
        address = (user.email or "").strip()
        if "@" not in address:
            continue
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        emails.append(address)
    return emails


def resolve_supplement_reply_body(parsed: ParsedDecision, record: ReceivedMailRecord) -> str:
    if parsed.reply_ko:
        return parsed.reply_ko
    if parsed.operator_ko:
        return parsed.operator_ko
    lines = ["작업 처리를 위해 아래 정보가 추가로 필요합니다."]
    missing = list(parsed.missing)
    if record.unreadable_attachment_names:
        missing.extend(
            f"텍스트로 읽을 수 없는 첨부({name}) — 텍스트 파일로 다시 보내 주세요"
            for name in record.unreadable_attachment_names
        )
    if missing:
        lines.append("")
        for item in missing:
            lines.append(f"- {item}")
    else:
        lines.append("요청 대상 식별 정보(클러스터/네임스페이스/VM 등)를 본문에 명시해 주세요.")
    return "\n".join(lines)


def apply_unreadable_attachment_rule(
    decision_type: int,
    record: ReceivedMailRecord,
    parsed: ParsedDecision,
) -> tuple[int, ParsedDecision]:
    if not record.unreadable_attachment_names:
        return decision_type, parsed
    if decision_type == DECISION_TYPE_NON_JOB:
        return decision_type, parsed
    missing = list(parsed.missing)
    for name in record.unreadable_attachment_names:
        note = f"unreadable attachment: {name}"
        if note not in missing:
            missing.append(note)
    reply = parsed.reply_ko
    if not reply:
        names = ", ".join(record.unreadable_attachment_names)
        reply = (
            "첨부 파일이 Office 문서이거나 텍스트로 읽을 수 없습니다. "
            f"다음 파일을 텍스트 형식(.txt, .csv 등)으로 다시 보내 주세요: {names}"
        )
    updated = ParsedDecision(
        decision_type=DECISION_TYPE_INSUFFICIENT,
        infra=parsed.infra,
        job_kind=parsed.job_kind,
        missing=missing,
        summary=parsed.summary or "Unreadable or Office attachments present",
        reply_ko=reply,
        operator_ko=parsed.operator_ko,
    )
    return DECISION_TYPE_INSUFFICIENT, updated


async def process_received_mail_decision(
    database_path: Path | str,
    mail_uuid: str,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    outcome = await job_decision_agent_service.evaluate_received_mail(
        database_path,
        mail_uuid,
        persist=False,
    )
    record = get_received_mail_by_uuid(database_path, mail_uuid)
    if record is None:
        raise ValueError(f"received_mail not found: {mail_uuid}")
    if record.decision_type != DECISION_TYPE_PENDING and persist:
        outcome["skipped"] = True
        outcome["skipped_reason"] = "already decided"
        return outcome

    parsed: ParsedDecision = outcome["parsed"]
    decision_type = int(outcome["decision_type"])
    decision_type, parsed = apply_unreadable_attachment_rule(decision_type, record, parsed)
    sender = extract_sender_email(record.from_address)
    if decision_type == DECISION_TYPE_JOB and not sender:
        decision_type = DECISION_TYPE_INSUFFICIENT
        parsed = ParsedDecision(
            decision_type=DECISION_TYPE_INSUFFICIENT,
            infra=parsed.infra,
            job_kind=parsed.job_kind,
            missing=[*parsed.missing, "sender email"],
            summary=parsed.summary or "Sender email missing",
            reply_ko=parsed.reply_ko or "발신 메일 주소를 확인할 수 없습니다. 유효한 주소로 다시 보내 주세요.",
            operator_ko=parsed.operator_ko,
        )
    outcome["decision_type"] = decision_type
    outcome["parsed"] = parsed

    job: JobRecord | None = None
    email_sent = False
    if persist:
        if decision_type == DECISION_TYPE_JOB:
            job = create_job_from_received_mail(database_path, record, parsed)
            updated = update_decision_type(database_path, record.uuid, DECISION_TYPE_JOB)
            outcome["record"] = (
                {"idx": updated.idx, "decision_type": updated.decision_type} if updated else None
            )
        elif decision_type == DECISION_TYPE_NON_JOB:
            updated = update_decision_type(database_path, record.uuid, DECISION_TYPE_NON_JOB)
            outcome["record"] = (
                {"idx": updated.idx, "decision_type": updated.decision_type} if updated else None
            )
        else:
            sender = extract_sender_email(record.from_address)
            cc_addresses = list_supplement_cc_emails(database_path)
            body = resolve_supplement_reply_body(parsed, record)
            if sender:
                email_sent = await send_job_supplement_request_email(
                    database_path=database_path,
                    to_address=sender,
                    original_subject=record.subject,
                    body=body,
                    cc_addresses=cc_addresses,
                )
            else:
                logger.warning(
                    "supplement email skipped uuid=%s: no sender address",
                    record.uuid,
                )
            updated = update_decision_type(database_path, record.uuid, DECISION_TYPE_INSUFFICIENT)
            outcome["record"] = (
                {"idx": updated.idx, "decision_type": updated.decision_type} if updated else None
            )
        outcome["persisted"] = True
    else:
        outcome["persisted"] = False

    outcome["job_idx"] = job.idx if job is not None else None
    outcome["job_srnum"] = job.srnum if job is not None else None
    outcome["email_sent"] = email_sent
    return outcome


async def process_pending_received_mails(
    database_path: Path | str,
    *,
    limit: int = 20,
) -> int:
    pending = list_pending_received_mail(database_path, limit=limit)
    processed = 0
    for record in pending:
        try:
            await process_received_mail_decision(database_path, record.uuid, persist=True)
            processed += 1
        except Exception:
            logger.exception("JOB_DECISION pipeline failed uuid=%s idx=%s", record.uuid, record.idx)
    return processed
