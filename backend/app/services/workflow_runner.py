"""Execute a workflow expression sequentially."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from croniter import croniter

from backend.app.config import (
    RESULT_LATEST_FILENAME,
    read_work_node_validation_output,
    write_work_node_validation_output,
    work_node_file_path,
)
from backend.app.db.agentruntime import catalog_agent_id, get_agentruntime_by_idx
from backend.app.db.job_datetime import now_job_datetime
from backend.app.db.jobs import (
    JOB_TYPE_WORKFLOW,
    JobIntakePayload,
    JobRecord,
    assign_job_approver,
    create_job_from_intake,
)
from backend.app.db.users import User, get_user_by_userid
from backend.app.db.workflow import (
    WorkNodeRecord,
    WorkflowRecord,
    get_work_node_by_uuid,
    get_workflow_by_uuid,
    insert_workflow_history,
    mark_work_node_run_finished,
    mark_work_node_run_started,
    mark_workflow_run_finished,
    resolve_work_node_upload_userid,
    mark_workflow_run_started,
    set_work_node_schedule_wait,
    work_uuids_from_expression,
)
from backend.app.notifications.email_sender import (
    load_email_settings_from_db,
    resolve_recipient_email,
    send_markdown_email,
)
from backend.app.services.agent_runtime_client import AgentInvokeRequest
from backend.app.services.k8s_scrape_scheduler import cron_matches_minute
from backend.app.services.workflow_document import parse_workflow_document
from backend.app.services.workflow_graph import FlowToken
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

logger = logging.getLogger(__name__)

_WORKFLOW_JOB_MESSAGE_RE = re.compile(
    r"^workflow:(?P<uuid>[0-9a-fA-F-]{36}):(?P<index>\d+)$"
)

# workflow_uuid(lower) → work_node uuid(lower) requested to stop
_stop_requests: dict[str, str] = {}

USER_STOP_REASON = "사용자에 의해 중지되었습니다."


class WorkflowStopRequested(Exception):
    """Raised when an operator stops the currently running work node."""

    def __init__(self, work_uuid: str, *, reason: str = USER_STOP_REASON) -> None:
        self.work_uuid = (work_uuid or "").strip()
        self.reason = reason or USER_STOP_REASON
        super().__init__(self.reason)


def request_work_node_stop(workflow_uuid: str, work_uuid: str) -> None:
    wf = (workflow_uuid or "").strip().lower()
    node = (work_uuid or "").strip().lower()
    if not wf or not node:
        raise ValueError("중지 대상이 올바르지 않습니다.")
    _stop_requests[wf] = node


def clear_work_node_stop(workflow_uuid: str) -> None:
    _stop_requests.pop((workflow_uuid or "").strip().lower(), None)


def is_work_node_stop_requested(workflow_uuid: str, work_uuid: str) -> bool:
    wf = (workflow_uuid or "").strip().lower()
    node = (work_uuid or "").strip().lower()
    if not wf or not node:
        return False
    return _stop_requests.get(wf) == node


def _raise_if_work_node_stopped(workflow_uuid: str, work_uuid: str) -> None:
    if is_work_node_stop_requested(workflow_uuid, work_uuid):
        raise WorkflowStopRequested(work_uuid)


def _parse_work_report_addresses(work_report: str) -> list[str]:
    return [part.strip() for part in (work_report or "").split(";") if part.strip()]


async def _maybe_send_work_report_email(
    database_path: Path | str,
    *,
    node: WorkNodeRecord,
    result_content: str,
) -> None:
    targets = _parse_work_report_addresses(node.work_report)
    if not targets:
        return
    try:
        settings = load_email_settings_from_db(database_path)
        if settings is None:
            logger.warning(
                "work_report email skipped uuid=%s: mail settings missing",
                node.uuid,
            )
            return
        recipients: list[str] = []
        for target in targets:
            resolved = resolve_recipient_email(database_path, target)
            if resolved:
                recipients.append(resolved)
            else:
                logger.warning(
                    "work_report recipient unresolved uuid=%s target=%s",
                    node.uuid,
                    target,
                )
        unique = list(dict.fromkeys(recipients))
        if not unique:
            return
        subject = f"[단위작업 결과] {node.work_name}".strip()[:200]
        body = (
            f"## 단위작업 결과 보고\n\n"
            f"- 작업명: **{node.work_name}**\n"
            f"- 작업 UUID: `{node.uuid}`\n\n"
            f"## 결과\n\n"
            f"{(result_content or '(결과 없음)').strip()}\n"
        )
        await send_markdown_email(
            settings=settings,
            to_addresses=unique,
            subject=subject,
            markdown_body=body,
        )
    except Exception:
        logger.exception("work_report email failed uuid=%s", node.uuid)


@dataclass
class WorkflowRunStep:
    kind: str
    label: str
    status: str
    detail: str = ""
    work_uuid: str | None = None


@dataclass
class WorkflowRuntimeNodeStatus:
    """In-memory per-node status for the current run (not persisted in workflow JSON)."""

    work_uuid: str | None
    kind: str
    label: str
    status: str  # pending|running|ok|failed|awaiting|skipped
    detail: str = ""


@dataclass
class WorkflowRunResult:
    status: str  # success | failed | awaiting_approval
    message: str
    workflow: WorkflowRecord | None = None
    steps: list[WorkflowRunStep] = field(default_factory=list)
    runtime_nodes: list[WorkflowRuntimeNodeStatus] = field(default_factory=list)
    job_idx: int | None = None


def encode_workflow_job_message_id(workflow_uuid: str, resume_index: int) -> str:
    return f"workflow:{workflow_uuid.strip().lower()}:{int(resume_index)}"


def parse_workflow_job_message_id(message_id: str) -> tuple[str, int] | None:
    match = _WORKFLOW_JOB_MESSAGE_RE.match((message_id or "").strip())
    if not match:
        return None
    return match.group("uuid").lower(), int(match.group("index"))


def _hitl_info_for_token(
    database_path: Path | str,
    token: FlowToken,
) -> tuple[str, str | None] | None:
    """Return (approver_userid, work_uuid) when token is a HITL step."""
    if token.kind == "hitl":
        userid = (token.userid or "").strip()
        if not userid:
            return None
        return userid, token.work_uuid
    if token.kind == "work" and token.work_uuid:
        node = get_work_node_by_uuid(database_path, token.work_uuid)
        if node is None:
            return None
        if (node.worker or "agent").strip().lower() != "hitl":
            return None
        userid = (node.approver_userid or "").strip()
        if not userid:
            return None
        return userid, node.uuid
    return None


def resolve_awaiting_hitl_from_job(
    *,
    workflow_expression: str,
    message_id: str,
    database_path: Path | str | None = None,
) -> tuple[str, str] | None:
    """Return (graph_node_id, userid) for the HITL token waiting on this job."""
    parsed = parse_workflow_job_message_id(message_id)
    if parsed is None:
        return None
    _, resume_index = parsed
    hitl_index = int(resume_index) - 1
    if hitl_index < 0:
        return None
    tokens = parse_workflow_document(workflow_expression)
    if hitl_index >= len(tokens):
        return None
    token = tokens[hitl_index]
    if database_path is not None:
        info = _hitl_info_for_token(database_path, token)
        if info is None:
            return None
        userid, work_uuid = info
        if work_uuid:
            return f"H:{userid}@{hitl_index}", userid
        return f"H:{userid}@{hitl_index}", userid
    if token.kind != "hitl" or not (token.userid or "").strip():
        return None
    userid = token.userid.strip()
    return f"H:{userid}@{hitl_index}", userid


def resolve_hitl_work_uuid_from_job(
    *,
    database_path: Path | str,
    workflow_expression: str,
    message_id: str,
) -> str | None:
    parsed = parse_workflow_job_message_id(message_id)
    if parsed is None:
        return None
    _, resume_index = parsed
    hitl_index = int(resume_index) - 1
    if hitl_index < 0:
        return None
    tokens = parse_workflow_document(workflow_expression)
    if hitl_index >= len(tokens):
        return None
    info = _hitl_info_for_token(database_path, tokens[hitl_index])
    if info is None:
        return None
    return info[1]


def require_hitl_attachment_ready(database_path: Path | str, job: JobRecord) -> None:
    """Raise ValueError when HITL step requires upload but none is present."""
    if int(job.job_type) != JOB_TYPE_WORKFLOW:
        return
    parsed = parse_workflow_job_message_id(job.message_id)
    if parsed is None:
        return
    workflow_uuid, _ = parsed
    workflow = get_workflow_by_uuid(database_path, workflow_uuid)
    if workflow is None:
        return
    work_uuid = resolve_hitl_work_uuid_from_job(
        database_path=database_path,
        workflow_expression=workflow.workflow,
        message_id=job.message_id,
    )
    if not work_uuid:
        return
    node = get_work_node_by_uuid(database_path, work_uuid)
    if node is None or not node.upload:
        return
    path = (node.upload_path or "").strip()
    if not path:
        raise ValueError("승인 전에 파일을 업로드해야 합니다.")
    from backend.app.config import resolve_attachment_dir

    directory = resolve_attachment_dir(path)
    if directory is None or not directory.is_dir():
        raise ValueError("업로드된 첨부 디렉터리를 찾을 수 없습니다.")
    has_file = any(child.is_file() for child in directory.iterdir())
    if not has_file:
        raise ValueError("승인 전에 텍스트 파일을 1개 이상 업로드해야 합니다.")


def _diagram_text(
    database_path: Path | str,
    tokens: list[FlowToken],
    work_names: dict[str, str],
) -> str:
    parts: list[str] = []
    for token in tokens:
        if token.kind == "start":
            parts.append("시작(S)")
        elif token.kind == "end":
            parts.append("종료(E)")
        else:
            hitl = _hitl_info_for_token(database_path, token)
            if hitl is not None:
                userid, work_uuid = hitl
                label = work_names.get(work_uuid or "", f"승인(H:{userid})")
                parts.append(label)
            elif token.kind == "work" and token.work_uuid:
                name = work_names.get(token.work_uuid, token.work_uuid[:8])
                parts.append(name)
            else:
                parts.append(token.raw)
    return " → ".join(parts)


def _work_names_for_tokens(
    database_path: Path | str, tokens: list[FlowToken]
) -> dict[str, str]:
    work_names: dict[str, str] = {}
    for token in tokens:
        for key in (token.work_uuid, token.fail_work_uuid):
            if not key:
                continue
            node = get_work_node_by_uuid(database_path, key)
            if node is not None:
                work_names[key] = node.work_name
    return work_names


def _append_previous_result(script: str, previous_result: str, *, use_previous: bool) -> str:
    if not use_previous:
        return script
    prior = (previous_result or "").strip()
    if not prior:
        return script
    return (
        f"{script}\n\n"
        "----- 이전 작업 결과 -----\n"
        f"{prior}"
    )


def _wrap_work_script_for_execution(script_type: str, script: str) -> str:
    """Wrap work_script by script_type before sending to target_agent."""
    normalized = (script_type or "").strip().lower()
    body = script.strip()
    if normalized == "kubectl":
        return (
            "다음 스크립트를 kubectl 도구를 사용하여 수행하고 정의된 결과 json 형식에 맞춰 응답하세요\n"
            "-------------\n"
            "# 수행 스크립트\n"
            f"{body}\n"
            "-------------\n"
            "# 결과\n"
            "{\n"
            '  "success": [ true | false ],\n'
            '  "message": "결과 메시지"\n'
            "}"
        )
    if normalized == "ansible":
        return (
            "다음 스크립트를 ansible 에이전트 도구를 사용하여 수행하고 정의된 결과 json 형식에 맞춰 응답하세요\n"
            "-------------\n"
            "# 수행 스크립트\n"
            f"{body}\n"
            "-------------\n"
            "# 결과\n"
            "{\n"
            '  "success": [ true | false ],\n'
            '  "message": "결과 메시지"\n'
            "}"
        )
    # prompt: as-is. cli: TBD — currently as-is.
    return body


def _build_agent_message(
    node: WorkNodeRecord,
    previous_result: str,
    *,
    attachment_text: str = "",
) -> str:
    script = (node.work_script or "").strip()
    if not script:
        raise ValueError(f"작업 스크립트가 비어 있습니다: {node.work_name}")
    wrapped = _wrap_work_script_for_execution(node.script_type, script)
    message = _append_previous_result(
        wrapped,
        previous_result,
        use_previous=bool(node.use_previous_work_result),
    )
    attach = (attachment_text or "").strip()
    if attach:
        message = f"{message}\n\n----- 승인 단계 업로드 파일 -----\n{attach}"
    return message


def _read_attachment_bundle(upload_path: str) -> str:
    """Load text file listing + contents from an attachment directory path."""
    from backend.app.config import resolve_attachment_dir

    directory = resolve_attachment_dir(upload_path)
    if directory is None or not directory.is_dir():
        return ""
    chunks: list[str] = []
    files = sorted(path for path in directory.iterdir() if path.is_file())
    if not files:
        return f"(디렉터리 비어 있음: {directory})"
    names = ", ".join(path.name for path in files)
    chunks.append(f"경로: {directory}")
    chunks.append(f"파일 목록: {names}")
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            chunks.append(f"\n## {path.name}\n(텍스트로 읽을 수 없는 파일)")
            continue
        chunks.append(f"\n## {path.name}\n{text}")
    return "\n".join(chunks)


def _attachment_context_from_previous_hitl(
    database_path: Path | str,
    tokens: list[FlowToken],
    current_index: int,
) -> str:
    """Use the immediately preceding HITL node's upload_path when present."""
    for token in reversed(tokens[: max(0, current_index)]):
        info = _hitl_info_for_token(database_path, token)
        if info is None:
            continue
        _userid, work_uuid = info
        if not work_uuid:
            return ""
        node = get_work_node_by_uuid(database_path, work_uuid)
        if node is None:
            return ""
        if not node.upload:
            return ""
        return _read_attachment_bundle(node.upload_path)
    return ""


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fenced and fenced.group(1):
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_success_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "ok", "success", "성공", "통과"}:
            return True
        if normalized in {"false", "0", "no", "fail", "failed", "실패"}:
            return False
    return None


