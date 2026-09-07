"""CRUD APIs for work_node and workflow designer (owner / distribute model)."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.config import (
    normalize_work_node_filename,
    read_work_node_validation_output,
    work_node_upload_dir,
    write_work_node_validation_output,
)
from backend.app.db.agentruntime import get_agentruntime_by_idx
from backend.app.db.job_datetime import now_job_datetime
from backend.app.db.jobs import (
    JobRecord,
    find_pending_workflow_approval_job,
    map_pending_workflow_approval_jobs,
)
from backend.app.db.roles import ROLE_ADMIN, ROLE_INFRAADMIN
from backend.app.db.users import get_user_by_idx, list_users
from backend.app.db.workflow import (
    WorkNodeRecord,
    WorkflowRecord,
    clone_workflow,
    create_work_node,
    create_workflow,
    delete_work_node,
    delete_workflow,
    get_work_node_by_uuid,
    get_workflow_by_uuid,
    list_work_nodes_visible,
    list_workflows_visible,
    normalize_script_type,
    set_workflow_distribute,
    update_work_node,
    update_workflow,
    user_can_view_workflow,
    user_owns_workflow,
)
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.workflow_graph import build_workflow_graph, validate_workflow_expression
from backend.app.services.workflow_runner import (
    WorkflowRunResult,
    resolve_awaiting_hitl_from_job,
    run_workflow,
)

router = APIRouter(tags=["workflow"])


class WorkNodeResponse(BaseModel):
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
    run_count: int = 0
    sucess_count: int = 0
    fail_count: int = 0
    last_success: bool = False
    awaiting_approval: bool = False
    awaiting_hitl_node_id: str = ""
    awaiting_hitl_userid: str = ""
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
    ) -> "WorkflowResponse":
        return cls(
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
            run_count=record.run_count,
            sucess_count=record.sucess_count,
            fail_count=record.fail_count,
            last_success=record.last_success,
            awaiting_approval=awaiting_approval,
            awaiting_hitl_node_id=awaiting_hitl_node_id,
            awaiting_hitl_userid=awaiting_hitl_userid,
            graph=WorkflowGraph.model_validate(graph),
        )


class WorkflowWriteRequest(BaseModel):
    uuid: str | None = Field(default=None, max_length=36)
    workflow_name: str = Field(min_length=1, max_length=100)
    workflow_description: str = Field(default="", max_length=500)
    workflow: str = ""


class WorkflowDistributeRequest(BaseModel):
    distribute: bool


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


def _write_validation_output_if_needed(record: WorkNodeRecord, message: str | None) -> None:
    if not record.test_result:
        return
    text = (message or "").strip()
    if not text:
        return
    try:
        write_work_node_validation_output(
            record.uuid,
            validate_date=record.validate_date or now_job_datetime(),
            message=text,
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
    try:
        return build_workflow_graph(
            expression,
            work_names=names,
            user_names=_user_names(database_path),
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
        validate_workflow_expression(
            text,
            known_work_uuids=known,
            known_userids=_known_userids(database_path),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _awaiting_hitl_fields(
    record: WorkflowRecord,
    pending_job: JobRecord | None,
) -> tuple[bool, str, str]:
    if pending_job is None:
        return False, "", ""
    resolved = resolve_awaiting_hitl_from_job(
        workflow_expression=record.workflow,
        message_id=pending_job.message_id,
    )
    if resolved is None:
        return True, "", ""
    node_id, userid = resolved
    return True, node_id, userid


def _require_view_workflow(record: WorkflowRecord, user_idx: int) -> None:
    if not user_can_view_workflow(record, user_idx):
        raise HTTPException(status_code=403, detail="이 워크플로우를 조회할 권한이 없습니다.")


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
        record, job
    )
    return WorkflowResponse.from_record(
        record,
        graph=_graph_for(database_path, record.workflow, user_idx=user_idx),
        owner_username=_owner_username(database_path, int(getattr(record, "owner", 0) or 0)),
        can_edit=user_owns_workflow(record, user_idx),
        awaiting_approval=awaiting_approval,
        awaiting_hitl_node_id=awaiting_hitl_node_id,
        awaiting_hitl_userid=awaiting_hitl_userid,
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
            uuid=body.uuid,
            owner=auth_user.idx,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _write_validation_output_if_needed(record, body.validation_message)
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
    )
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _write_validation_output_if_needed(record, body.validation_message)
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
    if not delete_work_node(database_path, node_uuid):
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
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


@router.get("/work-nodes/{node_uuid}/validation-result")
async def api_get_work_node_validation_result(
    node_uuid: str,
    request: Request,
) -> dict[str, str]:
    """Return saved validation output text located by work_node.validate_date."""
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_work_node_by_uuid(database_path, node_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    visible = {node.uuid for node in list_work_nodes_visible(database_path, auth_user.idx)}
    if record.uuid not in visible:
        raise HTTPException(status_code=403, detail="이 작업노드를 조회할 권한이 없습니다.")
    if not record.test_result or not (record.validate_date or "").strip():
        raise HTTPException(status_code=404, detail="저장된 검증 결과가 없습니다.")
    try:
        content = read_work_node_validation_output(
            record.uuid,
            validate_date=record.validate_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if content is None:
        raise HTTPException(status_code=404, detail="검증 결과 파일을 찾을 수 없습니다.")
    return {"content": content, "validate_date": record.validate_date}


@router.post("/work-nodes/{node_uuid}/file", response_model=WorkNodeResponse)
async def api_upload_work_node_file(
    node_uuid: str,
    request: Request,
    file: UploadFile = File(...),
) -> WorkNodeResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_work_node_by_uuid(database_path, node_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _require_own_work_node(record, auth_user.idx)
    raw_name = (file.filename or "upload.bin").replace("/", "_").replace("\\", "_")
    safe_name = raw_name.strip()[:180] or "upload.bin"
    try:
        directory = work_node_upload_dir(record.uuid)
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
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
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
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    _require_own_workflow(existing, auth_user.idx)

    try:
        _validate_expression(database_path, body.workflow, user_idx=auth_user.idx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = update_workflow(
        database_path,
        existing.uuid,
        workflow_name=body.workflow_name.strip(),
        workflow_description=(body.workflow_description or "").strip()[:500],
        workflow=(body.workflow or "").strip(),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
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
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    _require_own_workflow(existing, auth_user.idx)
    record = set_workflow_distribute(database_path, existing.uuid, bool(body.distribute))
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record, user_idx=auth_user.idx)


@router.post("/workflows/{workflow_uuid}/clone", response_model=WorkflowResponse, status_code=201)
async def api_clone_workflow(workflow_uuid: str, request: Request) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
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
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    if not (
        user_owns_workflow(existing, auth_user.idx)
        or bool(getattr(existing, "distribute", False))
    ):
        raise HTTPException(
            status_code=403,
            detail="소유자이거나 배포된 워크플로우만 실행할 수 있습니다.",
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


@router.delete("/workflows/{workflow_uuid}")
async def api_delete_workflow(workflow_uuid: str, request: Request) -> dict[str, bool]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    _require_own_workflow(existing, auth_user.idx)
    if not delete_workflow(database_path, existing.uuid):
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return {"ok": True}
