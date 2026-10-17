"""Resolve job auditor agent and build review messages."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.app.agents.mock_platform_agents import JOB_AUDITOR_AXIT_LOCAL_AGENT_ID, JOB_AUDITOR_LOCAL_AGENT_ID
from backend.app.config import JobAuditorSettings, load_job_auditor_settings
from backend.app.db.agentruntime import (
    StoredAgentRuntime,
    catalog_agent_id,
    get_agentruntime_by_local_agent_id,
)
from backend.app.db.jobs import JOB_TYPE_WORKFLOW, JobRecord
from backend.app.db.received_mail import get_received_mail_by_uuid
from backend.app.services.agent_runtime_client import normalize_runtime_mode
from backend.app.services.received_mail_attachments import (
    ATTACHMENT_TEXT_MAX_CHARS,
    is_allowed_attachment_filename,
    load_received_mail_text_attachments,
)

logger = logging.getLogger(__name__)

MAIL_CHANNEL_ID = "received_mail"
ATTACHMENT_MAX_CHARS = ATTACHMENT_TEXT_MAX_CHARS


def _is_non_orchestrator(record: StoredAgentRuntime | None) -> bool:
    return record is not None and not record.is_orchestrator


def _find_http_job_auditor_record(
    database_path: str | Path,
    *,
    settings: JobAuditorSettings,
) -> StoredAgentRuntime | None:
    """Resolve by agentruntime.local_agent_id only (AXIT uuid comes from DB agent_id)."""
    local_candidates: list[str] = []
    for candidate in (
        settings.local_agent_id,
        JOB_AUDITOR_AXIT_LOCAL_AGENT_ID,
        JOB_AUDITOR_LOCAL_AGENT_ID,
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


def try_resolve_job_auditor_runtime_record(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: JobAuditorSettings | None = None,
) -> StoredAgentRuntime | None:
    if normalize_runtime_mode(runtime_mode) == "mock":
        return get_agentruntime_by_local_agent_id(
            database_path,
            JOB_AUDITOR_LOCAL_AGENT_ID,
            runtime_mode="mock",
        )

    auditor_settings = settings or load_job_auditor_settings()
    return _find_http_job_auditor_record(database_path, settings=auditor_settings)


def try_resolve_job_auditor_agent_id(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: JobAuditorSettings | None = None,
) -> str | None:
    if normalize_runtime_mode(runtime_mode) == "mock":
        return JOB_AUDITOR_LOCAL_AGENT_ID

    record = try_resolve_job_auditor_runtime_record(
        database_path,
        runtime_mode,
        settings=settings,
    )
    if record is None:
        return None
    return catalog_agent_id(record)


def resolve_job_auditor_agent_id(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: JobAuditorSettings | None = None,
) -> str:
    agent_id = try_resolve_job_auditor_agent_id(
        database_path,
        runtime_mode,
        settings=settings,
    )
    if agent_id is not None:
        return agent_id

    auditor_settings = settings or load_job_auditor_settings()
    raise RuntimeError(
        "agentruntime record not found for job auditor "
        f"(local_agent_id candidates: {auditor_settings.local_agent_id!r}, "
        f"{JOB_AUDITOR_AXIT_LOCAL_AGENT_ID!r}, {JOB_AUDITOR_LOCAL_AGENT_ID!r}). "
        "Register a non-orchestrator agent (is_orchestrator=0) with "
        "local_agent_id=JOB_AUDITOR_AGENT in agentruntime (http) or set JOB_AUDITOR_LOCAL_AGENT_ID."
    )


def _load_mail_text_attachments(database_path: str | Path, job: JobRecord) -> list[tuple[str, str]]:
    """Return (filename, content) for text attachments linked to a mail-origin job."""
    if (job.channel_id or "").strip() != MAIL_CHANNEL_ID:
        return []
    mail_uuid = (job.message_id or "").strip()
    if not mail_uuid:
        return []
    record = get_received_mail_by_uuid(database_path, mail_uuid)
    if record is None:
        logger.warning("AI review: received_mail missing for job idx=%s message_id=%s", job.idx, mail_uuid)
        return []
    return load_received_mail_text_attachments(
        mail_uuid,
        record.attachment_names,
        max_chars=ATTACHMENT_MAX_CHARS,
    )


def _load_workflow_hitl_attachments(database_path: str | Path, job: JobRecord) -> list[tuple[str, str]]:
    """Return text files uploaded for a workflow HITL approval job, if any."""
    if int(job.job_type) != JOB_TYPE_WORKFLOW:
        return []
    try:
        from backend.app.config import resolve_attachment_dir
        from backend.app.db.workflow import get_work_node_by_uuid, get_workflow_by_uuid
        from backend.app.services.workflow_runner import (
            parse_workflow_job_message_id,
            resolve_hitl_work_uuid_from_job,
        )
    except Exception:
        return []

    parsed = parse_workflow_job_message_id(job.message_id)
    if parsed is None:
        return []
    workflow = get_workflow_by_uuid(database_path, parsed.workflow_uuid)
    if workflow is None:
        return []
    work_uuid = resolve_hitl_work_uuid_from_job(
        database_path=database_path,
        workflow_expression=workflow.workflow,
        message_id=job.message_id,
    )
    if not work_uuid:
        return []
    node = get_work_node_by_uuid(database_path, work_uuid)
    if node is None or not node.upload:
        return []
    directory = resolve_attachment_dir((node.upload_path or "").strip())
    if directory is None or not directory.is_dir():
        return []
    loaded: list[tuple[str, str]] = []
    for path in sorted(p for p in directory.iterdir() if p.is_file()):
        if not is_allowed_attachment_filename(path.name):
            loaded.append((path.name, "(텍스트 허용 확장자가 아닌 파일 — 내용 생략)"))
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > ATTACHMENT_MAX_CHARS:
                text = text[:ATTACHMENT_MAX_CHARS] + "\n...[truncated]..."
            loaded.append((path.name, text))
        except OSError as exc:
            loaded.append((path.name, f"[failed to read {path.name}: {exc}]"))
    return loaded


def load_job_review_attachments(
    database_path: str | Path,
    job: JobRecord,
) -> list[tuple[str, str]]:
    mail_attachments = _load_mail_text_attachments(database_path, job)
    if mail_attachments:
        return mail_attachments
    return _load_workflow_hitl_attachments(database_path, job)


def build_job_review_message(
    job: JobRecord,
    *,
    attachments: list[tuple[str, str]] | None = None,
) -> str:
    requester_email = (job.requester_email or "").strip()
    requester_identified = bool(requester_email and "@" in requester_email)
    parts = [
        "다음 작업 요청 내용에 대한 1차 AI 검토를 수행해 주세요.",
        "검토 의견, 리스크, 보완 사항, 필요 시 작업 계획서를 한국어로 작성해 주세요.",
        "첨부(텍스트) 파일이 있으면 다음도 함께 검토해 주세요:",
        "- 작업 수행에 필요한 정보가 첨부/본문에 포함되어 있는지",
        "- 첨부가 작업 목적에 적합한 파일인지(형식·내용·대상 식별 정보)",
        "",
        "요청자 신원 판정 규칙:",
        "- requester_email(발신 메일 주소)이 있으면 요청자 신원은 확인된 것으로 본다.",
        "- 표시명(requester_name) 부재·이메일이름 동일·부서 '확인 불가'만으로 신원 미상/보완 요청을 하지 않는다.",
        (
            f"- 본 건 요청자 신원: {'확인됨 (이메일 존재)' if requester_identified else '미확인 (이메일 없음)'}"
        ),
        "",
        f"- SR 번호: {job.srnum}",
        f"- 제목: {job.job_title}",
        f"- 요청자: {job.requester_name} ({job.requester_email}, {job.requester_depart})",
        f"- 요청 일시: {job.request_date}",
        "",
        "작업 내용:",
        job.job_content,
        "",
        "=== 첨부 파일 (텍스트) ===",
    ]
    files = attachments or []
    if not files:
        parts.append("(없음)")
    else:
        for filename, content in files:
            parts.append(f"--- file: {filename} ---")
            parts.append(content)
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"