def _assert_structured_work_success(script_type: str, content: str) -> None:
    """For kubectl/ansible, require JSON ``success: true``; otherwise raise (fail path)."""
    normalized = (script_type or "").strip().lower()
    if normalized not in {"kubectl", "ansible"}:
        return
    payload = _extract_json_object(content)
    if payload is None:
        raise ValueError("작업 결과 JSON을 파싱하지 못했습니다.")
    flag = _coerce_success_flag(payload.get("success"))
    if flag is None:
        raise ValueError("작업 결과에 success 필드가 없습니다.")
    if flag:
        return
    message = str(payload.get("message") or "").strip() or "작업 수행 결과가 success=false 입니다."
    raise ValueError(message[:200])


async def _await_work_node_schedule_if_needed(
    database_path: Path | str,
    node: WorkNodeRecord,
    *,
    workflow_uuid: str = "",
) -> None:
    """Block until the one-shot clock time when ``node.cron`` is enabled.

    Schedule applies only while a workflow run is executing this node.
    """
    if not node.cron:
        return
    expr = (node.cron_expr or "").strip()
    if not expr:
        return

    set_work_node_schedule_wait(database_path, node.uuid, waiting=True)
    logger.info(
        "workflow work_node schedule wait uuid=%s name=%s cron_expr=%s",
        node.uuid,
        node.work_name,
        expr,
    )
    try:
        while True:
            if workflow_uuid:
                _raise_if_work_node_stopped(workflow_uuid, node.uuid)
            now = now_display_datetime()
            minute_now = now.astimezone(DISPLAY_TIMEZONE).replace(second=0, microsecond=0)
            if cron_matches_minute(expr, minute_now):
                return
            try:
                iterator = croniter(expr, minute_now)
                nxt = iterator.get_next(datetime)
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"잘못된 스케줄 표현식입니다: {expr}") from exc
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=DISPLAY_TIMEZONE)
            else:
                nxt = nxt.astimezone(DISPLAY_TIMEZONE)
            delay = (nxt - now).total_seconds()
            if delay <= 0:
                return
            await asyncio.sleep(min(delay, 30.0))
    finally:
        set_work_node_schedule_wait(database_path, node.uuid, waiting=False)


