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
    mark_workflow_run_started,
    set_work_node_schedule_wait,
)
from backend.app.notifications.email_sender import (
    load_email_settings_from_db,
    resolve_recipient_email,
    send_markdown_email,
)
from backend.app.services.agent_runtime_client import AgentInvokeRequest
from backend.app.services.k8s_scrape_scheduler import cron_matches_minute
from backend.app.services.workflow_graph import FlowToken, parse_workflow_tokens
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

logger = logging.getLogger(__name__)

_WORKFLOW_JOB_MESSAGE_RE = re.compile(
    r"^workflow:(?P<uuid>[0-9a-fA-F-]{36}):(?P<index>\d+)$"
)


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
class WorkflowRunResult:
    status: str  # success | failed | awaiting_approval
    message: str
    workflow: WorkflowRecord | None = None
    steps: list[WorkflowRunStep] = field(default_factory=list)
    job_idx: int | None = None


def encode_workflow_job_message_id(workflow_uuid: str, resume_index: int) -> str:
    return f"workflow:{workflow_uuid.strip().lower()}:{int(resume_index)}"


def parse_workflow_job_message_id(message_id: str) -> tuple[str, int] | None:
    match = _WORKFLOW_JOB_MESSAGE_RE.match((message_id or "").strip())
    if not match:
        return None
    return match.group("uuid").lower(), int(match.group("index"))


def resolve_awaiting_hitl_from_job(
    *,
    workflow_expression: str,
    message_id: str,
) -> tuple[str, str] | None:
    """Return (graph_node_id, userid) for the HITL token waiting on this job."""
    parsed = parse_workflow_job_message_id(message_id)
    if parsed is None:
        return None
    _, resume_index = parsed
    hitl_index = int(resume_index) - 1
    if hitl_index < 0:
        return None
    tokens = parse_workflow_tokens(workflow_expression)
    if hitl_index >= len(tokens):
        return None
    token = tokens[hitl_index]
    if token.kind != "hitl" or not (token.userid or "").strip():
        return None
    userid = token.userid.strip()
    return f"H:{userid}@{hitl_index}", userid


def _diagram_text(tokens: list[FlowToken], work_names: dict[str, str]) -> str:
    parts: list[str] = []
    for token in tokens:
        if token.kind == "start":
            parts.append("시작(S)")
        elif token.kind == "end":
            parts.append("종료(E)")
        elif token.kind == "hitl":
            parts.append(f"승인(H:{token.userid})")
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


def _build_agent_message(node: WorkNodeRecord, previous_result: str) -> str:
    script = (node.work_script or "").strip()
    if not script:
        raise ValueError(f"작업 스크립트가 비어 있습니다: {node.work_name}")
    wrapped = _wrap_work_script_for_execution(node.script_type, script)
    return _append_previous_result(
        wrapped,
        previous_result,
        use_previous=bool(node.use_previous_work_result),
    )


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
) -> str:
    agent_id = _resolve_invoke_agent_id(database_path, node.target_agent)
    result = await agent_runtime.invoke(
        AgentInvokeRequest(
            agent_id=agent_id,
            message=message,
            session_id=f"workflow-{node.uuid}",
            agentruntime_idx=int(node.target_agent),
        )
    )
    content = str(getattr(result, "content", "") or "").strip()
    if not content:
        raise ValueError("에이전트 응답이 비어 있습니다.")
    return content


def _load_node_result_text(node: WorkNodeRecord) -> str:
    text = read_work_node_validation_output(
        node.uuid,
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
        text = _load_node_result_text(node)
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


def _last_work_result_file_path(tokens: list[FlowToken]) -> str:
    for token in reversed(tokens):
        if token.kind != "work" or not token.work_uuid:
            continue
        path = work_node_file_path(token.work_uuid, RESULT_LATEST_FILENAME)
        if path is not None:
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
            result_file=_last_work_result_file_path(tokens),
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
    diagram = _diagram_text(tokens, work_names)
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
        if token.kind == "hitl":
            userid = (token.userid or "").strip()
            if requester is None:
                raise ValueError("승인 요청을 생성하려면 요청자 정보가 필요합니다.")
            steps.append(
                WorkflowRunStep(
                    kind="hitl",
                    label=f"승인:{userid}",
                    status="awaiting",
                    detail="승인 요청을 생성했습니다.",
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
            await _await_work_node_schedule_if_needed(database_path, node)
            message = _build_agent_message(node, previous)
            content = await _invoke_work_node(
                database_path=database_path,
                agent_runtime=agent_runtime,
                node=node,
                message=message,
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
                    await _await_work_node_schedule_if_needed(database_path, fail_node)
                    fail_message = _build_agent_message(fail_node, previous)
                    fail_content = await _invoke_work_node(
                        database_path=database_path,
                        agent_runtime=agent_runtime,
                        node=fail_node,
                        message=fail_message,
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

    tokens = parse_workflow_tokens(workflow.workflow)
    if not tokens:
        raise ValueError("작업 워크플로우 표현식이 비어 있습니다.")
    if tokens[0].kind != "start" or tokens[-1].kind != "end":
        raise ValueError("작업 워크플로우는 S로 시작하고 E로 끝나야 합니다.")

    started = mark_workflow_run_started(database_path, workflow.uuid)
    if started is None:
        raise ValueError("작업 워크플로우 실행 시작 기록에 실패했습니다.")

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
    tokens = parse_workflow_tokens(workflow.workflow)
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
    return mark_workflow_run_finished(database_path, workflow_uuid, success=False)
