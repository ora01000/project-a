"""CRUD APIs for work_node and workflow designer (owner / distribute model)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.config import (
    PROJECT_ROOT,
    WORKFLOW_HISTORY_RESULT_FILENAME,
    attachment_dir,
    attachment_relative_path,
    find_work_node_upload_dir,
    list_work_node_result_outputs,
    new_attachment_timestamp,
    normalize_work_node_filename,
    read_work_node_result_output,
    read_work_node_run_result,
    read_work_node_validation_output,
    read_workflow_history_result,
    remove_work_node_upload_dirs,
    remove_workflow_upload_dirs,
    resolve_attachment_dir,
    sanitize_upload_userid,
    work_node_run_upload_dir,
    work_node_upload_dir,
    workflow_history_result_path,
    workflow_template_dir,
    write_work_node_validation_output,
)
from backend.app.db.agentruntime import get_agentruntime_by_idx
from backend.app.db.job_datetime import now_job_datetime
from backend.app.db.jobs import (
    JobRecord,
    find_pending_workflow_approval_job,
    get_job_by_idx,
    map_pending_workflow_approval_jobs,
)
from backend.app.db.roles import ROLE_ADMIN, ROLE_INFRAADMIN, can_manage_workflow_templates
from backend.app.db.users import get_user_by_idx, list_users
from backend.app.db.workflow import (
    WorkNodeRecord,
    WorkflowHistoryRecord,
    WorkflowRecord,
    clone_workflow,
    create_work_node,
    create_workflow,
    delete_work_node,
    delete_workflow,
    get_work_node_by_uuid,
    get_workflow_by_uuid,
    get_workflow_history_by_idx,
    list_work_node_history,
    list_work_nodes_visible,
    list_workflow_history,
    list_workflows_visible,
    normalize_crud,
    normalize_script_type,
    resolve_work_node_upload_userid,
    resolve_workflow_history_userid,
    find_workflow_uuid_for_work_node,
    get_work_node_history_by_idx,
    set_workflow_distribute,
    set_work_node_upload_path,
    update_work_node,
    update_workflow,
    user_can_view_workflow,
    user_owns_workflow,
    work_uuids_from_expression,
)
from backend.app.db.workflow_template import (
    create_workflow_template,
    get_workflow_template_by_filename,
    get_workflow_template_by_idx,
    get_workflow_template_by_name,
    list_workflow_templates,
    read_workflow_template_content,
    sanitize_template_filename,
    sanitize_template_name,
    seed_workflow_templates_from_docs,
    sync_disk_templates_to_db,
    update_workflow_template,
)
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.logging.workflow_logger import read_work_node_agent_log
from backend.app.services.workflow_graph import build_workflow_graph
from backend.app.services.workflow_document import validate_workflow_document
from backend.app.services.workflow_runner import (
    WorkflowRunResult,
    resolve_awaiting_hitl_from_job,
    resolve_hitl_work_uuid_from_job,
    run_workflow,
    stop_running_work_node,
)
from backend.app.services.workflow_template_cache import (
    add_template_to_cache,
    cached_template_filename_exists,
    cached_template_name_exists,
    refresh_workflow_template_cache,
    replace_template_in_cache,
)

router = APIRouter(tags=["workflow"])
logger = logging.getLogger(__name__)

WORKFLOW_FRONT_DIR = PROJECT_ROOT / "docs" / "workflow_front"
WORKFLOW_FRONT_MD = WORKFLOW_FRONT_DIR / "workflow_front.md"


class WorkflowTemplateListItem(BaseModel):
    idx: int = 0
    template_name: str
    template_filename: str
    # Backward-compatible alias used by older clients (filename).
    name: str = ""


class WorkflowTemplateResponse(BaseModel):
    idx: int = 0
    template_name: str = ""
    template_filename: str = ""
    name: str
    content: str
    update_date: str = ""
    created_by: int = 0


class WorkflowTemplateWriteRequest(BaseModel):
    template_name: str = Field(min_length=1, max_length=70)
    template_filename: str = Field(min_length=1, max_length=200)
    content: str = ""


class WorkflowTemplateCheckResponse(BaseModel):
    template_name: str = ""
    template_filename: str = ""
    name_available: bool = True
    filename_available: bool = True
    name_error: str = ""
    filename_error: str = ""


class WorkflowFrontGuideResponse(BaseModel):
    content: str


def _ensure_templates_ready(database_path) -> None:
    seeded = seed_workflow_templates_from_docs(database_path)
    synced = sync_disk_templates_to_db(database_path)
    if seeded or synced:
        logger.info(
            "workflow templates ready seeded=%s synced=%s",
            seeded,
            synced,
        )


def _template_list_item(record) -> WorkflowTemplateListItem:
    return WorkflowTemplateListItem(
        idx=record.idx,
        template_name=record.template_name,
        template_filename=record.template_filename,
        name=record.template_filename,
    )


@router.get("/workflow-templates", response_model=list[WorkflowTemplateListItem])
async def api_list_workflow_templates(request: Request) -> list[WorkflowTemplateListItem]:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    _ensure_templates_ready(database_path)
    records = list_workflow_templates(database_path)
    try:
        await refresh_workflow_template_cache(database_path)
    except Exception:
        logger.exception("workflow template cache refresh failed")
    return [_template_list_item(row) for row in records]


@router.get("/workflow-templates/check", response_model=WorkflowTemplateCheckResponse)
async def api_check_workflow_template(
    request: Request,
    template_name: str = "",
    template_filename: str = "",
    exclude_idx: int = 0,
) -> WorkflowTemplateCheckResponse:
    auth_user = get_request_auth_user(request)
    if not can_manage_workflow_templates(int(auth_user.role)):
        raise HTTPException(status_code=403, detail="템플릿을 관리할 권한이 없습니다.")
    database_path = request.app.state.database_path
    _ensure_templates_ready(database_path)
    skip_idx = int(exclude_idx or 0)
    result = WorkflowTemplateCheckResponse(
        template_name=(template_name or "").strip(),
        template_filename=(template_filename or "").strip(),
    )
    if result.template_name:
        try:
            sanitize_template_name(result.template_name)
        except ValueError as exc:
            result.name_available = False
            result.name_error = str(exc)
        else:
            conflict = get_workflow_template_by_name(database_path, result.template_name)
            taken = conflict is not None and (skip_idx <= 0 or conflict.idx != skip_idx)
            if not taken and skip_idx <= 0:
                taken = await cached_template_name_exists(database_path, result.template_name)
                if taken:
                    conflict = get_workflow_template_by_name(database_path, result.template_name)
                    taken = conflict is not None
            if taken:
                result.name_available = False
                result.name_error = f"이미 존재하는 양식 이름입니다: {result.template_name}"
    if result.template_filename:
        try:
            normalized = sanitize_template_filename(result.template_filename)
            result.template_filename = normalized
        except ValueError as exc:
            result.filename_available = False
            result.filename_error = str(exc)
        else:
            conflict = get_workflow_template_by_filename(database_path, normalized)
            taken = conflict is not None and (skip_idx <= 0 or conflict.idx != skip_idx)
            if not taken and skip_idx <= 0:
                taken = await cached_template_filename_exists(database_path, normalized)
                if taken:
                    conflict = get_workflow_template_by_filename(database_path, normalized)
                    taken = conflict is not None
            if taken:
                result.filename_available = False
                result.filename_error = f"이미 존재하는 파일명입니다: {normalized}"
    return result


@router.post("/workflow-templates", response_model=WorkflowTemplateResponse, status_code=201)
async def api_create_workflow_template(
    body: WorkflowTemplateWriteRequest,
    request: Request,
) -> WorkflowTemplateResponse:
    auth_user = get_request_auth_user(request)
    if not can_manage_workflow_templates(int(auth_user.role)):
        raise HTTPException(status_code=403, detail="템플릿을 관리할 권한이 없습니다.")
    database_path = request.app.state.database_path
    _ensure_templates_ready(database_path)
    try:
        name = sanitize_template_name(body.template_name)
        filename = sanitize_template_filename(body.template_filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if await cached_template_name_exists(database_path, name):
        raise HTTPException(status_code=409, detail=f"이미 존재하는 양식 이름입니다: {name}")
    if await cached_template_filename_exists(database_path, filename):
        raise HTTPException(status_code=409, detail=f"이미 존재하는 파일명입니다: {filename}")
    try:
        record = create_workflow_template(
            database_path,
            template_name=name,
            template_filename=filename,
            created_by=int(auth_user.idx),
            content=body.content or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await add_template_to_cache(
        template_name=record.template_name,
        template_filename=record.template_filename,
    )
    try:
        content = read_workflow_template_content(record)
    except FileNotFoundError:
        content = body.content or ""
    return WorkflowTemplateResponse(
        idx=record.idx,
        template_name=record.template_name,
        template_filename=record.template_filename,
        name=record.template_filename,
        content=content,
        update_date=record.update_date,
        created_by=record.created_by,
    )


@router.put("/workflow-templates/{template_idx}", response_model=WorkflowTemplateResponse)
async def api_update_workflow_template(
    template_idx: int,
    body: WorkflowTemplateWriteRequest,
    request: Request,
) -> WorkflowTemplateResponse:
    auth_user = get_request_auth_user(request)
    if not can_manage_workflow_templates(int(auth_user.role)):
        raise HTTPException(status_code=403, detail="템플릿을 관리할 권한이 없습니다.")
    database_path = request.app.state.database_path
    _ensure_templates_ready(database_path)
    existing = get_workflow_template_by_idx(database_path, int(template_idx))
    if existing is None:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    try:
        record = update_workflow_template(
            database_path,
            int(template_idx),
            template_name=body.template_name,
            template_filename=body.template_filename,
            content=body.content or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await replace_template_in_cache(
        old_template_name=existing.template_name,
        old_template_filename=existing.template_filename,
        template_name=record.template_name,
        template_filename=record.template_filename,
    )
    try:
        content = read_workflow_template_content(record)
    except FileNotFoundError:
        content = body.content or ""
    return WorkflowTemplateResponse(
        idx=record.idx,
        template_name=record.template_name,
        template_filename=record.template_filename,
        name=record.template_filename,
        content=content,
        update_date=record.update_date,
        created_by=record.created_by,
    )


@router.get("/workflow-templates/{name}", response_model=WorkflowTemplateResponse)
async def api_get_workflow_template(name: str, request: Request) -> WorkflowTemplateResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    _ensure_templates_ready(database_path)
    try:
        filename = sanitize_template_filename(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = get_workflow_template_by_filename(database_path, filename)
    if record is None:
        # Allow reading an on-disk file that is not yet registered (http manual drop).
        directory = workflow_template_dir()
        path = (directory / filename).resolve()
        try:
            path.relative_to(directory.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid template name") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Template not found")
        return WorkflowTemplateResponse(
            name=filename,
            template_filename=filename,
            template_name=path.stem,
            content=path.read_text(encoding="utf-8"),
        )
    try:
        content = read_workflow_template_content(record)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WorkflowTemplateResponse(
        idx=record.idx,
        template_name=record.template_name,
        template_filename=record.template_filename,
        name=record.template_filename,
        content=content,
        update_date=record.update_date,
        created_by=record.created_by,
    )


@router.get("/workflow-front", response_model=WorkflowFrontGuideResponse)
async def api_get_workflow_front_guide(request: Request) -> WorkflowFrontGuideResponse:
    """Return the idle-state workflow screen guide markdown."""
    get_request_auth_user(request)
    path = WORKFLOW_FRONT_MD.resolve()
    try:
        path.relative_to(WORKFLOW_FRONT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="안내 문서를 찾을 수 없습니다.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="안내 문서를 찾을 수 없습니다.")
    return WorkflowFrontGuideResponse(content=path.read_text(encoding="utf-8"))


class WorkNodeResponse(BaseModel):
    idx: int = 0
    uuid: str
    owner: int = 0
    work_name: str
    work_description: str = ""
    target_agent: int
    target_agent_name: str = ""
    work_script: str
    script_type: str = ""
    test_result: bool
    files: str
    create_date: str = ""
    validate_date: str = ""
    last_start_date: str = ""
    last_end_date: str = ""
    last_success: bool = False
    last_fail_reason: str = ""
    use_previous_work_result: bool = False
    work_report: str = ""
    cron: bool = False
    cron_expr: str = "0 9 * * *"
    schedule_wait: bool = False
    worker: str = "agent"
    upload: bool = False
    upload_path: str = ""
    approver_userid: str = ""
    crud: str = ""
    is_draft: bool = False

    @classmethod
    def from_record(
        cls,
        record: WorkNodeRecord,
        *,
        agent_name: str = "",
        is_draft: bool = False,  # retained for response shape; always False
    ) -> "WorkNodeResponse":
        _ = is_draft
        return cls(
            idx=int(getattr(record, "idx", 0) or 0),
            uuid=record.uuid,
            owner=int(getattr(record, "owner", 0) or 0),
            work_name=record.work_name,
            work_description=record.work_description,
            target_agent=record.target_agent,
            target_agent_name=agent_name,
            work_script=record.work_script,
            script_type=record.script_type,
            test_result=record.test_result,
            files=record.files,
            create_date=record.create_date,
            validate_date=record.validate_date,
            last_start_date=record.last_start_date,
            last_end_date=record.last_end_date,
            last_success=record.last_success,
            last_fail_reason=record.last_fail_reason,
            use_previous_work_result=record.use_previous_work_result,
            work_report=record.work_report,
            cron=bool(getattr(record, "cron", False)),
            cron_expr=str(getattr(record, "cron_expr", None) or "0 9 * * *")[:20],
            schedule_wait=bool(getattr(record, "schedule_wait", False)),
            worker=str(getattr(record, "worker", None) or "agent"),
            upload=bool(getattr(record, "upload", False)),
            upload_path=str(getattr(record, "upload_path", None) or ""),
            approver_userid=str(getattr(record, "approver_userid", None) or ""),
            crud=str(getattr(record, "crud", None) or ""),
            is_draft=False,
        )


class WorkNodeWriteRequest(BaseModel):
    uuid: str | None = Field(default=None, max_length=36)
    work_name: str = Field(default="새 작업노드", max_length=100)
    work_description: str = Field(default="", max_length=500)
    target_agent: int = Field(default=0, ge=0)
    work_script: str = ""
    script_type: str = Field(default="", max_length=20)
    test_result: bool = False
    files: str = Field(default="", max_length=300)
    use_previous_work_result: bool = False
    work_report: str = Field(default="", max_length=400)
    cron: bool | None = None
    cron_expr: str | None = Field(default=None, max_length=20)
    worker: str | None = Field(default=None, max_length=10)
    upload: bool | None = None
    upload_path: str | None = Field(default=None, max_length=500)
    approver_userid: str | None = Field(default=None, max_length=50)
    crud: str | None = Field(default=None, max_length=20)
    validation_message: str | None = None


class WorkflowApproverResponse(BaseModel):
    userid: str
    username: str
    role: int


class WorkflowGraphNode(BaseModel):
    id: str
    kind: str
    label: str
    work_uuid: str | None = None
    userid: str | None = None
    cx: float
    cy: float
    width: int
    height: int


class WorkflowGraphEdge(BaseModel):
    source: str
    target: str
    kind: str


class WorkflowGraph(BaseModel):
    nodes: list[WorkflowGraphNode] = Field(default_factory=list)
    edges: list[WorkflowGraphEdge] = Field(default_factory=list)
    width: int = 200
    height: int = 160


class WorkflowResponse(BaseModel):
    idx: int = 0
    uuid: str
    owner: int = 0
    owner_username: str = ""
    distribute: bool = False
    can_edit: bool = False
    workflow_name: str
    workflow_description: str
    workflow: str
    create_date: str = ""
    test_result: bool = False
    validate_date: str = ""
    last_start_date: str = ""
    last_end_date: str = ""
    cron: bool = False
    cron_expr: str = "0 9 * * *"
    merge_work_result: str = ""
    awaiting_approval: bool = False
    awaiting_hitl_node_id: str = ""
    awaiting_hitl_userid: str = ""
    awaiting_job_idx: int | None = None
    graph: WorkflowGraph

    @classmethod
    def from_record(
        cls,
        record: WorkflowRecord,
        *,
        graph: dict,
        owner_username: str = "",
        can_edit: bool = False,
        awaiting_approval: bool = False,
        awaiting_hitl_node_id: str = "",
        awaiting_hitl_userid: str = "",
        awaiting_job_idx: int | None = None,
    ) -> "WorkflowResponse":
        return cls(
            idx=int(getattr(record, "idx", 0) or 0),
            uuid=record.uuid,
            owner=int(getattr(record, "owner", 0) or 0),
            owner_username=owner_username,
            distribute=bool(getattr(record, "distribute", False)),
            can_edit=can_edit,
            workflow_name=record.workflow_name,
            workflow_description=record.workflow_description,
            workflow=record.workflow,
            create_date=record.create_date,
            test_result=record.test_result,
            validate_date=record.validate_date,
            last_start_date=record.last_start_date,
            last_end_date=record.last_end_date,
            cron=bool(getattr(record, "cron", False)),
            cron_expr=str(getattr(record, "cron_expr", None) or "0 9 * * *")[:20],
            merge_work_result=str(getattr(record, "merge_work_result", None) or "")[:2000],
            awaiting_approval=awaiting_approval,
            awaiting_hitl_node_id=awaiting_hitl_node_id,
            awaiting_hitl_userid=awaiting_hitl_userid,
            awaiting_job_idx=awaiting_job_idx,
            graph=WorkflowGraph.model_validate(graph),
        )


class WorkflowWriteRequest(BaseModel):
    uuid: str | None = Field(default=None, max_length=36)
    workflow_name: str = Field(min_length=1, max_length=100)
    workflow_description: str = Field(default="", max_length=500)
    workflow: str = ""
    cron: bool | None = None
    cron_expr: str | None = Field(default=None, max_length=20)
    merge_work_result: str | None = Field(default=None, max_length=2000)


class WorkflowDistributeRequest(BaseModel):
    distribute: bool


class WorkflowHistoryResponse(BaseModel):
    idx: int
    uuid: str
    start_date: str = ""
    end_date: str = ""
    success: bool = False
    user_idx: int = 1
    username: str = ""

    @classmethod
    def from_record(
        cls,
        record: WorkflowHistoryRecord,
        *,
        username: str = "",
    ) -> "WorkflowHistoryResponse":
        return cls(
            idx=record.idx,
            uuid=record.uuid,
            start_date=record.start_date,
            end_date=record.end_date,
            success=record.success,
            user_idx=int(record.user_idx or 1),
            username=username,
        )


class WorkflowRunStepResponse(BaseModel):
    kind: str
    label: str
    status: str
    detail: str = ""
    work_uuid: str | None = None


class WorkflowRunResponse(BaseModel):
    status: str
    message: str
    job_idx: int | None = None
    steps: list[WorkflowRunStepResponse] = Field(default_factory=list)
    workflow: WorkflowResponse | None = None


def _agent_name(database_path, target_agent: int) -> str:
    if int(target_agent) <= 0:
        return ""
    record = get_agentruntime_by_idx(database_path, target_agent)
    return record.agent_name if record is not None else ""


def _write_validation_output_if_needed(
    database_path,
    record: WorkNodeRecord,
    message: str | None,
) -> None:
    if not record.test_result:
        return
    text = (message or "").strip()
    if not text:
        return
    workflow_uuid = find_workflow_uuid_for_work_node(database_path, record.uuid)
    try:
        write_work_node_validation_output(
            record.uuid,
            userid=resolve_work_node_upload_userid(database_path, record.owner),
            validate_date=record.validate_date or now_job_datetime(),
            message=text,
            workflow_uuid=workflow_uuid or None,
        )
    except (ValueError, OSError):
        return


def _require_agent(database_path, target_agent: int) -> None:
    if int(target_agent) <= 0:
        return
    if get_agentruntime_by_idx(database_path, target_agent) is None:
        raise HTTPException(status_code=400, detail="대상 에이전트를 찾을 수 없습니다.")


def _visible_work_names(database_path, user_idx: int) -> dict[str, str]:
    return {
        node.uuid: node.work_name
        for node in list_work_nodes_visible(database_path, user_idx)
    }


def _visible_work_reports(database_path, user_idx: int) -> set[str]:
    return {
        node.uuid
        for node in list_work_nodes_visible(database_path, user_idx)
        if (node.work_report or "").strip()
    }


def _user_names(database_path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for user in list_users(database_path, viewer_role=ROLE_ADMIN):
        mapping[user.userid] = user.username or user.userid
    return mapping


def _known_userids(database_path) -> set[str]:
    return set(_user_names(database_path).keys())


def _owner_username(database_path, owner: int) -> str:
    if int(owner or 0) <= 0:
        return ""
    user = get_user_by_idx(database_path, int(owner))
    if user is None:
        return ""
    return (user.username or user.userid or "").strip()


def _graph_for(
    database_path,
    expression: str,
    *,
    user_idx: int,
    extra_work_names: dict[str, str] | None = None,
) -> dict:
    names = _visible_work_names(database_path, user_idx)
    if extra_work_names:
        names.update(extra_work_names)
    worker_by_uuid: dict[str, str] = {}
    approver_by_uuid: dict[str, str] = {}
    upload_by_uuid: dict[str, bool] = {}
    for node in list_work_nodes_visible(database_path, user_idx):
        worker_by_uuid[node.uuid] = node.worker or "agent"
        if (node.approver_userid or "").strip():
            approver_by_uuid[node.uuid] = node.approver_userid.strip()
        if bool(getattr(node, "upload", False)):
            upload_by_uuid[node.uuid] = True
    try:
        return build_workflow_graph(
            expression,
            work_names=names,
            user_names=_user_names(database_path),
            work_report_uuids=_visible_work_reports(database_path, user_idx),
            worker_by_uuid=worker_by_uuid,
            approver_by_uuid=approver_by_uuid,
            upload_by_uuid=upload_by_uuid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate_expression(
    database_path,
    expression: str,
    *,
    user_idx: int,
    extra_work_uuids: set[str] | None = None,
) -> None:
    text = (expression or "").strip()
    if not text:
        return
    known = set(_visible_work_names(database_path, user_idx).keys())
    if extra_work_uuids:
        known |= extra_work_uuids
    try:
        validate_workflow_document(
            text,
            known_work_uuids=known,
            known_userids=_known_userids(database_path),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _awaiting_hitl_fields(
    database_path,
    record: WorkflowRecord,
    pending_job: JobRecord | None,
) -> tuple[bool, str, str]:
    if pending_job is None:
        return False, "", ""
    resolved = resolve_awaiting_hitl_from_job(
        workflow_expression=record.workflow,
        message_id=pending_job.message_id,
        database_path=database_path,
    )
    if resolved is None:
        return True, "", ""
    node_id, userid = resolved
    return True, node_id, userid


def _require_view_workflow(record: WorkflowRecord, user_idx: int) -> None:
    if not user_can_view_workflow(record, user_idx):
        raise HTTPException(status_code=403, detail="이 작업 워크플로우를 조회할 권한이 없습니다.")


def _require_own_workflow(record: WorkflowRecord, user_idx: int) -> None:
    if not user_owns_workflow(record, user_idx):
        raise HTTPException(status_code=403, detail="소유자만 수정할 수 있습니다.")


def _require_own_work_node(record: WorkNodeRecord, user_idx: int) -> None:
    if int(getattr(record, "owner", 0) or 0) != int(user_idx):
        raise HTTPException(status_code=403, detail="소유자만 수정할 수 있습니다.")


def _workflow_response(
    database_path,
    record: WorkflowRecord,
    *,
    user_idx: int,
    pending_job: JobRecord | None = None,
) -> WorkflowResponse:
    job = pending_job
    if job is None and record.uuid:
        job = find_pending_workflow_approval_job(database_path, record.uuid)
    awaiting_approval, awaiting_hitl_node_id, awaiting_hitl_userid = _awaiting_hitl_fields(
        database_path, record, job
    )
    return WorkflowResponse.from_record(
        record,
        graph=_graph_for(database_path, record.workflow, user_idx=user_idx),
        owner_username=_owner_username(database_path, int(getattr(record, "owner", 0) or 0)),
        can_edit=user_owns_workflow(record, user_idx),
        awaiting_approval=awaiting_approval,
        awaiting_hitl_node_id=awaiting_hitl_node_id,
        awaiting_hitl_userid=awaiting_hitl_userid,
        awaiting_job_idx=int(job.idx) if job is not None else None,
    )


@router.get("/work-nodes", response_model=list[WorkNodeResponse])
async def api_list_work_nodes(request: Request) -> list[WorkNodeResponse]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    records = list_work_nodes_visible(database_path, auth_user.idx)
    return [
        WorkNodeResponse.from_record(
            record,
            agent_name=_agent_name(database_path, record.target_agent),
        )
        for record in sorted(records, key=lambda item: (item.create_date, item.uuid))
    ]


@router.post("/work-nodes", response_model=WorkNodeResponse, status_code=201)
async def api_create_work_node(body: WorkNodeWriteRequest, request: Request) -> WorkNodeResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    _require_agent(database_path, body.target_agent)
    try:
        script_type = normalize_script_type(body.script_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        record = create_work_node(
            database_path,
            work_name=body.work_name,
            work_description=body.work_description,
            target_agent=body.target_agent,
            work_script=body.work_script,
            script_type=script_type,
            test_result=body.test_result,
            files=normalize_work_node_filename(body.files),
            use_previous_work_result=body.use_previous_work_result,
            work_report=body.work_report,
            cron=bool(body.cron) if body.cron is not None else False,
            cron_expr=body.cron_expr,
            uuid=body.uuid,
            owner=auth_user.idx,
            worker=body.worker or "agent",
            upload=bool(body.upload) if body.upload is not None else False,
            upload_path=body.upload_path or "",
            approver_userid=body.approver_userid or "",
            crud=normalize_crud(body.crud) if body.crud is not None else "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_validation_output_if_needed(database_path, record, body.validation_message)
    return WorkNodeResponse.from_record(
        record, agent_name=_agent_name(database_path, record.target_agent)
    )


@router.put("/work-nodes/{node_uuid}", response_model=WorkNodeResponse)
async def api_update_work_node(
    node_uuid: str,
    body: WorkNodeWriteRequest,
    request: Request,
) -> WorkNodeResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_work_node_by_uuid(database_path, node_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _require_own_work_node(existing, auth_user.idx)
    _require_agent(database_path, body.target_agent)
    try:
        script_type = normalize_script_type(body.script_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        record = update_work_node(
            database_path,
            existing.uuid,
            work_name=body.work_name.strip() or "새 작업노드",
            work_description=(body.work_description or "").strip()[:500],
            target_agent=int(body.target_agent),
            work_script=body.work_script,
            script_type=script_type,
            test_result=bool(body.test_result),
            files=normalize_work_node_filename(body.files),
            use_previous_work_result=bool(body.use_previous_work_result),
            work_report=(body.work_report or "").strip()[:400],
            cron=body.cron,
            cron_expr=body.cron_expr,
            worker=body.worker,
            upload=body.upload,
            upload_path=body.upload_path,
            approver_userid=body.approver_userid,
            crud=body.crud,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _write_validation_output_if_needed(database_path, record, body.validation_message)
    return WorkNodeResponse.from_record(
        record, agent_name=_agent_name(database_path, record.target_agent)
    )


@router.delete("/work-nodes/{node_uuid}")
async def api_delete_work_node(node_uuid: str, request: Request) -> dict[str, bool]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_work_node_by_uuid(database_path, node_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _require_own_work_node(existing, auth_user.idx)
    workflow_uuid = find_workflow_uuid_for_work_node(database_path, existing.uuid)
    owner_userid = resolve_work_node_upload_userid(database_path, existing.owner)
    userids = {owner_userid, sanitize_upload_userid(auth_user.userid) or auth_user.userid}
    if not delete_work_node(database_path, node_uuid):
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    remove_work_node_upload_dirs(
        existing.uuid,
        userids=userids,
        workflow_uuid=workflow_uuid or None,
    )
    return {"ok": True}


@router.get("/workflow-approvers", response_model=list[WorkflowApproverResponse])
async def api_list_workflow_approvers(request: Request) -> list[WorkflowApproverResponse]:
    get_request_auth_user(request)
    users = list_users(request.app.state.database_path, viewer_role=ROLE_ADMIN)
    return [
        WorkflowApproverResponse(userid=user.userid, username=user.username, role=user.role)
        for user in users
        if user.role in {ROLE_ADMIN, ROLE_INFRAADMIN} and user.userid.strip()
    ]


def _require_visible_work_node(request: Request, node_uuid: str) -> WorkNodeRecord:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_work_node_by_uuid(database_path, node_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    visible = {node.uuid for node in list_work_nodes_visible(database_path, auth_user.idx)}
    if record.uuid not in visible:
        raise HTTPException(status_code=403, detail="이 작업노드를 조회할 권한이 없습니다.")
    return record


def _latest_work_node_run_result_content(
    database_path,
    *,
    workflow_uuid: str,
    work_uuid: str,
    userid: str,
) -> str | None:
    """Newest run-scoped ``result.out`` for this node in the workflow's latest runs."""
    wf = (workflow_uuid or "").strip()
    wn = (work_uuid or "").strip()
    if not wf or not wn:
        return None
    histories = list_workflow_history(database_path, wf)
    # Prefer finished runs, then any open run that already has node output.
    ordered = sorted(
        histories,
        key=lambda row: (0 if (row.end_date or "").strip() else 1, -int(row.idx or 0)),
    )
    for history in ordered:
        try:
            node_histories = list_work_node_history(
                database_path, wn, workflow_history_idx=int(history.idx)
            )
        except Exception:
            continue
        for node_history in node_histories:
            try:
                content = read_work_node_run_result(
                    wf,
                    wn,
                    int(history.idx),
                    int(node_history.idx),
                    userid=userid,
                )
            except (ValueError, OSError):
                continue
            if content is not None and content.strip():
                return content
    return None