def _resolve_invoke_agent_id(database_path: Path | str, target_agent: int) -> str:
    if int(target_agent) <= 0:
        raise ValueError("대상 에이전트가 지정되지 않았습니다.")
    record = get_agentruntime_by_idx(database_path, int(target_agent))
    if record is None:
        raise ValueError(f"대상 에이전트를 찾을 수 없습니다 (idx={target_agent}).")
    agent_id = catalog_agent_id(record).strip() or record.agent_id.strip()
    if not agent_id:
        raise ValueError(f"에이전트 ID가 비어 있습니다 (idx={target_agent}).")
    return agent_id


async def _invoke_work_node(
    *,
    database_path: Path | str,
    agent_runtime: Any,
    node: WorkNodeRecord,
    message: str,
    workflow_uuid: str = "",
) -> str:
    agent_id = _resolve_invoke_agent_id(database_path, node.target_agent)
    invoke_coro = agent_runtime.invoke(
        AgentInvokeRequest(
            agent_id=agent_id,
            message=message,
            session_id=f"workflow-{node.uuid}",
            agentruntime_idx=int(node.target_agent),
        )
    )
    if not workflow_uuid:
        result = await invoke_coro
    else:
        task = asyncio.ensure_future(invoke_coro)
        try:
            while not task.done():
                _raise_if_work_node_stopped(workflow_uuid, node.uuid)
                done, _ = await asyncio.wait({task}, timeout=0.5)
                if done:
                    break
            result = await task
        except WorkflowStopRequested:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            raise
    content = str(getattr(result, "content", "") or "").strip()
    if not content:
        raise ValueError("에이전트 응답이 비어 있습니다.")
    if workflow_uuid:
        _raise_if_work_node_stopped(workflow_uuid, node.uuid)
    return content


