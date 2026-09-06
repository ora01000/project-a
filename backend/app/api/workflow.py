"""CRUD APIs for work_node and workflow designer (Redis draft working set)."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.app.config import PROJECT_ROOT
from backend.app.db.agentruntime import get_agentruntime_by_idx
from backend.app.db.roles import ROLE_ADMIN, ROLE_INFRAADMIN
from backend.app.db.users import get_user_by_idx, list_users
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
from backend.app.services import workflow_draft_store as draft_store
from backend.app.services.workflow_graph import build_workflow_graph, validate_workflow_expression

router = APIRouter(tags=["workflow"])


class WorkNodeResponse(BaseModel):
    idx: int
    uuid: str = ""
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
    is_draft: bool = False

    @classmethod
    def from_record(
        cls,
        record: WorkNodeRecord,
        *,
        agent_name: str = "",
        is_draft: bool = False,
    ) -> "WorkNodeResponse":
        return cls(
            idx=record.idx,
            uuid=record.uuid,
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
            is_draft=is_draft,
        )


class WorkNodeWriteRequest(BaseModel):
    work_name: str = Field(default="새 작업노드", max_length=100)
    work_description: str = Field(default="", max_length=500)
    target_agent: int = Field(default=0, ge=0)
    work_script: str = ""
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
    is_draft: bool = False
    draft_dirty: bool = False

    @classmethod
    def from_record(
        cls,
        record: WorkflowRecord,
        *,
        graph: dict,
        checkin_username: str = "",
        is_draft: bool = False,
        draft_dirty: bool = False,
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
            is_draft=is_draft,
            draft_dirty=draft_dirty,
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


def _db_work_names(database_path) -> dict[int, str]:
    return {node.idx: node.work_name for node in list_work_nodes(database_path)}


def _user_names(database_path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for user in list_users(database_path, viewer_role=ROLE_ADMIN):
        mapping[user.userid] = user.username or user.userid
    return mapping


def _known_userids(database_path) -> set[str]:
    return set(_user_names(database_path).keys())


def _checkin_username(database_path, checkin_user: int) -> str:
    if int(checkin_user or 0) <= 0:
        return ""
    user = get_user_by_idx(database_path, int(checkin_user))
    if user is None:
        return ""
    return (user.username or user.userid or "").strip()


def _graph_for(
    database_path,
    expression: str,
    *,
    extra_work_names: dict[int, str] | None = None,
) -> dict:
    names = _db_work_names(database_path)
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
    extra_work_idxs: set[int] | None = None,
) -> None:
    text = (expression or "").strip()
    if not text:
        return
    known = set(_db_work_names(database_path).keys())
    if extra_work_idxs:
        known |= extra_work_idxs
    try:
        validate_workflow_expression(
            text,
            known_work_idxs=known,
            known_userids=_known_userids(database_path),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _workflow_response(
    database_path,
    record: WorkflowRecord,
    *,
    is_draft: bool = False,
    draft_dirty: bool = False,
    extra_work_names: dict[int, str] | None = None,
) -> WorkflowResponse:
    return WorkflowResponse.from_record(
        record,
        graph=_graph_for(database_path, record.workflow, extra_work_names=extra_work_names),
        checkin_username=_checkin_username(database_path, record.checkin_user),
        is_draft=is_draft,
        draft_dirty=draft_dirty,
    )


async def _overlay_workflow_for_user(
    database_path,
    record: WorkflowRecord,
    user_idx: int,
) -> WorkflowResponse:
    if record.checkin_user == user_idx and record.uuid:
        payload = await draft_store.get_draft(record.uuid)
        if payload is not None and int(payload.get("meta", {}).get("user_idx") or 0) == user_idx:
            working = draft_store.working_workflow(payload)
            # Keep live checkin lock fields from DB.
            working = WorkflowRecord(
                idx=working.idx,
                uuid=working.uuid or record.uuid,
                checkin_user=record.checkin_user,
                checkin_time=record.checkin_time,
                workflow_name=working.workflow_name,
                workflow_description=working.workflow_description,
                workflow=working.workflow,
                create_date=working.create_date or record.create_date,
                test_result=working.test_result,
                validate_date=working.validate_date,
            )
            nodes = draft_store.working_nodes(payload)
            extra_names = {idx: node.work_name for idx, node in nodes.items()}
            dirty = bool(payload.get("meta", {}).get("dirty"))
            return _workflow_response(
                database_path,
                working,
                is_draft=True,
                draft_dirty=dirty,
                extra_work_names=extra_names,
            )
    return _workflow_response(database_path, record)


async def _find_user_draft_for_node(user_idx: int, node_idx: int) -> dict | None:
    for payload in await draft_store.get_user_drafts(user_idx):
        nodes = draft_store.working_nodes(payload)
        if int(node_idx) in nodes:
            return payload
        # Also allow updating nodes newly created in this session.
        created = draft_store.baseline_created_cleanup_idxs(payload)
        if int(node_idx) in created:
            return payload
    # If user has exactly one active draft, attach node updates there.
    drafts = await draft_store.get_user_drafts(user_idx)
    if len(drafts) == 1:
        return drafts[0]
    return None


async def _active_user_draft(user_idx: int) -> dict | None:
    drafts = await draft_store.get_user_drafts(user_idx)
    if not drafts:
        return None
    if len(drafts) == 1:
        return drafts[0]
    # Prefer dirty draft, else first.
    for payload in drafts:
        if payload.get("meta", {}).get("dirty"):
            return payload
    return drafts[0]


def _snapshot_nodes_for_workflow(database_path, workflow: WorkflowRecord) -> list[WorkNodeRecord]:
    idxs = draft_store.work_idxs_from_expression(workflow.workflow)
    nodes: list[WorkNodeRecord] = []
    for idx in sorted(idxs):
        record = get_work_node_by_idx(database_path, idx)
        if record is not None:
            nodes.append(record)
    return nodes


@router.get("/work-nodes", response_model=list[WorkNodeResponse])
async def api_list_work_nodes(request: Request) -> list[WorkNodeResponse]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    by_idx = {record.idx: record for record in list_work_nodes(database_path)}
    draft_idxs: set[int] = set()
    for payload in await draft_store.get_user_drafts(auth_user.idx):
        for idx, node in draft_store.working_nodes(payload).items():
            by_idx[idx] = node
            draft_idxs.add(idx)
    return [
        WorkNodeResponse.from_record(
            record,
            agent_name=_agent_name(database_path, record.target_agent),
            is_draft=record.idx in draft_idxs,
        )
        for record in sorted(by_idx.values(), key=lambda item: item.idx)
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
    record = create_work_node(
        database_path,
        work_name=body.work_name,
        work_description=body.work_description,
        target_agent=body.target_agent,
        work_script=body.work_script,
        script_type=script_type,
        test_result=body.test_result,
        files=body.files,
    )
    draft = await _active_user_draft(auth_user.idx)
    if draft is not None:
        next_payload = draft_store.set_working_node(draft, record)
        next_payload = draft_store.track_created_node(next_payload, record.idx)
        await draft_store.save_draft(next_payload)
        return WorkNodeResponse.from_record(
            record,
            agent_name=_agent_name(database_path, record.target_agent),
            is_draft=True,
        )
    return WorkNodeResponse.from_record(
        record, agent_name=_agent_name(database_path, record.target_agent)
    )


@router.put("/work-nodes/{idx}", response_model=WorkNodeResponse)
async def api_update_work_node(
    idx: int,
    body: WorkNodeWriteRequest,
    request: Request,
) -> WorkNodeResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_work_node_by_idx(database_path, idx)
    if existing is None:
        # May exist only in draft (should not happen with current create path).
        draft = await _find_user_draft_for_node(auth_user.idx, idx)
        if draft is None:
            raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
        existing = draft_store.working_nodes(draft).get(idx)
        if existing is None:
            raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    _require_agent(database_path, body.target_agent)
    try:
        script_type = normalize_script_type(body.script_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    next_node = WorkNodeRecord(
        idx=existing.idx,
        uuid=existing.uuid,
        work_name=body.work_name.strip() or "새 작업노드",
        work_description=(body.work_description or "").strip()[:500],
        target_agent=int(body.target_agent),
        work_script=body.work_script,
        script_type=script_type,
        test_result=bool(body.test_result),
        files=(body.files or "").strip()[:300],
        create_date=existing.create_date,
        validate_date=existing.validate_date if body.test_result else "",
    )

    draft = await _find_user_draft_for_node(auth_user.idx, idx)
    if draft is not None:
        next_payload = draft_store.set_working_node(draft, next_node)
        await draft_store.save_draft(next_payload)
        return WorkNodeResponse.from_record(
            next_node,
            agent_name=_agent_name(database_path, next_node.target_agent),
            is_draft=True,
        )

    # No active draft: block if any workflow is checked in by someone else referencing this node.
    for workflow in list_workflows(database_path):
        if workflow.checkin_user > 0 and workflow.checkin_user != auth_user.idx:
            if idx in draft_store.work_idxs_from_expression(workflow.workflow):
                raise HTTPException(
                    status_code=409,
                    detail="다른 사용자가 체크인한 워크플로우의 작업노드입니다.",
                )

    record = update_work_node(
        database_path,
        idx,
        work_name=next_node.work_name,
        work_description=next_node.work_description,
        target_agent=next_node.target_agent,
        work_script=next_node.work_script,
        script_type=next_node.script_type,
        test_result=next_node.test_result,
        files=next_node.files,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    return WorkNodeResponse.from_record(
        record, agent_name=_agent_name(database_path, record.target_agent)
    )


@router.delete("/work-nodes/{idx}")
async def api_delete_work_node(idx: int, request: Request) -> dict[str, bool]:
    auth_user = get_request_auth_user(request)
    draft = await _find_user_draft_for_node(auth_user.idx, idx)
    if draft is not None:
        raise HTTPException(
            status_code=409,
            detail="체크인 세션의 작업노드는 체크아웃 전에 삭제할 수 없습니다. 다이어그램에서 제거하세요.",
        )
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
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_work_node_by_idx(database_path, idx)
    draft = await _find_user_draft_for_node(auth_user.idx, idx)
    if record is None and draft is not None:
        record = draft_store.working_nodes(draft).get(idx)
    if record is None:
        raise HTTPException(status_code=404, detail="워크 노드를 찾을 수 없습니다.")
    raw_name = (file.filename or "upload.bin").replace("/", "_").replace("\\", "_")
    safe_name = raw_name.strip()[:180] or "upload.bin"
    if draft is not None:
        directory = PROJECT_ROOT / "data" / "workflow_drafts" / str(
            draft.get("meta", {}).get("workflow_uuid") or "unknown"
        ) / str(idx)
    else:
        directory = PROJECT_ROOT / "data" / "workflow_files" / str(idx)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / safe_name
    payload = await file.read()
    target.write_bytes(payload)
    relative = str(target.relative_to(PROJECT_ROOT))[:300]
    next_node = WorkNodeRecord(
        idx=record.idx,
        uuid=record.uuid,
        work_name=record.work_name,
        work_description=record.work_description,
        target_agent=record.target_agent,
        work_script=record.work_script,
        script_type=record.script_type,
        test_result=record.test_result,
        files=relative,
        create_date=record.create_date,
        validate_date=record.validate_date,
    )
    if draft is not None:
        next_payload = draft_store.set_working_node(draft, next_node)
        await draft_store.save_draft(next_payload)
        return WorkNodeResponse.from_record(
            next_node,
            agent_name=_agent_name(database_path, next_node.target_agent),
            is_draft=True,
        )
    updated = update_work_node(
        database_path,
        idx,
        work_name=next_node.work_name,
        work_description=next_node.work_description,
        target_agent=next_node.target_agent,
        work_script=next_node.work_script,
        script_type=next_node.script_type,
        test_result=next_node.test_result,
        files=relative,
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
    return [
        await _overlay_workflow_for_user(database_path, record, auth_user.idx)
        for record in list_workflows(database_path)
    ]


@router.get("/workflows/{idx}", response_model=WorkflowResponse)
async def api_get_workflow(idx: int, request: Request) -> WorkflowResponse:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    record = get_workflow_by_idx(database_path, idx)
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return await _overlay_workflow_for_user(database_path, record, auth_user.idx)


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

    payload = await draft_store.get_draft(existing.uuid)
    if payload is None or int(payload.get("meta", {}).get("user_idx") or 0) != auth_user.idx:
        raise HTTPException(status_code=409, detail="체크인 드래프트를 찾을 수 없습니다. 다시 체크인하세요.")

    draft_nodes = draft_store.working_nodes(payload)
    try:
        _validate_expression(
            database_path,
            body.workflow,
            extra_work_idxs=set(draft_nodes.keys()),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    current = draft_store.working_workflow(payload)
    next_record = WorkflowRecord(
        idx=existing.idx,
        uuid=existing.uuid,
        checkin_user=existing.checkin_user,
        checkin_time=existing.checkin_time,
        workflow_name=body.workflow_name.strip(),
        workflow_description=(body.workflow_description or "").strip()[:500],
        workflow=(body.workflow or "").strip(),
        create_date=current.create_date or existing.create_date,
        test_result=current.test_result,
        validate_date=current.validate_date,
    )
    next_payload = draft_store.set_working_workflow(payload, next_record)
    await draft_store.save_draft(next_payload)
    return await _overlay_workflow_for_user(database_path, existing, auth_user.idx)


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
        # Ensure draft exists (recover if Redis lost).
        payload = await draft_store.get_draft(existing.uuid)
        if payload is None:
            nodes = _snapshot_nodes_for_workflow(database_path, existing)
            payload = draft_store.build_draft_payload(
                user_idx=auth_user.idx,
                workflow=existing,
                nodes=nodes,
            )
            await draft_store.save_draft(payload)
        return await _overlay_workflow_for_user(database_path, existing, auth_user.idx)

    record = set_workflow_checkin_user(database_path, idx, auth_user.idx)
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    nodes = _snapshot_nodes_for_workflow(database_path, record)
    payload = draft_store.build_draft_payload(
        user_idx=auth_user.idx,
        workflow=record,
        nodes=nodes,
    )
    await draft_store.save_draft(payload)
    return await _overlay_workflow_for_user(database_path, record, auth_user.idx)


async def _commit_draft_to_db(database_path, payload: dict) -> WorkflowRecord:
    working_wf = draft_store.working_workflow(payload)
    working_nodes = draft_store.working_nodes(payload)
    for node in working_nodes.values():
        existing = get_work_node_by_idx(database_path, node.idx)
        if existing is None:
            # Should have been created during session; skip orphan.
            continue
        updated = update_work_node(
            database_path,
            node.idx,
            work_name=node.work_name,
            work_description=node.work_description,
            target_agent=node.target_agent,
            work_script=node.work_script,
            script_type=node.script_type,
            test_result=node.test_result,
            files=node.files,
        )
        if updated is None:
            raise HTTPException(status_code=500, detail=f"작업노드 {node.idx} 커밋에 실패했습니다.")
    record = update_workflow(
        database_path,
        working_wf.idx,
        workflow_name=working_wf.workflow_name,
        workflow_description=working_wf.workflow_description,
        workflow=working_wf.workflow,
    )
    if record is None:
        raise HTTPException(status_code=500, detail="워크플로우 커밋에 실패했습니다.")
    return record


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

    payload = await draft_store.get_draft(existing.uuid)
    if payload is not None:
        working = draft_store.working_workflow(payload)
        draft_nodes = draft_store.working_nodes(payload)
        try:
            _validate_expression(
                database_path,
                working.workflow,
                extra_work_idxs=set(draft_nodes.keys()),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _commit_draft_to_db(database_path, payload)
        await draft_store.delete_draft(existing.uuid, auth_user.idx)

    record = set_workflow_checkin_user(database_path, idx, 0)
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return _workflow_response(database_path, record)


@router.post("/workflows/{idx}/restore", response_model=WorkflowResponse)
async def api_restore_workflow(idx: int, request: Request) -> WorkflowResponse:
    """Discard draft changes, delete session-created nodes, and check out."""
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    if existing.checkin_user <= 0:
        return _workflow_response(database_path, existing)
    if existing.checkin_user != auth_user.idx:
        raise HTTPException(status_code=403, detail="본인이 체크인한 워크플로우만 복원할 수 있습니다.")

    payload = await draft_store.get_draft(existing.uuid)
    created_idxs = draft_store.baseline_created_cleanup_idxs(payload) if payload else []
    for node_idx in created_idxs:
        delete_work_node(database_path, node_idx)
    if payload is not None:
        await draft_store.delete_draft(existing.uuid, auth_user.idx)

    record = set_workflow_checkin_user(database_path, idx, 0)
    if record is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    # DB workflow body never changed during draft saves — committed state remains baseline.
    return _workflow_response(database_path, record)


@router.delete("/workflows/{idx}")
async def api_delete_workflow(idx: int, request: Request) -> dict[str, bool]:
    auth_user = get_request_auth_user(request)
    database_path = request.app.state.database_path
    existing = get_workflow_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    if existing.checkin_user > 0:
        raise HTTPException(status_code=409, detail="체크인된 워크플로우는 삭제할 수 없습니다.")
    if existing.uuid:
        await draft_store.delete_draft(existing.uuid, auth_user.idx)
    if not delete_workflow(database_path, idx):
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다.")
    return {"ok": True}
