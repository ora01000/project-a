"""Redis working-set drafts for workflow check-in sessions."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.db.workflow import WorkNodeRecord, WorkflowRecord
from backend.app.services.redis_client import get_redis
from backend.app.services.workflow_graph import parse_workflow_tokens

logger = logging.getLogger(__name__)

DRAFT_TTL_SECONDS = 60 * 60 * 24  # 24h
DRAFT_KEY_PREFIX = "workflow:draft:"
DRAFT_USER_INDEX_PREFIX = "workflow:draft:user:"


def draft_key(workflow_uuid: str) -> str:
    return f"{DRAFT_KEY_PREFIX}{workflow_uuid.strip()}"


def user_index_key(user_idx: int) -> str:
    return f"{DRAFT_USER_INDEX_PREFIX}{int(user_idx)}"


def work_idxs_from_expression(expression: str) -> set[int]:
    idxs: set[int] = set()
    try:
        tokens = parse_workflow_tokens(expression)
    except ValueError:
        return idxs
    for token in tokens:
        if token.work_idx is not None:
            idxs.add(int(token.work_idx))
        if token.fail_work_idx is not None:
            idxs.add(int(token.fail_work_idx))
    return idxs


def workflow_to_dict(record: WorkflowRecord) -> dict[str, Any]:
    return {
        "idx": record.idx,
        "uuid": record.uuid,
        "checkin_user": record.checkin_user,
        "checkin_time": record.checkin_time,
        "workflow_name": record.workflow_name,
        "workflow_description": record.workflow_description,
        "workflow": record.workflow,
        "create_date": record.create_date,
        "test_result": record.test_result,
        "validate_date": record.validate_date,
    }


def work_node_to_dict(record: WorkNodeRecord) -> dict[str, Any]:
    return {
        "idx": record.idx,
        "uuid": record.uuid,
        "work_name": record.work_name,
        "work_description": record.work_description,
        "target_agent": record.target_agent,
        "user_prompt": record.user_prompt,
        "agent_response": record.agent_response,
        "script_type": record.script_type,
        "test_result": record.test_result,
        "files": record.files,
        "create_date": record.create_date,
        "validate_date": record.validate_date,
    }


def work_node_from_dict(data: dict[str, Any]) -> WorkNodeRecord:
    return WorkNodeRecord(
        idx=int(data.get("idx") or 0),
        uuid=str(data.get("uuid") or ""),
        work_name=str(data.get("work_name") or ""),
        work_description=str(data.get("work_description") or ""),
        target_agent=int(data.get("target_agent") or 0),
        user_prompt=str(data.get("user_prompt") or ""),
        agent_response=str(data.get("agent_response") or ""),
        script_type=str(data.get("script_type") or "").strip().lower(),
        test_result=bool(data.get("test_result")),
        files=str(data.get("files") or ""),
        create_date=str(data.get("create_date") or ""),
        validate_date=str(data.get("validate_date") or ""),
    )


def workflow_from_dict(data: dict[str, Any]) -> WorkflowRecord:
    return WorkflowRecord(
        idx=int(data.get("idx") or 0),
        uuid=str(data.get("uuid") or ""),
        checkin_user=int(data.get("checkin_user") or 0),
        checkin_time=str(data.get("checkin_time") or ""),
        workflow_name=str(data.get("workflow_name") or ""),
        workflow_description=str(data.get("workflow_description") or ""),
        workflow=str(data.get("workflow") or ""),
        create_date=str(data.get("create_date") or ""),
        test_result=bool(data.get("test_result")),
        validate_date=str(data.get("validate_date") or ""),
    )


def build_draft_payload(
    *,
    user_idx: int,
    workflow: WorkflowRecord,
    nodes: list[WorkNodeRecord],
) -> dict[str, Any]:
    node_map = {str(node.idx): work_node_to_dict(node) for node in nodes}
    workflow_dict = workflow_to_dict(workflow)
    return {
        "meta": {
            "workflow_idx": workflow.idx,
            "workflow_uuid": workflow.uuid,
            "user_idx": int(user_idx),
            "created_node_idxs": [],
            "dirty": False,
        },
        "baseline": {
            "workflow": workflow_dict,
            "nodes": dict(node_map),
        },
        "working": {
            "workflow": dict(workflow_dict),
            "nodes": dict(node_map),
        },
    }


async def save_draft(payload: dict[str, Any], *, ttl: int = DRAFT_TTL_SECONDS) -> None:
    redis = get_redis()
    uuid = str(payload.get("meta", {}).get("workflow_uuid") or "").strip()
    user_idx = int(payload.get("meta", {}).get("user_idx") or 0)
    if not uuid or user_idx <= 0:
        raise ValueError("draft meta.workflow_uuid / user_idx 가 필요합니다.")
    key = draft_key(uuid)
    await redis.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl)
    await redis.sadd(user_index_key(user_idx), uuid)
    await redis.expire(user_index_key(user_idx), ttl)


async def get_draft(workflow_uuid: str) -> dict[str, Any] | None:
    redis = get_redis()
    raw = await redis.get(draft_key(workflow_uuid))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid workflow draft JSON for %s", workflow_uuid)
        return None
    if not isinstance(data, dict):
        return None
    return data


async def delete_draft(workflow_uuid: str, user_idx: int | None = None) -> None:
    redis = get_redis()
    uuid = workflow_uuid.strip()
    payload = await get_draft(uuid)
    await redis.delete(draft_key(uuid))
    owner = user_idx
    if owner is None and payload is not None:
        owner = int(payload.get("meta", {}).get("user_idx") or 0)
    if owner and int(owner) > 0:
        await redis.srem(user_index_key(int(owner)), uuid)


async def list_user_draft_uuids(user_idx: int) -> list[str]:
    redis = get_redis()
    members = await redis.smembers(user_index_key(int(user_idx)))
    return sorted(str(item) for item in (members or set()) if str(item).strip())


async def get_user_drafts(user_idx: int) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for uuid in await list_user_draft_uuids(user_idx):
        payload = await get_draft(uuid)
        if payload is not None:
            drafts.append(payload)
    return drafts


async def touch_draft_ttl(workflow_uuid: str, user_idx: int, *, ttl: int = DRAFT_TTL_SECONDS) -> None:
    redis = get_redis()
    await redis.expire(draft_key(workflow_uuid), ttl)
    await redis.expire(user_index_key(int(user_idx)), ttl)


def working_workflow(payload: dict[str, Any]) -> WorkflowRecord:
    return workflow_from_dict(payload["working"]["workflow"])


def working_nodes(payload: dict[str, Any]) -> dict[int, WorkNodeRecord]:
    nodes = payload.get("working", {}).get("nodes") or {}
    result: dict[int, WorkNodeRecord] = {}
    for key, value in nodes.items():
        if not isinstance(value, dict):
            continue
        node = work_node_from_dict(value)
        result[node.idx] = node
    return result


def baseline_created_cleanup_idxs(payload: dict[str, Any]) -> list[int]:
    meta = payload.get("meta") or {}
    raw = meta.get("created_node_idxs") or []
    return [int(item) for item in raw if int(item) > 0]


def mark_dirty(payload: dict[str, Any]) -> dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    meta["dirty"] = True
    next_payload = dict(payload)
    next_payload["meta"] = meta
    return next_payload


def set_working_workflow(payload: dict[str, Any], workflow: WorkflowRecord) -> dict[str, Any]:
    next_payload = mark_dirty(payload)
    working = dict(next_payload.get("working") or {})
    # Preserve checkin fields from DB-facing record when present.
    working["workflow"] = workflow_to_dict(workflow)
    next_payload["working"] = working
    return next_payload


def set_working_node(payload: dict[str, Any], node: WorkNodeRecord) -> dict[str, Any]:
    next_payload = mark_dirty(payload)
    working = dict(next_payload.get("working") or {})
    nodes = dict(working.get("nodes") or {})
    nodes[str(node.idx)] = work_node_to_dict(node)
    working["nodes"] = nodes
    next_payload["working"] = working
    return next_payload


def track_created_node(payload: dict[str, Any], node_idx: int) -> dict[str, Any]:
    next_payload = mark_dirty(payload)
    meta = dict(next_payload.get("meta") or {})
    created = [int(item) for item in (meta.get("created_node_idxs") or [])]
    if int(node_idx) not in created:
        created.append(int(node_idx))
    meta["created_node_idxs"] = created
    next_payload["meta"] = meta
    return next_payload


def restore_working_from_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline") or {}
    next_payload = dict(payload)
    next_payload["working"] = {
        "workflow": dict(baseline.get("workflow") or {}),
        "nodes": dict(baseline.get("nodes") or {}),
    }
    meta = dict(next_payload.get("meta") or {})
    meta["dirty"] = False
    # Keep created_node_idxs for cleanup on discard/restore-checkout.
    next_payload["meta"] = meta
    return next_payload