def _finalize_user_stop(
    database_path: Path | str,
    *,
    workflow: WorkflowRecord,
    tokens: list[FlowToken],
    node: WorkNodeRecord,
    steps: list[WorkflowRunStep],
    requester: User | None,
) -> WorkflowRunResult:
    reason = USER_STOP_REASON
    clear_work_node_stop(workflow.uuid)
    current_node = get_work_node_by_uuid(database_path, node.uuid) or node
    if _is_work_node_run_in_progress(current_node):
        mark_work_node_run_finished(
            database_path, node.uuid, success=False, fail_reason=reason
        )
    if not any(
        step.work_uuid == node.uuid and step.status == "failed" and step.detail == reason
        for step in steps
    ):
        steps.append(
            WorkflowRunStep(
                kind="work",
                label=node.work_name,
                status="failed",
                detail=reason,
                work_uuid=node.uuid,
            )
        )
    current_wf = get_workflow_by_uuid(database_path, workflow.uuid) or workflow
    wf_end = (current_wf.last_end_date or "").strip()
    if not wf_end:
        finished = mark_workflow_run_finished(database_path, workflow.uuid, success=False)
        _record_workflow_history_on_end(
            database_path,
            workflow_uuid=workflow.uuid,
            tokens=tokens,
            success=False,
            user_idx=int(requester.idx) if requester is not None else 1,
        )
    else:
        finished = current_wf
    return WorkflowRunResult(
        status="failed",
        message=reason,
        workflow=finished or get_workflow_by_uuid(database_path, workflow.uuid),
        steps=steps,
    )


