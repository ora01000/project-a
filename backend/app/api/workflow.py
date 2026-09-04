"""CRUD APIs for work_node and workflow designer."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.config import PROJECT_ROOT
from backend.app.db.agentruntime import get_agentruntime_by_idx
from backend.app.db.users import get_user_by_idx, list_users
from backend.app.db.roles import ROLE_ADMIN, ROLE_INFRAADMIN
from backend.app.db.workflow import (
    WorkNodeRecord,
    WorkflowRecord,
    create_work_node,
    create_workflow,
    delete_work_node,
    delete_workflow,
    get_work_node_by_idx,
    get_workflow_by_idx,
    list_work_nodes,
    list_workflows,
    normalize_script_type,
    set_workflow_checkin_user,
    update_work_node,
    update_workflow,
)
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.workflow_graph import build_workflow_graph, validate_workflow_expression

router = APIRouter(tags=["workflow"])


class WorkNodeResponse(BaseModel):
    idx: int
    uuid: str = ""
    work_name: str
    work_description: str = ""
    target_agent: int
    target_agent_name: str = ""
    user_prompt: str
    agent_response: str
    script_type: str = ""
    test_result: bool
    files: str
    create_date: str = ""
    validate_date: str = ""

    @classmethod
    def from_record(cls, record: WorkNodeRecord, *, agent_name: str = "") -> "WorkNodeResponse":
        return cls(
            idx=record.idx,
            uuid=record.uuid,
            work_name=record.work_name,
            work_description=record.work_description,
            target_agent=record.target_agent,
            target_agent_name=agent_name,
            user_prompt=record.user_prompt,
            agent_response=record.agent_response,
            script_type=record.script_type,
            test_result=record.test_result,
            files=record.files,
            create_date=record.create_date,
            validate_date=record.validate_date,
        )


class WorkNodeWriteRequest(BaseModel):
    work_name: str = Field(default="새 작업노드", max_length=100)
    work_description: str = Field(default="", max_length=500)
    target_agent: int = Field(default=0, ge=0)
    user_prompt: str = ""
    agent_response: str = ""
    script_type: str = Field(default="", max_length=20)
    test_result: bool = False
    files: str = Field(default="", max_length=300)


class WorkflowApproverResponse(BaseModel):
    userid: str
    username: str
    role: int


class WorkflowGraphNode(BaseModel):
    id: str
    kind: str
    label: str
    work_idx: int | None = None
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
    idx: int
    uuid: str = ""
    checkin_user: int = 0
    checkin_username: str = ""
    checkin_time: str = ""
    workflow_name: str
    workflow_description: str
    workflow: str
    create_date: str = ""
    test_result: bool = False
    validate_date: str = ""
    graph: WorkflowGraph

    @classmethod
    def from_record(
        cls,
        record: WorkflowRecord,
        *,
        graph: dict,
        checkin_username: str = "",
    ) -> "WorkflowResponse":
        return cls(
            idx=record.idx,
            uuid=record.uuid,
            checkin_user=record.checkin_user,
            checkin_username=checkin_username,
            checkin_time=record.checkin_time,
            workflow_name=record.workflow_name,
            workflow_description=record.workflow_description,
            workflow=record.workflow,
            create_date=record.create_date,
            test_result=record.test_result,
            validate_date=record.validate_date,
            graph=WorkflowGraph.model_validate(graph),
        )


class WorkflowWriteRequest(BaseModel):
    workflow_name: str = Field(min_length=1, max_length=100)
    workflow_description: str = Field(default="", max_length=500)
    workflow: str = ""


def _agent_name(database_path, target_agent: int) -> str:
    if int(target_agent) <= 0:
        return ""
    record = get_agentruntime_by_idx(database_path, target_agent)
    return record.agent_name if record is not None else ""


def _require_agent(database_path, target_agent: int) -> None:
    if int(target_agent) <= 0:
        return
    if get_agentruntime_by_idx(database_path, target_agent) is None:
        raise HTTPException(status_code=400, detail="대상 에이전트를 찾을 수 없습니다.")


def _work_names(database_path) -> dict[int, str]:
    return {node.idx: node.work_name for node in list_work_nodes(database_path)}


def _user_names(database_path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for user in list_users(database_path, viewer_role=ROLE_ADMIN):
        mapping[user.userid] = user.username or user.userid
    return mapping


def _known_userids(database_path) -> set[str]:
    return set(_user_names(database_path).keys())


def _validate_expression(database_path, expression: str) -> None:
    text = (expression or "").strip()
    if not text:
        return
    try:
        validate_workflow_expression(
            text,
            known_work_idxs=set(_work_names(database_path).keys()),
            known_userids=_known_userids(database_path),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _graph_for(database_path, expression: str) -> dict:
    try:
        return build_workflow_graph(
            expression,
            work_names=_work_names(database_path),
            user_names=_user_names(database_path),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _checkin_username(database_path, checkin_user: int) -> str:
    if int(checkin_user or 0) <= 0:
        return ""
    user = get_user_by_idx(database_path, int(checkin_user))
    if user is None:
        return ""
    return (user.username or user.userid or "").strip()


def _workflow_response(database_path, record: WorkflowRecord) -> WorkflowResponse:
    return WorkflowResponse.from_record(
        record,
        graph=_graph_for(database_path, record.workflow),
        checkin_username=_checkin_username(database_path, record.checkin_user),
    )


@router.get("/work-nodes", response_model=list[WorkNodeResponse])
async def api_list_work_nodes(request: Request) -> list[WorkNodeResponse]:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    return [
        WorkNodeResponse.from_record(record, agent_name=_agent_name(database_path, record.target_agent))
        for record in list_work_nodes(database_path)
    ]


@router.post("/work-nodes", response_model=WorkNodeResponse, status_code=201)
async def api_create_work_node(body: WorkNodeWriteRequest, request: Request) -> WorkNodeResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    _require_agent(database_path, body.target_agent)
    try:
        script_type = normalize_script_type(body.script_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = create_work_node(
        database_path,
        work_name=body.work_name,
        work_description=body.work_description,
        target_agent=body.target_agent,
        user_prompt=body.user_prompt,
        agent_response=body.agent_response,
        script_type=script_type,
        test_result=body.test_result,
        files=body.files,
    )
    return WorkNodeResponse.from_record(record, agent_name=_agent_name(database_path, record.target_agent))


@router.put("/work-nodes/{idx}", response_model=WorkNodeResponse)
async def api_update_work_node(
    idx: int,
    body: WorkNodeWriteRequest,
    request: Request,
) -> WorkNodeResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    if get_work_node_by_idx(database_path, idx) is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _require_agent(database_path, body.target_agent)
    try:
        script_type = normalize_script_type(body.script_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = update_work_node(
        database_path,
        idx,
        work_name=body.work_name,
        work_description=body.work_description,
        target_agent=body.target_agent,
        user_prompt=body.user_prompt,
        agent_response=body.agent_response,
        script_type=script_type,
        test_result=body.test_result,
        files=body.files,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    return WorkNodeResponse.from_record(record, agent_name=_agent_name(database_path, record.target_agent))


@router.delete("/work-nodes/{idx}")
async def api_delete_work_node(idx: int, request: Request) -> dict[str, bool]:
    get_request_auth_user(request)
    if not delete_work_node(request.app.state.database_path, idx):
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


@router.post("/work-nodes/{idx}/file", response_model=WorkNodeResponse)
async def api_upload_work_node_file(
    idx: int,
    request: Request,
    file: UploadFile = File(...),
) -> WorkNodeResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_work_node_by_idx(database_path, idx)
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    raw_name = (file.filename or "upload.bin").replace("/", "_").replace("\\", "_")
    safe_name = raw_name.strip()[:180] or "upload.bin"
    directory = PROJECT_ROOT / "data" / "workflow_files" / str(idx)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / safe_name
    payload = await file.read()
    target.write_bytes(payload)
    relative = str(target.relative_to(PROJECT_ROOT))[:300]
    updated = update_work_node(
        database_path,
        idx,
        work_name=record.work_name,
        work_description=record.work_description,
        target_agent=record.target_agent,
        user_prompt=record.user_prompt,
        agent_response=record.agent_response,
        script_type=record.script_type,
        test_result=record.test_result,
        files=relative,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    return WorkNodeResponse.from_record(
        updated, agent_name=_agent_name(database_path, updated.target_agent)
    )


@router.get("/workflows", response_model=list[WorkflowResponse])
async def api_list_workflows(request: Request) -> list[WorkflowResponse]:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    return [_workflow_response(database_path, record) for record in list_workflows(database_path)]


@router.get("/workflows/{idx}", response_model=WorkflowResponse)
async def api_get_workflow(idx: int, request: Request) -> WorkflowResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_workflow_by_idx(database_path, idx)
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record)


@router.post("/workflows", response_model=WorkflowResponse, status_code=201)
async def api_create_workflow(body: WorkflowWriteRequest, request: Request) -> WorkflowResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path
    try:
        _validate_expression(database_path, body.workflow)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = create_workflow(
        database_path,
        workflow_name=body.workflow_name,
        workflow_description=body.workflow_description,
        workflow=body.workflow,
    )
    return _workflow_response(database_path, record)


@router.put("/workflows/{idx}", response_model=WorkflowResponse)
async def api_update_workflow(
    idx: int,
    body: WorkflowWriteRequest,
    request: Request,
) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    if existing.checkin_user > 0 and existing.checkin_user != auth_user.idx:
        raise HTTPException(status_code=409, detail="다른 사용자가 체크인한 워크플로우입니다.")
    if existing.checkin_user <= 0:
        raise HTTPException(status_code=409, detail="체크인 후 편집할 수 있습니다.")
    try:
        _validate_expression(database_path, body.workflow)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = update_workflow(
        database_path,
        idx,
        workflow_name=body.workflow_name,
        workflow_description=body.workflow_description,
        workflow=body.workflow,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record)


@router.post("/workflows/{idx}/checkin", response_model=WorkflowResponse)
async def api_checkin_workflow(idx: int, request: Request) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    if existing.checkin_user > 0 and existing.checkin_user != auth_user.idx:
        raise HTTPException(
            status_code=409,
            detail="이미 다른 사용자가 체크인한 워크플로우입니다.",
        )
    if existing.checkin_user == auth_user.idx and (existing.checkin_time or "").strip():
        return _workflow_response(database_path, existing)
    record = set_workflow_checkin_user(database_path, idx, auth_user.idx)
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record)


@router.post("/workflows/{idx}/checkout", response_model=WorkflowResponse)
async def api_checkout_workflow(idx: int, request: Request) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    if existing.checkin_user <= 0:
        return _workflow_response(database_path, existing)
    if existing.checkin_user != auth_user.idx:
        raise HTTPException(status_code=403, detail="본인이 체크인한 워크플로우만 체크아웃할 수 있습니다.")
    record = set_workflow_checkin_user(database_path, idx, 0)
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record)


@router.delete("/workflows/{idx}")
async def api_delete_workflow(idx: int, request: Request) -> dict[str, bool]:
    get_request_auth_user(request)
    if not delete_workflow(request.app.state.database_path, idx):
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return {"ok": True}
