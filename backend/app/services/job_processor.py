"""Resolve job-delegation agent id and build messages for approved jobs."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.app.agents.private_cloud_agent import PRIVATE_CLOUD_AGENT_ID
from backend.app.agents.system_agents import HELPDESK_AGENT_ID
from backend.app.config import JobProcessorSettings, load_job_processor_settings
from backend.app.db.agentruntime import (
    StoredAgentRuntime,
    catalog_agent_id,
    get_agentruntime_by_local_agent_id,
)
from backend.app.db.jobs import JobRecord
from backend.app.db.received_mail import get_received_mail_by_uuid
from backend.app.services.agent_runtime_client import normalize_runtime_mode
from backend.app.services.received_mail_attachments import (
    format_text_attachments_for_prompt,
    load_received_mail_text_attachments,
)

logger = logging.getLogger(__name__)

MAIL_CHANNEL_ID = "received_mail"

# Mock / unset-env default: PRIVATE_CLOUD_AGENT (replaces former helpdesk).
DEFAULT_JOB_DELEGATION_LOCAL_AGENT_ID = PRIVATE_CLOUD_AGENT_ID


def _is_non_orchestrator(record: StoredAgentRuntime | None) -> bool:
    return record is not None and not record.is_orchestrator


def _find_http_helpdesk_record(
    database_path: str | Path,
    *,
    settings: JobProcessorSettings,
) -> StoredAgentRuntime | None:
    """Resolve by agentruntime.local_agent_id only (AXIT uuid comes from DB agent_id)."""
    local_candidates: list[str] = []
    for candidate in (
        settings.helpdesk_local_agent_id,
        DEFAULT_JOB_DELEGATION_LOCAL_AGENT_ID,
        HELPDESK_AGENT_ID,
    ):
        normalized = candidate.strip()
        if normalized and normalized not in local_candidates:
            local_candidates.append(normalized)

    for local_agent_id in local_candidates:
        record = get_agentruntime_by_local_agent_id(
            database_path,
            local_agent_id,
            runtime_mode="http",
        )
        if _is_non_orchestrator(record):
            return record

    return None


def try_resolve_helpdesk_runtime_record(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: JobProcessorSettings | None = None,
) -> StoredAgentRuntime | None:
    """Return delegation agentruntime record (is_orchestrator=0) for http mode."""
    if normalize_runtime_mode(runtime_mode) == "mock":
        return None

    processor_settings = settings or load_job_processor_settings()
    return _find_http_helpdesk_record(database_path, settings=processor_settings)


def try_resolve_helpdesk_agent_id(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: JobProcessorSettings | None = None,
) -> str | None:
    """Return catalog agent id for job delegation, or None when http has no match."""
    processor_settings = settings or load_job_processor_settings()
    if normalize_runtime_mode(runtime_mode) == "mock":
        return (
            processor_settings.helpdesk_local_agent_id.strip()
            or DEFAULT_JOB_DELEGATION_LOCAL_AGENT_ID
        )

    record = try_resolve_helpdesk_runtime_record(
        database_path,
        runtime_mode,
        settings=processor_settings,
    )
    if record is None:
        return None
    return catalog_agent_id(record)


def resolve_helpdesk_agent_id(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: JobProcessorSettings | None = None,
) -> str:
    """Mock uses local catalog id; AXIT runtime uses agentruntime catalog id."""
    processor_settings = settings or load_job_processor_settings()
    agent_id = try_resolve_helpdesk_agent_id(
        database_path,
        runtime_mode,
        settings=processor_settings,
    )
    if agent_id is not None:
        return agent_id

    raise RuntimeError(
        "agentruntime record not found for job delegation "
        f"(local_agent_id candidates: {processor_settings.helpdesk_local_agent_id!r}, "
        f"{DEFAULT_JOB_DELEGATION_LOCAL_AGENT_ID!r}, {HELPDESK_AGENT_ID!r}). "
        "Register a non-orchestrator agent (is_orchestrator=0) with matching "
        "local_agent_id in agentruntime (http) or set JOB_PROCESSOR_HELPDESK_LOCAL_AGENT_ID."
    )


def _mail_text_attachments_for_job(
    database_path: str | Path,
    job: JobRecord,
) -> list[tuple[str, str]]:
    """Load text attachments for mail-origin jobs (channel_id=received_mail)."""
    if (job.channel_id or "").strip() != MAIL_CHANNEL_ID:
        return []
    mail_uuid = (job.message_id or "").strip()
    if not mail_uuid:
        return []
    record = get_received_mail_by_uuid(database_path, mail_uuid)
    if record is None:
        logger.warning(
            "job agent message: received_mail missing for idx=%s message_id=%s",
            job.idx,
            mail_uuid,
        )
        return []
    return load_received_mail_text_attachments(mail_uuid, record.attachment_names)


def build_job_agent_message(
    job: JobRecord,
    *,
    database_path: str | Path | None = None,
    text_attachments: list[tuple[str, str]] | None = None,
) -> str:
    """Build helpdesk agent prompt; mail jobs include attachment text after approval."""
    message = (
        "작업요청서 처리를 수행해 주세요.\n\n"
        f"- SR 번호: {job.srnum}\n"
        f"- 제목: {job.job_title}\n"
        f"- 요청자: {job.requester_name} ({job.requester_email}, {job.requester_depart})\n"
        f"- 요청 일시: {job.request_date}\n\n"
        "작업 내용:\n"
        f"{job.job_content}"
    )
    attachments = text_attachments
    if attachments is None and database_path is not None:
        attachments = _mail_text_attachments_for_job(database_path, job)
    block = format_text_attachments_for_prompt(attachments or [])
    if not block:
        return message
    return f"{message}\n\n{block}"

