"""Resolve job auditor orchestrator and build review messages."""

from __future__ import annotations

from pathlib import Path

from backend.app.agents.mock_platform_agents import JOB_AUDITOR_AXIT_LOCAL_AGENT_ID, JOB_AUDITOR_LOCAL_AGENT_ID
from backend.app.config import JobAuditorSettings, load_job_auditor_settings
from backend.app.db.agentruntime import (
    StoredAgentRuntime,
    catalog_agent_id,
    get_agentruntime_by_agent_id,
    get_agentruntime_by_local_agent_id,
)
from backend.app.db.jobs import JobRecord
from backend.app.services.agent_runtime_client import normalize_runtime_mode


def _find_http_job_auditor_record(
    database_path: str | Path,
    *,
    settings: JobAuditorSettings,
) -> StoredAgentRuntime | None:
    if settings.axit_agent_id:
        record = get_agentruntime_by_agent_id(
            database_path,
            settings.axit_agent_id,
            runtime_mode="http",
        )
        if record is not None and record.is_orchestrator:
            return record

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
        if record is not None and record.is_orchestrator:
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
        f"{JOB_AUDITOR_AXIT_LOCAL_AGENT_ID!r}, {JOB_AUDITOR_LOCAL_AGENT_ID!r}"
        + (
            f"; axit_agent_id={auditor_settings.axit_agent_id!r}"
            if auditor_settings.axit_agent_id
            else ""
        )
        + "). Register an orchestrator (is_orchestrator=1) in agentruntime or set "
        "JOB_AUDITOR_LOCAL_AGENT_ID / JOB_AUDITOR_AXIT_AGENT_ID."
    )


def build_job_review_message(job: JobRecord) -> str:
    return (
        "다음 작업 요청 내용에 대한 1차 AI 검토를 수행해 주세요.\n"
        "검토 의견, 리스크, 보완 사항, 필요 시 작업 계획서를 한국어로 작성해 주세요.\n\n"
        f"- SR 번호: {job.srnum}\n"
        f"- 제목: {job.job_title}\n"
        f"- 요청자: {job.requester_name} ({job.requester_email}, {job.requester_depart})\n"
        f"- 요청 일시: {job.request_date}\n\n"
        "작업 내용:\n"
        f"{job.job_content}"
    )
