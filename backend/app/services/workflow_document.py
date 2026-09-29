"""Canonical workflow document (JSON) with legacy string expression compatibility.

DB ``workflow.workflow`` stores design-time JSON::

    {
      "version": 1,
      "nodes": ["uuid-1", "uuid-2"],
      "edges": [
        {"from": "S", "to": "uuid-1", "kind": "success"},
        {"from": "uuid-1", "to": "uuid-2", "kind": "success"},
        {"from": "uuid-1", "to": "uuid-fail", "kind": "fail"},
        {"from": "uuid-2", "to": "E", "kind": "success"}
      ]
    }

Legacy ``S->{uuid}->H:userid->E`` strings are still accepted by
``parse_workflow_document`` / ``normalize_workflow_document``.
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.services.workflow_graph import (
    FlowToken,
    is_uuid_token,
    parse_workflow_tokens,
    validate_workflow_expression,
)

WORKFLOW_DOC_VERSION = 1


def is_workflow_json_text(raw: str | None) -> bool:
    text = (raw or "").strip()
    return text.startswith("{") and text.endswith("}")


def parse_workflow_json(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        data = raw
    else:
        text = (raw or "").strip()
        if not text:
            raise ValueError("작업 워크플로우 JSON이 비어 있습니다.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("작업 워크플로우 JSON을 파싱하지 못했습니다.") from exc
    if not isinstance(data, dict):
        raise ValueError("작업 워크플로우 JSON 루트는 object 여야 합니다.")
    version = int(data.get("version") or WORKFLOW_DOC_VERSION)
    nodes_raw = data.get("nodes")
    edges_raw = data.get("edges")
    if not isinstance(nodes_raw, list):
        raise ValueError("workflow.nodes 는 배열이어야 합니다.")
    if not isinstance(edges_raw, list):
        raise ValueError("workflow.edges 는 배열이어야 합니다.")
    nodes: list[str] = []
    for item in nodes_raw:
        key = str(item or "").strip()
        if not key:
            continue
        if not is_uuid_token(key) and key.upper() not in {"S", "E"}:
            # allow bare uuid only in nodes list (S/E live in edges)
            if not is_uuid_token(key):
                raise ValueError(f"올바르지 않은 workflow node: {key}")
        nodes.append(key.lower() if is_uuid_token(key) else key)
    edges: list[dict[str, str]] = []
    for edge in edges_raw:
        if not isinstance(edge, dict):
            raise ValueError("workflow.edges 항목은 object 여야 합니다.")
        source = str(edge.get("from") or edge.get("source") or "").strip()
        target = str(edge.get("to") or edge.get("target") or "").strip()
        kind = str(edge.get("kind") or "success").strip().lower() or "success"
        if kind not in {"success", "fail"}:
            raise ValueError(f"올바르지 않은 edge kind: {kind}")
        if not source or not target:
            raise ValueError("edge 에 from/to 가 필요합니다.")
        if is_uuid_token(source):
            source = source.lower()
        if is_uuid_token(target):
            target = target.lower()
        edges.append({"from": source, "to": target, "kind": kind})
    return {"version": version, "nodes": nodes, "edges": edges}


def dumps_workflow_json(doc: dict[str, Any]) -> str:
    normalized = parse_workflow_json(doc)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def tokens_to_workflow_json(tokens: list[FlowToken]) -> dict[str, Any]:
    """Convert a linear token list (legacy semantics) into the JSON document."""
    if not tokens:
        return {
            "version": WORKFLOW_DOC_VERSION,
            "nodes": [],
            "edges": [{"from": "S", "to": "E", "kind": "success"}],
        }
    nodes: list[str] = []
    edges: list[dict[str, str]] = []
    main_refs: list[str] = []
    for token in tokens:
        if token.kind == "start":
            main_refs.append("S")
        elif token.kind == "end":
            main_refs.append("E")
        elif token.kind == "hitl":
            # Legacy HITL without uuid cannot enter nodes; caller should migrate first.
            ref = (token.work_uuid or "").strip().lower()
            if not ref:
                raise ValueError("HITL 토큰에 work_uuid 가 필요합니다. 마이그레이션을 먼저 수행하세요.")
            if ref not in nodes:
                nodes.append(ref)
            main_refs.append(ref)
        elif token.kind == "work":
            ref = (token.work_uuid or "").strip().lower()
            if not ref:
                raise ValueError("work 토큰에 uuid 가 없습니다.")
            if ref not in nodes:
                nodes.append(ref)
            main_refs.append(ref)
            if token.fail_end:
                edges.append({"from": ref, "to": "E", "kind": "fail"})
            elif token.fail_work_uuid:
                fail = token.fail_work_uuid.strip().lower()
                if fail not in nodes:
                    nodes.append(fail)
                edges.append({"from": ref, "to": fail, "kind": "fail"})
        else:
            raise ValueError(f"알 수 없는 토큰 kind: {token.kind}")

    for index in range(len(main_refs) - 1):
        edges.append(
            {"from": main_refs[index], "to": main_refs[index + 1], "kind": "success"}
        )
    return {"version": WORKFLOW_DOC_VERSION, "nodes": nodes, "edges": edges}


def workflow_json_to_tokens(doc: dict[str, Any] | str) -> list[FlowToken]:
    """Walk the success path from S to E and rebuild FlowToken list."""
    data = parse_workflow_json(doc)
    success_next: dict[str, str] = {}
    fail_next: dict[str, str] = {}
    for edge in data["edges"]:
        if edge["kind"] == "success":
            success_next[edge["from"]] = edge["to"]
        elif edge["kind"] == "fail":
            fail_next[edge["from"]] = edge["to"]

    if "S" not in success_next:
        raise ValueError("workflow 는 S 에서 시작하는 success edge 가 필요합니다.")

    tokens: list[FlowToken] = [FlowToken(kind="start", raw="S")]
    current = success_next["S"]
    visited: set[str] = set()
    while current.upper() != "E":
        if current in visited:
            raise ValueError("workflow success 경로에 순환이 있습니다.")
        visited.add(current)
        if not is_uuid_token(current):
            raise ValueError(f"알 수 없는 workflow 노드: {current}")
        fail_target = fail_next.get(current)
        fail_end = False
        fail_work_uuid = None
        if fail_target:
            if fail_target.upper() == "E":
                fail_end = True
            elif is_uuid_token(fail_target):
                fail_work_uuid = fail_target.lower()
            else:
                raise ValueError(f"올바르지 않은 fail 대상: {fail_target}")
        raw = current
        if fail_end:
            raw = f"{current}:E"
        elif fail_work_uuid:
            raw = f"{current}:{fail_work_uuid}"
        tokens.append(
            FlowToken(
                kind="work",
                raw=raw,
                work_uuid=current.lower(),
                fail_work_uuid=fail_work_uuid,
                fail_end=fail_end,
            )
        )
        nxt = success_next.get(current)
        if not nxt:
            raise ValueError(f"노드 {current} 에서 이어지는 success edge 가 없습니다.")
        current = nxt
    tokens.append(FlowToken(kind="end", raw="E"))
    return tokens


def parse_workflow_document(raw: str | None) -> list[FlowToken]:
    """Parse JSON document or legacy string expression into FlowTokens."""
    text = (raw or "").strip()
    if not text:
        return []
    if is_workflow_json_text(text):
        return workflow_json_to_tokens(text)
    return parse_workflow_tokens(text)


def validate_workflow_document(
    raw: str | None,
    *,
    known_work_uuids: set[str] | None = None,
    known_userids: set[str] | None = None,
) -> list[FlowToken]:
    text = (raw or "").strip()
    if not text:
        return []
    if is_workflow_json_text(text):
        tokens = workflow_json_to_tokens(text)
        if not tokens or tokens[0].kind != "start" or tokens[-1].kind != "end":
            raise ValueError("작업 워크플로우는 S 로 시작해 E 로 끝나야 합니다.")
        for token in tokens:
            if token.kind == "work" and token.work_uuid and known_work_uuids is not None:
                if token.work_uuid not in known_work_uuids:
                    raise ValueError(f"존재하지 않는 work_node uuid: {token.work_uuid}")
                if (
                    token.fail_work_uuid is not None
                    and token.fail_work_uuid not in known_work_uuids
                ):
                    raise ValueError(
                        f"존재하지 않는 실패 work_node uuid: {token.fail_work_uuid}"
                    )
        return tokens
    return validate_workflow_expression(
        text,
        known_work_uuids=known_work_uuids,
        known_userids=known_userids,
    )


def normalize_workflow_document(raw: str | None) -> str:
    """Return canonical JSON text for persistence (legacy string → JSON)."""
    text = (raw or "").strip()
    if not text:
        return dumps_workflow_json(
            {
                "version": WORKFLOW_DOC_VERSION,
                "nodes": [],
                "edges": [{"from": "S", "to": "E", "kind": "success"}],
            }
        )
    if is_workflow_json_text(text):
        return dumps_workflow_json(parse_workflow_json(text))
    tokens = parse_workflow_tokens(text)
    # Legacy HITL tokens without uuid cannot convert — keep string until migrated.
    for token in tokens:
        if token.kind == "hitl" and not (token.work_uuid or "").strip():
            return text
    return dumps_workflow_json(tokens_to_workflow_json(tokens))


def work_uuids_from_document(raw: str | None) -> set[str]:
    tokens = parse_workflow_document(raw)
    found: set[str] = set()
    for token in tokens:
        if token.work_uuid:
            found.add(token.work_uuid.lower())
        if token.fail_work_uuid:
            found.add(token.fail_work_uuid.lower())
    if is_workflow_json_text(raw or ""):
        try:
            doc = parse_workflow_json(raw or "")
            for node in doc["nodes"]:
                if is_uuid_token(node):
                    found.add(node.lower())
            for edge in doc["edges"]:
                for key in ("from", "to"):
                    value = edge[key]
                    if is_uuid_token(value):
                        found.add(value.lower())
        except ValueError:
            pass
    return found


def rewrite_document_uuid_map(raw: str | None, uuid_map: dict[str, str]) -> str:
    """Rewrite uuid references in JSON or legacy expression."""
    text = (raw or "").strip()
    if not text:
        return text
    mapping = {
        str(old).strip().lower(): str(new).strip().lower()
        for old, new in uuid_map.items()
        if str(old).strip() and str(new).strip()
    }
    if not mapping:
        return text
    if is_workflow_json_text(text):
        doc = parse_workflow_json(text)

        def remap(value: str) -> str:
            if is_uuid_token(value):
                return mapping.get(value.lower(), value.lower())
            return value

        doc["nodes"] = [remap(node) for node in doc["nodes"]]
        doc["edges"] = [
            {"from": remap(edge["from"]), "to": remap(edge["to"]), "kind": edge["kind"]}
            for edge in doc["edges"]
        ]
        return dumps_workflow_json(doc)
    rewritten: list[str] = []
    for part in text.split("->"):
        token = part.strip()
        upper = token.upper()
        if upper in {"S", "E"} or upper.startswith("H:"):
            rewritten.append(token)
            continue
        if ":" in token:
            left, right = token.split(":", 1)
            left = left.strip()
            right = right.strip()
            fail = right if right.upper() == "E" else mapping.get(right, right)
            rewritten.append(f"{mapping.get(left, left)}:{fail}")
            continue
        rewritten.append(mapping.get(token, token))
    return "->".join(rewritten)