def _load_node_result_text(database_path: Path | str, node: WorkNodeRecord) -> str:
    text = read_work_node_validation_output(
        node.uuid,
        userid=resolve_work_node_upload_userid(database_path, node.owner),
        validate_date=node.last_end_date or node.validate_date,
    )
    if text and text.strip():
        return text.strip()
    return ""


def _previous_result_before_index(
    database_path: Path | str, tokens: list[FlowToken], index: int
) -> str:
    for token in reversed(tokens[: max(0, index)]):
        if token.kind != "work" or not token.work_uuid:
            continue
        node = get_work_node_by_uuid(database_path, token.work_uuid)
        if node is None:
            continue
        text = _load_node_result_text(database_path, node)
        if text:
            return text
    return ""


async def _notify_hitl_approval(
    *,
    database_path: Path | str,
    workflow: WorkflowRecord,
    requester: User,
    approver_userid: str,
    diagram: str,
    previous_result: str,
    resume_index: int,
) -> int:
    approver = get_user_by_userid(database_path, approver_userid)
    if approver is None:
        raise ValueError(f"승인자를 찾을 수 없습니다: {approver_userid}")

    title = f"[작업 워크플로우] {workflow.workflow_name} - 승인을 요청합니다."
    body_md = (
        f"## 작업 워크플로우 승인 요청\n\n"
        f"- 작업 워크플로우: **{workflow.workflow_name}**\n"
        f"- 요청자: {requester.username or requester.userid}\n"
        f"- 단계:\n\n```\n{diagram}\n```\n\n"
        f"## 이전 작업 결과\n\n"
        f"{(previous_result or '(결과 없음)').strip()}\n"
    )
    job = create_job_from_intake(
        database_path,
        JobIntakePayload(
            job_title=title[:300],
            requester_name=(requester.username or requester.userid).strip(),
            requester_email=(requester.email or "").strip() or f"{requester.userid}@local",
            requester_depart=(requester.depart or "").strip() or "-",
            job_content=body_md,
            request_date=now_job_datetime(),
            madang_id=(requester.userid or "").strip(),
            team_id="",
            channel_id="",
            message_id=encode_workflow_job_message_id(workflow.uuid, resume_index),
            job_type=JOB_TYPE_WORKFLOW,
        ),
    )
    try:
        assign_job_approver(database_path, job.idx, approver_userid=approver_userid)
    except ValueError as exc:
        logger.warning("workflow HITL approver assign failed job=%s: %s", job.idx, exc)

    try:
        settings = load_email_settings_from_db(database_path)
        recipient = resolve_recipient_email(database_path, approver_userid)
        if settings is not None and recipient:
            await send_markdown_email(
                settings=settings,
                to_addresses=[recipient],
                subject=title,
                markdown_body=body_md,
            )
        else:
            logger.warning(
                "workflow HITL email skipped workflow=%s approver=%s",
                workflow.uuid,
                approver_userid,
            )
    except Exception:
        logger.exception(
            "workflow HITL email failed workflow=%s approver=%s",
            workflow.uuid,
            approver_userid,
        )
    return job.idx


def _last_work_result_file_path(
    database_path: Path | str,
    tokens: list[FlowToken],
) -> str:
    for token in reversed(tokens):
        if token.kind != "work" or not token.work_uuid:
            continue
        node = get_work_node_by_uuid(database_path, token.work_uuid)
        if node is None:
            continue
        path = work_node_file_path(
            token.work_uuid,
            RESULT_LATEST_FILENAME,
            userid=resolve_work_node_upload_userid(database_path, node.owner),
        )
        if path is not None and path.is_file():
            return str(path.resolve())
    return ""


def _record_workflow_history_on_end(
    database_path: Path | str,
    *,
    workflow_uuid: str,
    tokens: list[FlowToken],
    success: bool,
    user_idx: int = 1,
) -> None:
    finished = get_workflow_by_uuid(database_path, workflow_uuid)
    if finished is None:
        return
    try:
        insert_workflow_history(
            database_path,
            workflow_uuid=finished.uuid,
            start_date=finished.last_start_date,
            end_date=finished.last_end_date,
            finish_success=success,
            result_file=_last_work_result_file_path(database_path, tokens),
            user_idx=user_idx,
        )
    except Exception:
        logger.exception("failed to insert workflow_history uuid=%s", workflow_uuid)