@router.get("/work-nodes/{node_uuid}/results")
async def api_list_work_node_results(
    node_uuid: str,
    request: Request,
    workflow_uuid: str | None = None,
) -> dict[str, object]:
    """List saved work-node result files (run-scoped ``result.out`` and legacy archives)."""
    record = _require_visible_work_node(request, node_uuid)
    database_path = request.app.state.database_path
    upload_userid = resolve_work_node_upload_userid(database_path, record.owner)
    wf = (workflow_uuid or "").strip() or find_workflow_uuid_for_work_node(
        database_path, record.uuid
    )
    try:
        items = list_work_node_result_outputs(
            record.uuid, userid=upload_userid, workflow_uuid=wf or None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enriched: list[dict[str, object]] = []
    for item in items:
        row = dict(item)
        wnh_idx = int(row.get("work_node_history_idx") or 0)
        if wnh_idx > 0:
            history = get_work_node_history_by_idx(database_path, wnh_idx)
            if history is not None and history.uuid == record.uuid:
                in_progress = not (history.end_date or "").strip()
                row["start_date"] = history.start_date
                row["end_date"] = history.end_date
                row["in_progress"] = in_progress
                row["success"] = False if in_progress else bool(history.success)
        enriched.append(row)
    node_in_progress = bool((record.last_start_date or "").strip()) and not bool(
        (record.last_end_date or "").strip()
    )
    return {
        "items": enriched,
        "work_name": record.work_name,
        "validate_date": record.validate_date or record.last_end_date or "",
        "last_start_date": record.last_start_date or "",
        "last_end_date": record.last_end_date or "",
        "last_success": bool(record.last_success),
        "in_progress": node_in_progress,
        "workflow_uuid": wf,
    }


@router.get("/work-nodes/{node_uuid}/validation-result")
async def api_get_work_node_validation_result(
    node_uuid: str,
    request: Request,
    filename: str | None = None,
    workflow_uuid: str | None = None,
) -> dict[str, str]:
    """Return saved run/validation output (run-scoped ``result.out``, with legacy fallback)."""
    record = _require_visible_work_node(request, node_uuid)
    database_path = request.app.state.database_path
    upload_userid = resolve_work_node_upload_userid(database_path, record.owner)
    wf = (workflow_uuid or "").strip() or find_workflow_uuid_for_work_node(
        database_path, record.uuid
    )
    try:
        if filename and filename.strip():
            content = read_work_node_result_output(
                record.uuid,
                filename,
                userid=upload_userid,
                workflow_uuid=wf or None,
            )
            resolved_name = filename.strip()
        else:
            # Prefer last workflow-run result when scoped; fall back to legacy validation files.
            content = None
            resolved_name = ""
            if wf:
                content = _latest_work_node_run_result_content(
                    database_path,
                    workflow_uuid=wf,
                    work_uuid=record.uuid,
                    userid=upload_userid,
                )
                if content is not None:
                    resolved_name = "result.out"
            if content is None:
                content = read_work_node_validation_output(
                    record.uuid,
                    userid=upload_userid,
                    validate_date=record.validate_date or record.last_end_date,
                    workflow_uuid=wf or None,
                )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if content is None:
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")
    return {
        "content": content,
        "filename": resolved_name,
        "validate_date": record.validate_date or record.last_end_date or "",
        "workflow_uuid": wf,
    }


@router.get("/work-nodes/{node_uuid}/agent-log")
async def api_get_work_node_agent_log(
    node_uuid: str,
    request: Request,
    limit: int = 200,
) -> dict[str, object]:
    """Return work_node agent interaction / failure log entries (JSONL)."""
    record = _require_visible_work_node(request, node_uuid)
    upload_userid = resolve_work_node_upload_userid(
        request.app.state.database_path, record.owner
    )
    capped = max(1, min(int(limit or 200), 1000))
    entries = read_work_node_agent_log(upload_userid, record.uuid, limit=capped)
    return {
        "items": entries,
        "work_name": record.work_name,
        "last_fail_reason": record.last_fail_reason or "",
    }


@router.post("/work-nodes/{node_uuid}/file", response_model=WorkNodeResponse)
async def api_upload_work_node_file(
    node_uuid: str,
    request: Request,
    file: UploadFile = File(...),
    workflow_uuid: str | None = None,
) -> WorkNodeResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_work_node_by_uuid(database_path, node_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _require_own_work_node(record, auth_user.idx)
    raw_name = (file.filename or "upload.bin").replace("/", "_").replace("\\", "_")
    safe_name = raw_name.strip()[:180] or "upload.bin"
    wf = (workflow_uuid or "").strip() or find_workflow_uuid_for_work_node(
        database_path, record.uuid
    )
    try:
        directory = work_node_upload_dir(
            record.uuid,
            userid=resolve_work_node_upload_userid(database_path, record.owner),
            workflow_uuid=wf or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / safe_name
    payload = await file.read()
    target.write_bytes(payload)
    stored_name = normalize_work_node_filename(safe_name)
    updated = update_work_node(
        database_path,
        record.uuid,
        work_name=record.work_name,
        work_description=record.work_description,
        target_agent=record.target_agent,
        work_script=record.work_script,
        script_type=record.script_type,
        test_result=record.test_result,
        files=stored_name,
        use_previous_work_result=record.use_previous_work_result,
        work_report=record.work_report,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    return WorkNodeResponse.from_record(
        updated, agent_name=_agent_name(database_path, updated.target_agent)
    )


@router.get("/workflows", response_model=list[WorkflowResponse])
async def api_list_workflows(request: Request) -> list[WorkflowResponse]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    pending_by_uuid = map_pending_workflow_approval_jobs(database_path)
    return [
        _workflow_response(
            database_path,
            record,
            user_idx=auth_user.idx,
            pending_job=pending_by_uuid.get((record.uuid or "").strip().lower()),
        )
        for record in list_workflows_visible(database_path, auth_user.idx)
    ]


@router.get("/workflows/{workflow_uuid}", response_model=WorkflowResponse)
async def api_get_workflow(workflow_uuid: str, request: Request) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_workflow_by_uuid(database_path, workflow_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_view_workflow(record, auth_user.idx)
    return _workflow_response(database_path, record, user_idx=auth_user.idx)


@router.post("/workflows", response_model=WorkflowResponse, status_code=201)
async def api_create_workflow(body: WorkflowWriteRequest, request: Request) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    try:
        _validate_expression(database_path, body.workflow, user_idx=auth_user.idx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        record = create_workflow(
            database_path,
            workflow_name=body.workflow_name,
            workflow_description=body.workflow_description,
            workflow=body.workflow,
            uuid=body.uuid,
            owner=auth_user.idx,
            distribute=False,
            cron=bool(body.cron) if body.cron is not None else False,
            cron_expr=body.cron_expr,
            merge_work_result=body.merge_work_result or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workflow_response(database_path, record, user_idx=auth_user.idx)


@router.put("/workflows/{workflow_uuid}", response_model=WorkflowResponse)
async def api_update_workflow(
    workflow_uuid: str,
    body: WorkflowWriteRequest,
    request: Request,
) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_own_workflow(existing, auth_user.idx)

    try:
        _validate_expression(database_path, body.workflow, user_idx=auth_user.idx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        record = update_workflow(
            database_path,
            existing.uuid,
            workflow_name=body.workflow_name.strip(),
            workflow_description=(body.workflow_description or "").strip()[:500],
            workflow=(body.workflow or "").strip(),
            cron=body.cron,
            cron_expr=body.cron_expr,
            merge_work_result=body.merge_work_result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record, user_idx=auth_user.idx)


@router.post("/workflows/{workflow_uuid}/distribute", response_model=WorkflowResponse)
async def api_set_workflow_distribute(
    workflow_uuid: str,
    body: WorkflowDistributeRequest,
    request: Request,
) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_own_workflow(existing, auth_user.idx)
    record = set_workflow_distribute(database_path, existing.uuid, bool(body.distribute))
    if record is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record, user_idx=auth_user.idx)


@router.get("/workflows/{workflow_uuid}/history", response_model=list[WorkflowHistoryResponse])
async def api_list_workflow_history(
    workflow_uuid: str,
    request: Request,
) -> list[WorkflowHistoryResponse]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_view_workflow(existing, auth_user.idx)
    records = list_workflow_history(database_path, existing.uuid)
    name_by_idx: dict[int, str] = {}
    for record in records:
        key = int(record.user_idx or 1)
        if key in name_by_idx:
            continue
        user = get_user_by_idx(database_path, key)
        name_by_idx[key] = (
            (user.username or user.userid).strip() if user is not None else str(key)
        )
    return [
        WorkflowHistoryResponse.from_record(
            record,
            username=name_by_idx.get(int(record.user_idx or 1), str(record.user_idx or 1)),
        )
        for record in records
    ]


@router.get("/workflows/{workflow_uuid}/history/{history_idx}/result")
async def api_get_workflow_history_result(
    workflow_uuid: str,
    history_idx: int,
    request: Request,
) -> dict[str, str | bool | int]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_view_workflow(existing, auth_user.idx)
    history = get_workflow_history_by_idx(database_path, history_idx)
    if history is None or history.uuid != existing.uuid:
        raise HTTPException(status_code=404, detail="이력을 찾을 수 없습니다.")
    userid = resolve_workflow_history_userid(database_path, history.user_idx)
    content = read_workflow_history_result(existing.uuid, history.idx, userid=userid)
    if content is None:
        raise HTTPException(status_code=404, detail="결과 파일이 없습니다.")
    result_path = workflow_history_result_path(existing.uuid, history.idx, userid=userid)
    return {
        "idx": history.idx,
        "content": content,
        "result_file": str(result_path),
        "filename": WORKFLOW_HISTORY_RESULT_FILENAME,
        "success": history.success,
    }


@router.post("/workflows/{workflow_uuid}/clone", response_model=WorkflowResponse, status_code=201)
async def api_clone_workflow(workflow_uuid: str, request: Request) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_view_workflow(existing, auth_user.idx)
    try:
        record = clone_workflow(
            database_path,
            existing.uuid,
            new_owner=auth_user.idx,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workflow_response(database_path, record, user_idx=auth_user.idx)


@router.post("/workflows/{workflow_uuid}/run", response_model=WorkflowRunResponse)
async def api_run_workflow(workflow_uuid: str, request: Request) -> WorkflowRunResponse:
    """Execute a workflow sequentially (work nodes + HITL notifications)."""
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    if not (
        user_owns_workflow(existing, auth_user.idx)
        or bool(getattr(existing, "distribute", False))
    ):
        raise HTTPException(
            status_code=403,
            detail="소유자이거나 배포된 작업 워크플로우만 실행할 수 있습니다.",
        )
    try:
        result: WorkflowRunResult = await run_workflow(
            database_path=database_path,
            agent_runtime=request.app.state.agent_runtime,
            workflow_uuid=existing.uuid,
            requester=auth_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    workflow_payload = None
    if result.workflow is not None:
        workflow_payload = _workflow_response(
            database_path, result.workflow, user_idx=auth_user.idx
        )
    return WorkflowRunResponse(
        status=result.status,
        message=result.message,
        job_idx=result.job_idx,
        steps=[
            WorkflowRunStepResponse(
                kind=step.kind,
                label=step.label,
                status=step.status,
                detail=step.detail,
                work_uuid=step.work_uuid,
            )
            for step in result.steps
        ],
        workflow=workflow_payload,
    )


@router.post(
    "/workflows/{workflow_uuid}/work-nodes/{node_uuid}/stop",
    response_model=WorkflowResponse,
)
async def api_stop_work_node(
    workflow_uuid: str, node_uuid: str, request: Request
) -> WorkflowResponse:
    """Stop a running work node and fail the parent workflow."""
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    if not (
        user_owns_workflow(existing, auth_user.idx)
        or bool(getattr(existing, "distribute", False))
    ):
        raise HTTPException(
            status_code=403,
            detail="소유자이거나 배포된 작업 워크플로우만 중지할 수 있습니다.",
        )
    try:
        finished = stop_running_work_node(
            database_path,
            workflow_uuid=existing.uuid,
            work_uuid=node_uuid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workflow_response(database_path, finished, user_idx=auth_user.idx)


@router.delete("/workflows/{workflow_uuid}")
async def api_delete_workflow(workflow_uuid: str, request: Request) -> dict[str, bool]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_own_workflow(existing, auth_user.idx)

    referenced = sorted(work_uuids_from_expression(existing.workflow))
    userids: set[str] = set()
    owner_user = get_user_by_idx(database_path, int(existing.owner or 0))
    if owner_user is not None:
        key = sanitize_upload_userid(owner_user.userid)
        if key:
            userids.add(key)
    auth_key = sanitize_upload_userid(auth_user.userid)
    if auth_key:
        userids.add(auth_key)

    node_owners: list[tuple[str, str]] = []
    for node_uuid in referenced:
        node = get_work_node_by_uuid(database_path, node_uuid)
        upload_userid = resolve_work_node_upload_userid(
            database_path,
            node.owner if node is not None else auth_user.idx,
        )
        if upload_userid:
            userids.add(upload_userid)
        node_owners.append((node_uuid, upload_userid))

    if not delete_workflow(database_path, existing.uuid):
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")

    # Remove the whole workflow tree first (edit + run results + history snapshots).
    remove_workflow_upload_dirs(existing.uuid, userids=userids)

    for node_uuid, upload_userid in node_owners:
        delete_work_node(database_path, node_uuid)
        # Legacy flat / per-node paths outside the workflow tree.
        remove_work_node_upload_dirs(
            node_uuid,
            userids={upload_userid, *userids},
            workflow_uuid=existing.uuid,
        )

    return {"ok": True}


_TEXT_ATTACHMENT_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".conf",
    ".cfg",
    ".ini",
    ".log",
    ".sh",
    ".py",
    ".crt",
    ".pem",
    ".key",
    ".csr",
}


def _is_text_attachment_name(filename: str) -> bool:
    name = (filename or "").strip().lower()
    if not name:
        return False
    suffix = Path(name).suffix
    return suffix in _TEXT_ATTACHMENT_SUFFIXES or suffix == ""


@router.get("/workflow-jobs/{job_idx}/hitl")
async def api_get_workflow_job_hitl(job_idx: int, request: Request) -> dict[str, object]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    from backend.app.db.jobs import JOB_TYPE_WORKFLOW
    from backend.app.services.workflow_runner import parse_workflow_job_message_id

    job = get_job_by_idx(database_path, job_idx)
    if job is None or int(job.job_type) != JOB_TYPE_WORKFLOW:
        raise HTTPException(status_code=404, detail="워크플로우 승인 작업을 찾을 수 없습니다.")
    parsed = parse_workflow_job_message_id(job.message_id)
    if parsed is None:
        raise HTTPException(status_code=400, detail="워크플로우 승인 작업이 올바르지 않습니다.")
    workflow_uuid = parsed.workflow_uuid
    workflow = get_workflow_by_uuid(database_path, workflow_uuid)
    if workflow is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    _require_view_workflow(workflow, auth_user.idx)
    work_uuid = resolve_hitl_work_uuid_from_job(
        database_path=database_path,
        workflow_expression=workflow.workflow,
        message_id=job.message_id,
    )
    node = get_work_node_by_uuid(database_path, work_uuid) if work_uuid else None
    files: list[str] = []
    if node is not None and (node.upload_path or "").strip():
        directory = resolve_attachment_dir(node.upload_path)
        if directory is not None and directory.is_dir():
            files = sorted(path.name for path in directory.iterdir() if path.is_file())
    return {
        "job_idx": job.idx,
        "workflow_uuid": workflow.uuid,
        "work_uuid": work_uuid or "",
        "work_name": node.work_name if node else "",
        "upload": bool(node.upload) if node else False,
        "upload_path": node.upload_path if node else "",
        "approver_userid": node.approver_userid if node else (job.approver or ""),
        "files": files,
    }


@router.post("/workflow-jobs/{job_idx}/attachments")
async def api_upload_workflow_job_attachments(
    job_idx: int,
    request: Request,
    files: list[UploadFile] = File(...),
) -> dict[str, object]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    from backend.app.db.jobs import JOB_TYPE_WORKFLOW
    from backend.app.services.workflow_runner import parse_workflow_job_message_id

    job = get_job_by_idx(database_path, job_idx)
    if job is None or int(job.job_type) != JOB_TYPE_WORKFLOW:
        raise HTTPException(status_code=404, detail="워크플로우 승인 작업을 찾을 수 없습니다.")
    if (job.approver or "").strip() and (job.approver or "").strip() != auth_user.userid:
        from backend.app.db.roles import is_admin_role

        if not is_admin_role(auth_user.role):
            raise HTTPException(status_code=403, detail="승인자만 파일을 업로드할 수 있습니다.")
    parsed = parse_workflow_job_message_id(job.message_id)
    if parsed is None:
        raise HTTPException(status_code=400, detail="워크플로우 승인 작업이 올바르지 않습니다.")
    workflow_uuid = parsed.workflow_uuid
    workflow = get_workflow_by_uuid(database_path, workflow_uuid)
    if workflow is None:
        raise HTTPException(status_code=404, detail="작업 워크플로우를 찾을 수 없습니다.")
    work_uuid = resolve_hitl_work_uuid_from_job(
        database_path=database_path,
        workflow_expression=workflow.workflow,
        message_id=job.message_id,
    )
    if not work_uuid:
        raise HTTPException(status_code=400, detail="HITL 작업 노드를 찾을 수 없습니다.")
    node = get_work_node_by_uuid(database_path, work_uuid)
    if node is None:
        raise HTTPException(status_code=404, detail="HITL 작업 노드를 찾을 수 없습니다.")
    if not node.upload:
        raise HTTPException(status_code=400, detail="이 승인 단계는 파일 업로드가 필요하지 않습니다.")
    if not files:
        raise HTTPException(status_code=400, detail="업로드할 파일이 없습니다.")

    cursor = parsed
    wnh_idx = int(cursor.work_node_history_idx or 0)
    history = get_work_node_history_by_idx(database_path, wnh_idx) if wnh_idx > 0 else None
    if history is None or history.uuid.lower() != node.uuid.lower():
        raise HTTPException(
            status_code=400,
            detail="승인 단계 업로드 경로를 위한 work_node_history를 찾을 수 없습니다.",
        )
    try:
        directory = work_node_run_upload_dir(
            workflow_uuid,
            node.uuid,
            history.workflow_history_idx,
            history.idx,
            userid=sanitize_upload_userid(auth_user.userid) or auth_user.userid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    directory.mkdir(parents=True, exist_ok=True)
    # Store path relative to UPLOAD_HOME for resolve_attachment_dir compatibility.
    from backend.app.config import resolve_upload_home

    try:
        relative = str(directory.resolve().relative_to(resolve_upload_home().resolve()))
    except ValueError:
        relative = str(directory)
    saved: list[str] = []
    for upload in files:
        raw_name = (upload.filename or "upload.txt").replace("/", "_").replace("\\", "_")
        safe_name = raw_name.strip()[:180] or "upload.txt"
        if not _is_text_attachment_name(safe_name):
            raise HTTPException(
                status_code=400,
                detail=f"텍스트 파일만 업로드할 수 있습니다: {safe_name}",
            )
        payload = await upload.read()
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"UTF-8 텍스트 파일만 업로드할 수 있습니다: {safe_name}",
            ) from exc
        (directory / safe_name).write_bytes(payload)
        saved.append(safe_name)
    updated = set_work_node_upload_path(database_path, node.uuid, relative)
    return {
        "ok": True,
        "upload_path": relative,
        "files": saved,
        "work_uuid": node.uuid,
        "work_name": updated.work_name if updated else node.work_name,
    }
