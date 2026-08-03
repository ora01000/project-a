"""Resolve helpdesk agent id and build delegation messages for approved jobs."""

from __future__ import annotations

from pathlib import Path

from backend.app.db.agentruntime import get_agentruntime_by_local_agent_id
from backend.app.db.jobs import JobRecord
from backend.app.services.agent_runtime_client import normalize_runtime_mode

MOCK_HELPDESK_AGENT_ID = "helpdesk"
HELPDESK_LOCAL_AGENT_ID = "helpdesk"


def resolve_helpdesk_agent_id(
    database_path: str | Path,
    runtime_mode: str,
) -> str:
    """Mock uses local catalog id; AXIT runtime uses agentruntime.agent_id."""
    if normalize_runtime_mode(runtime_mode) == "mock":
        return MOCK_HELPDESK_AGENT_ID

    record = get_agentruntime_by_local_agent_id(
        database_path,
        HELPDESK_LOCAL_AGENT_ID,
        runtime_mode="http",
    )
    if record is None:
        raise RuntimeError(
            f"agentruntime record not found for local_agent_id={HELPDESK_LOCAL_AGENT_ID!r}"
        )
    return record.agent_id


def build_job_agent_message(job: JobRecord) -> str:
    return (
        "작업요청서 처리를 수행해 주세요.\n\n"
        f"- SR 번호: {job.srnum}\n"
        f"- 제목: {job.job_title}\n"
        f"- 요청자: {job.requester_name} ({job.requester_email}, {job.requester_depart})\n"
        f"- 요청 일시: {job.request_date}\n\n"
        "작업 내용:\n"
        f"{job.job_content}"
    )