async def _execute_from_index(
    *,
    database_path: Path | str,
    agent_runtime: Any,
    workflow: WorkflowRecord,
    tokens: list[FlowToken],
    start_index: int,
    previous_result: str,
    requester: User | None,
    steps: list[WorkflowRunStep] | None = None,
    mark_hitl_approved: bool = False,
) -> WorkflowRunResult:
    work_names = _work_names_for_tokens(database_path, tokens)
    diagram = _diagram_text(database_path, tokens, work_names)
    steps = list(steps or [])
    previous = previous_result or ""
    index = max(0, int(start_index))
    visited_fail: set[str] = set()

    if mark_hitl_approved:
        steps.append(
            WorkflowRunStep(
                kind="hitl",
                label="승인",
                status="ok",
                detail="승인자가 승인하여 실행을 재개했습니다.",
            )
        )

    while index < len(tokens):
        token = tokens[index]
        if token.kind == "start":
            steps.append(WorkflowRunStep(kind="start", label="시작", status="ok"))
            index += 1
            continue
        if token.kind == "end":
            steps.append(WorkflowRunStep(kind="end", label="종료", status="ok"))
            finished = mark_workflow_run_finished(database_path, workflow.uuid, success=True)
            _record_workflow_history_on_end(
                database_path,
                workflow_uuid=workflow.uuid,
                tokens=tokens,
                success=True,
                user_idx=int(requester.idx) if requester is not None else 1,
            )
            return WorkflowRunResult(
                status="success",
                message="작업 워크플로우가 성공적으로 완료되었습니다.",
                workflow=finished or get_workflow_by_uuid(database_path, workflow.uuid),
                steps=steps,
            )
        hitl_info = _hitl_info_for_token(database_path, token)
        if hitl_info is not None:
            userid, hitl_work_uuid = hitl_info
            if requester is None:
                raise ValueError("승인 요청을 생성하려면 요청자 정보가 필요합니다.")
            steps.append(
                WorkflowRunStep(
                    kind="hitl",
                    label=f"승인:{userid}",
                    status="awaiting",
                    detail="승인 요청을 생성했습니다.",
                    work_uuid=hitl_work_uuid,
                )
            )
            job_idx = await _notify_hitl_approval(
                database_path=database_path,
                workflow=workflow,
                requester=requester,
                approver_userid=userid,
                diagram=diagram,
                previous_result=previous,
                resume_index=index + 1,
            )
            current = get_workflow_by_uuid(database_path, workflow.uuid)
            return WorkflowRunResult(
                status="awaiting_approval",
                message=f"승인자({userid})에게 승인 요청을 보냈습니다.",
                workflow=current,
                steps=steps,
                job_idx=job_idx,
            )

        if token.kind != "work" or not token.work_uuid:
            raise ValueError(f"지원하지 않는 토큰입니다: {token.raw}")

        node = get_work_node_by_uuid(database_path, token.work_uuid)
        if node is None:
            reason = f"작업노드를 찾을 수 없습니다: {token.work_uuid}"
            steps.append(
                WorkflowRunStep(
                    kind="work",
                    label=token.work_uuid,
                    status="failed",
                    detail=reason,
                    work_uuid=token.work_uuid,
                )
            )
            finished = mark_workflow_run_finished(database_path, workflow.uuid, success=False)
            return WorkflowRunResult(
                status="failed",
                message=reason,
                workflow=finished,
                steps=steps,
            )

        mark_work_node_run_started(database_path, node.uuid)
        try:
            await _await_work_node_schedule_if_needed(
                database_path, node, workflow_uuid=workflow.uuid
            )
            attachment_text = _attachment_context_from_previous_hitl(
                database_path, tokens, index
            )
            message = _build_agent_message(
                node, previous, attachment_text=attachment_text
            )
            content = await _invoke_work_node(
                database_path=database_path,
                agent_runtime=agent_runtime,
                node=node,
                message=message,
                workflow_uuid=workflow.uuid,
            )
            _assert_structured_work_success(node.script_type, content)
            finished_node = mark_work_node_run_finished(database_path, node.uuid, success=True)
            stamp = (
                finished_node.last_end_date
                if finished_node is not None
                else now_job_datetime()
            )
            try:
                write_work_node_validation_output(
                    node.uuid,
                    userid=resolve_work_node_upload_userid(database_path, node.owner),
                    validate_date=stamp,
                    message=content,
                )
            except (ValueError, OSError):
                logger.exception("failed to write work_node result uuid=%s", node.uuid)
            await _maybe_send_work_report_email(
                database_path, node=node, result_content=content
            )
            previous = content
            steps.append(
                WorkflowRunStep(
                    kind="work",
                    label=node.work_name,
                    status="ok",
                    detail="수행 완료",
                    work_uuid=node.uuid,
                )
            )
            index += 1
            continue
        except WorkflowStopRequested:
            return _finalize_user_stop(
                database_path,
                workflow=workflow,
                tokens=tokens,
                node=node,
                steps=steps,
                requester=requester,
            )
        except Exception as exc:
            reason = str(exc)[:200]
            mark_work_node_run_finished(
                database_path, node.uuid, success=False, fail_reason=reason
            )
            steps.append(
                WorkflowRunStep(
                    kind="work",
                    label=node.work_name,
                    status="failed",
                    detail=reason,
                    work_uuid=node.uuid,
                )
            )
            if token.fail_work_uuid and token.fail_work_uuid not in visited_fail:
                visited_fail.add(token.fail_work_uuid)
                fail_node = get_work_node_by_uuid(database_path, token.fail_work_uuid)
                if fail_node is None:
                    finished = mark_workflow_run_finished(
                        database_path, workflow.uuid, success=False
                    )
                    return WorkflowRunResult(
                        status="failed",
                        message=f"실패 분기 작업노드를 찾을 수 없습니다: {token.fail_work_uuid}",
                        workflow=finished,
                        steps=steps,
                    )
                mark_work_node_run_started(database_path, fail_node.uuid)
                try:
                    await _await_work_node_schedule_if_needed(
                        database_path, fail_node, workflow_uuid=workflow.uuid
                    )
                    fail_message = _build_agent_message(
                        fail_node,
                        previous,
                        attachment_text=_attachment_context_from_previous_hitl(
                            database_path, tokens, index
                        ),
                    )
                    fail_content = await _invoke_work_node(
                        database_path=database_path,
                        agent_runtime=agent_runtime,
                        node=fail_node,
                        message=fail_message,
                        workflow_uuid=workflow.uuid,
                    )
                    _assert_structured_work_success(fail_node.script_type, fail_content)
                    finished_fail = mark_work_node_run_finished(
                        database_path, fail_node.uuid, success=True
                    )
                    stamp = (
                        finished_fail.last_end_date
                        if finished_fail is not None
                        else now_job_datetime()
                    )
                    try:
                        write_work_node_validation_output(
                            fail_node.uuid,
                            userid=resolve_work_node_upload_userid(
                                database_path, fail_node.owner
                            ),
                            validate_date=stamp,
                            message=fail_content,
                        )
                    except (ValueError, OSError):
                        logger.exception(
                            "failed to write fail-branch result uuid=%s", fail_node.uuid
                        )
                    await _maybe_send_work_report_email(
                        database_path, node=fail_node, result_content=fail_content
                    )
                    previous = fail_content
                    steps.append(
                        WorkflowRunStep(
                            kind="work",
                            label=fail_node.work_name,
                            status="ok",
                            detail="실패 분기 수행 완료",
                            work_uuid=fail_node.uuid,
                        )
                    )
                    index += 1
                    continue
                except WorkflowStopRequested:
                    return _finalize_user_stop(
                        database_path,
                        workflow=workflow,
                        tokens=tokens,
                        node=fail_node,
                        steps=steps,
                        requester=requester,
                    )
                except Exception as fail_exc:
                    fail_reason = str(fail_exc)[:200]
                    mark_work_node_run_finished(
                        database_path,
                        fail_node.uuid,
                        success=False,
                        fail_reason=fail_reason,
                    )
                    steps.append(
                        WorkflowRunStep(
                            kind="work",
                            label=fail_node.work_name,
                            status="failed",
                            detail=fail_reason,
                            work_uuid=fail_node.uuid,
                        )
                    )
                    finished = mark_workflow_run_finished(
                        database_path, workflow.uuid, success=False
                    )
                    return WorkflowRunResult(
                        status="failed",
                        message=f"실패 분기 수행 실패: {fail_reason}",
                        workflow=finished,
                        steps=steps,
                    )
            finished = mark_workflow_run_finished(database_path, workflow.uuid, success=False)
            return WorkflowRunResult(
                status="failed",
                message=reason,
                workflow=finished,
                steps=steps,
            )

    finished = mark_workflow_run_finished(database_path, workflow.uuid, success=False)
    return WorkflowRunResult(
        status="failed",
        message="작업 워크플로우가 종료 토큰 없이 중단되었습니다.",
        workflow=finished,
        steps=steps,
    )


