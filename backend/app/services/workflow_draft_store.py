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


def work_uuids_from_expression(expression: str) -> set[str]:
    uuids: set[str] = set()
    try:
        tokens = parse_workflow_tokens(expression)
    except ValueError:
        return uuids
    for token in tokens:
        if token.work_uuid:
            uuids.add(str(token.work_uuid))
        if token.fail_work_uuid:
            uuids.add(str(token.fail_work_uuid))
    return uuids


def workflow_to_dict(record: WorkflowRecord) -> dict[str, Any]:
    return {
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
        "uuid": record.uuid,
        "work_name": record.work_name,
        "work_description": record.work_description,
        "target_agent": record.target_agent,
        "work_script": record.work_script,
        "script_type": record.script_type,
        "test_result": record.test_result,
        "files": record.files,
        "create_date": record.create_date,
        "validate_date": record.validate_date,
    }


def work_node_from_dict(data: dict[str, Any]) -> WorkNodeRecord:
    work_script = data.get("work_script")
    if work_script is None:
        work_script = data.get("agent_response") or ""
    return WorkNodeRecord(
        uuid=str(data.get("uuid") or ""),
        work_name=str(data.get("work_name") or ""),
        work_description=str(data.get("work_description") or ""),
        target_agent=int(data.get("target_agent") or 0),
        work_script=str(work_script or ""),
        script_type=str(data.get("script_type") or "").strip().lower(),
        test_result=bool(data.get("test_result")),
        files=str(data.get("files") or ""),
        create_date=str(data.get("create_date") or ""),
        validate_date=str(data.get("validate_date") or ""),
    )


def workflow_from_dict(data: dict[str, Any]) -> WorkflowRecord:
    return WorkflowRecord(
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
    node_map = {node.uuid: work_node_to_dict(node) for node in nodes if node.uuid}
    workflow_dict = workflow_to_dict(workflow)
    return {
        "meta": {
            "workflow_uuid": workflow.uuid,
            "user_idx": int(user_idx),
            "created_node_uuids": [],
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


def working_nodes(payload: dict[str, Any]) -> dict[str, WorkNodeRecord]:
    nodes = payload.get("working", {}).get("nodes") or {}
    result: dict[str, WorkNodeRecord] = {}
    for key, value in nodes.items():
        if not isinstance(value, dict):
            continue
        node = work_node_from_dict(value)
        result[node.uuid or str(key)] = node
    return result


def baseline_created_cleanup_uuids(payload: dict[str, Any]) -> list[str]:
    meta = payload.get("meta") or {}
    raw = meta.get("created_node_uuids") or []
    return [str(item).strip() for item in raw if str(item).strip()]


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
    nodes[node.uuid] = work_node_to_dict(node)
    working["nodes"] = nodes
    next_payload["working"] = working
    return next_payload


def track_created_node(payload: dict[str, Any], node_uuid: str) -> dict[str, Any]:
    next_payload = mark_dirty(payload)
    meta = dict(next_payload.get("meta") or {})
    created = [str(item) for item in (meta.get("created_node_uuids") or [])]
    key = str(node_uuid).strip()
    if key and key not in created:
        created.append(key)
    meta["created_node_uuids"] = created
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
    # Keep created_node_uuids for cleanup on discard/restore-checkout.
    next_payload["meta"] = meta
    return next_payload