async def run_workflow(
    *,
    database_path: Path | str,
    agent_runtime: Any,
    workflow_uuid: str,
    requester: User,
) -> WorkflowRunResult:
    workflow = get_workflow_by_uuid(database_path, workflow_uuid)
    if workflow is None:
        raise ValueError("작업 워크플로우를 찾을 수 없습니다.")

    tokens = parse_workflow_document(workflow.workflow)
    if not tokens:
        raise ValueError("작업 워크플로우 표현식이 비어 있습니다.")
    if tokens[0].kind != "start" or tokens[-1].kind != "end":
        raise ValueError("작업 워크플로우는 S로 시작하고 E로 끝나야 합니다.")

    started = mark_workflow_run_started(database_path, workflow.uuid)
    if started is None:
        raise ValueError("작업 워크플로우 실행 시작 기록에 실패했습니다.")
    clear_work_node_stop(workflow.uuid)

    return await _execute_from_index(
        database_path=database_path,
        agent_runtime=agent_runtime,
        workflow=started,
        tokens=tokens,
        start_index=0,
        previous_result="",
        requester=requester,
    )


async def resume_workflow_after_approval(
    *,
    database_path: Path | str,
    agent_runtime: Any,
    job: JobRecord,
) -> WorkflowRunResult | None:
    """Continue from the token after HITL when a workflow approval job is approved.

    Next token may be another work node, another HITL, or End (success).
    """
    if int(job.job_type) != JOB_TYPE_WORKFLOW:
        return None
    parsed = parse_workflow_job_message_id(job.message_id)
    if parsed is None:
        logger.warning("workflow job missing resume cursor job=%s message_id=%s", job.idx, job.message_id)
        return None
    workflow_uuid, resume_index = parsed
    workflow = get_workflow_by_uuid(database_path, workflow_uuid)
    if workflow is None:
        raise ValueError(f"승인 재개 대상 작업 워크플로우를 찾을 수 없습니다: {workflow_uuid}")
    tokens = parse_workflow_document(workflow.workflow)
    if not tokens:
        raise ValueError("작업 워크플로우 표현식이 비어 있습니다.")
    if resume_index < 0 or resume_index >= len(tokens):
        raise ValueError(f"승인 재개 위치가 올바르지 않습니다: {resume_index}")

    requester = get_user_by_userid(database_path, (job.madang_id or "").strip())
    previous = _previous_result_before_index(database_path, tokens, resume_index)
    return await _execute_from_index(
        database_path=database_path,
        agent_runtime=agent_runtime,
        workflow=workflow,
        tokens=tokens,
        start_index=resume_index,
        previous_result=previous,
        requester=requester,
        mark_hitl_approved=True,
    )


def fail_workflow_after_rejection(database_path: Path | str, job: JobRecord) -> WorkflowRecord | None:
    """Mark workflow run as failed when HITL approval is rejected."""
    if int(job.job_type) != JOB_TYPE_WORKFLOW:
        return None
    parsed = parse_workflow_job_message_id(job.message_id)
    if parsed is None:
        return None
    workflow_uuid, _ = parsed
    clear_work_node_stop(workflow_uuid)
    return mark_workflow_run_finished(database_path, workflow_uuid, success=False)


def _is_work_node_run_in_progress(node: WorkNodeRecord) -> bool:
    start = (node.last_start_date or "").strip()
    end = (node.last_end_date or "").strip()
    if not start:
        return False
    if not end:
        return True
    return start > end


def stop_running_work_node(
    database_path: Path | str,
    *,
    workflow_uuid: str,
    work_uuid: str,
) -> WorkflowRecord:
    """Request stop of a running work node and mark workflow failed.

    The active runner cooperatively cancels the agent invoke / schedule wait
    and finalizes. This call also updates DB immediately so the UI unlocks.
    """
    workflow = get_workflow_by_uuid(database_path, workflow_uuid)
    if workflow is None:
        raise ValueError("작업 워크플로우를 찾을 수 없습니다.")
    wf_start = (workflow.last_start_date or "").strip()
    wf_end = (workflow.last_end_date or "").strip()
    if not wf_start or (wf_end and wf_start <= wf_end):
        raise ValueError("실행 중인 작업 워크플로우가 아닙니다.")

    node = get_work_node_by_uuid(database_path, work_uuid)
    if node is None:
        raise ValueError("작업노드를 찾을 수 없습니다.")
    referenced = {u.lower() for u in work_uuids_from_expression(workflow.workflow)}
    if node.uuid.lower() not in referenced:
        raise ValueError("이 작업 워크플로우에 속하지 않는 작업노드입니다.")
    if not _is_work_node_run_in_progress(node):
        raise ValueError("실행 중인 작업노드가 아닙니다.")

    request_work_node_stop(workflow.uuid, node.uuid)
    mark_work_node_run_finished(
        database_path, node.uuid, success=False, fail_reason=USER_STOP_REASON
    )
    finished = mark_workflow_run_finished(database_path, workflow.uuid, success=False)
    if finished is None:
        raise ValueError("작업 워크플로우 종료 기록에 실패했습니다.")
    tokens = parse_workflow_document(workflow.workflow)
    _record_workflow_history_on_end(
        database_path,
        workflow_uuid=workflow.uuid,
        tokens=tokens,
        success=False,
        user_idx=int(getattr(workflow, "owner", 1) or 1),
    )
    return finished
