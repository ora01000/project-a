"""Parse workflow expression text into a drawable graph.

Expression tokens are joined by ``->``. Work nodes are referenced by their
``work_node.uuid``. Examples:
  S->0f1c…->2a9d…:7b31…->H:isyun->4e02…->E
  S              start
  E              end
  0f1c…          work_node 0f1c… (fail → E)
  2a9d…:7b31…    work_node 2a9d…, fail → work_node 7b31…
  2a9d…:E        work_node 2a9d…, fail → end
  H:isyun        HITL approver userid

UUIDs contain no ``:``, so ``split(":", 1)`` still separates a work node from
its failure target.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

WORK_W = 50
WORK_H = 50
HITL_W = 50
HITL_H = 20
MAIL_R = 18
ROUND_R = 22
H_GAP = 110
MAIN_Y = 70
FAIL_Y = 180
MAIL_GAP = 28
ORIGIN_X = 50

UUID_TOKEN_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_uuid_token(value: str) -> bool:
    return bool(UUID_TOKEN_PATTERN.match((value or "").strip()))


@dataclass(frozen=True)
class FlowToken:
    kind: str  # start | end | work | hitl
    raw: str
    work_uuid: str | None = None
    fail_work_uuid: str | None = None
    fail_end: bool = False
    userid: str | None = None


@dataclass
class GraphNode:
    id: str
    kind: str
    label: str
    work_uuid: str | None = None
    userid: str | None = None
    cx: float = 0
    cy: float = 0
    width: int = WORK_W
    height: int = WORK_H


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str  # success | fail


def parse_workflow_tokens(expression: str) -> list[FlowToken]:
    text = (expression or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in text.split("->") if part.strip()]
    if not parts:
        return []
    return [_parse_token(part) for part in parts]


def _parse_token(raw: str) -> FlowToken:
    token = raw.strip()
    upper = token.upper()
    if upper == "S":
        return FlowToken(kind="start", raw=token)
    if upper == "E":
        return FlowToken(kind="end", raw=token)
    if upper.startswith("H:"):
        userid = token.split(":", 1)[1].strip()
        if not userid:
            raise ValueError("HITL 표시자 H:{userid} 에 userid 가 필요합니다.")
        return FlowToken(kind="hitl", raw=token, userid=userid)
    if ":" in token:
        left, right = token.split(":", 1)
        left = left.strip()
        right = right.strip()
        if not is_uuid_token(left):
            raise ValueError(f"알 수 없는 워크플로우 토큰: {token}")
        if right.upper() == "E":
            return FlowToken(kind="work", raw=token, work_uuid=left, fail_end=True)
        if not is_uuid_token(right):
            raise ValueError(f"실패 대상이 올바르지 않습니다: {token}")
        if right == left:
            raise ValueError(f"실패 대상이 자신입니다: {token}")
        return FlowToken(kind="work", raw=token, work_uuid=left, fail_work_uuid=right)
    if is_uuid_token(token):
        return FlowToken(kind="work", raw=token, work_uuid=token)
    raise ValueError(f"알 수 없는 워크플로우 토큰: {token}")


def validate_workflow_expression(
    expression: str,
    *,
    known_work_uuids: set[str] | None = None,
    known_userids: set[str] | None = None,
) -> list[FlowToken]:
    tokens = parse_workflow_tokens(expression)
    if not tokens:
        return []
    if tokens[0].kind != "start":
        raise ValueError("워크플로우는 S 로 시작해야 합니다.")
    if tokens[-1].kind != "end":
        raise ValueError("워크플로우는 E 로 끝나야 합니다.")
    for token in tokens:
        if token.kind == "work":
            assert token.work_uuid is not None
            if known_work_uuids is not None and token.work_uuid not in known_work_uuids:
                raise ValueError(f"존재하지 않는 work_node uuid: {token.work_uuid}")
            if (
                token.fail_work_uuid is not None
                and known_work_uuids is not None
                and token.fail_work_uuid not in known_work_uuids
            ):
                raise ValueError(f"존재하지 않는 실패 work_node uuid: {token.fail_work_uuid}")
        if token.kind == "hitl" and token.userid and known_userids is not None:
            if token.userid not in known_userids:
                raise ValueError(f"존재하지 않는 HITL 승인자: {token.userid}")
    return tokens


def build_workflow_graph(
    expression: str,
    *,
    work_names: dict[str, str] | None = None,
    user_names: dict[str, str] | None = None,
    work_report_uuids: set[str] | None = None,
) -> dict[str, Any]:
    tokens = parse_workflow_tokens(expression)
    if not tokens:
        return {"nodes": [], "edges": [], "width": 200, "height": 160}

    names = work_names or {}
    users = user_names or {}
    report_uuids = work_report_uuids or set()
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    main_ids: list[str] = []
    id_by_work: dict[str, str] = {}
    end_id = "E"

    for index, token in enumerate(tokens):
        node_id = _main_node_id(token, index)
        label = _token_label(token, names, users)
        width, height = _token_size(token.kind)
        nodes.append(
            GraphNode(
                id=node_id,
                kind=token.kind,
                label=label,
                work_uuid=token.work_uuid,
                userid=token.userid,
                cx=ORIGIN_X + index * H_GAP,
                cy=MAIN_Y,
                width=width,
                height=height,
            )
        )
        main_ids.append(node_id)
        if token.kind == "work" and token.work_uuid is not None:
            id_by_work.setdefault(token.work_uuid, node_id)
        if token.kind == "end":
            end_id = node_id

    for index in range(len(main_ids) - 1):
        edges.append(GraphEdge(source=main_ids[index], target=main_ids[index + 1], kind="success"))

    fail_slot = 0
    for index, token in enumerate(tokens):
        if token.kind != "work":
            continue
        source_id = main_ids[index]
        next_id = main_ids[index + 1] if index + 1 < len(main_ids) else end_id
        if token.fail_work_uuid is not None:
            fail_id = id_by_work.get(token.fail_work_uuid)
            if fail_id is None:
                fail_id = f"F{token.fail_work_uuid}"
                source = nodes[index]
                nodes.append(
                    GraphNode(
                        id=fail_id,
                        kind="work",
                        label=names.get(token.fail_work_uuid, token.fail_work_uuid),
                        work_uuid=token.fail_work_uuid,
                        cx=source.cx + 20 + fail_slot * 24,
                        cy=FAIL_Y,
                        width=WORK_W,
                        height=WORK_H,
                    )
                )
                id_by_work[token.fail_work_uuid] = fail_id
                fail_slot += 1
                edges.append(GraphEdge(source=fail_id, target=next_id, kind="success"))
                edges.append(GraphEdge(source=fail_id, target=end_id, kind="fail"))
            edges.append(GraphEdge(source=source_id, target=fail_id, kind="fail"))
        elif token.fail_end:
            edges.append(GraphEdge(source=source_id, target=end_id, kind="fail"))

    for node in list(nodes):
        if node.kind != "work" or not node.work_uuid:
            continue
        if node.work_uuid not in report_uuids:
            continue
        mail_id = f"M:{node.id}"
        mail_cy = node.cy + node.height / 2 + MAIL_GAP + MAIL_R
        nodes.append(
            GraphNode(
                id=mail_id,
                kind="mail",
                label="메일전송",
                work_uuid=node.work_uuid,
                cx=node.cx,
                cy=mail_cy,
                width=MAIL_R * 2,
                height=MAIL_R * 2,
            )
        )
        edges.append(GraphEdge(source=node.id, target=mail_id, kind="report"))

    max_x = max((node.cx + node.width / 2 for node in nodes), default=ORIGIN_X)
    max_y = max((node.cy + node.height / 2 for node in nodes), default=MAIN_Y)
    return {
        "nodes": [
            {
                "id": node.id,
                "kind": node.kind,
                "label": node.label,
                "work_uuid": node.work_uuid,
                "userid": node.userid,
                "cx": node.cx,
                "cy": node.cy,
                "width": node.width,
                "height": node.height,
            }
            for node in nodes
        ],
        "edges": [
            {"source": edge.source, "target": edge.target, "kind": edge.kind} for edge in edges
        ],
        "width": int(max_x + ORIGIN_X),
        "height": int(max_y + 60),
    }


def _main_node_id(token: FlowToken, index: int) -> str:
    if token.kind == "start":
        return "S"
    if token.kind == "end":
        return "E"
    if token.kind == "hitl":
        return f"H:{token.userid}@{index}"
    return f"W{token.work_uuid}@{index}"


def _token_label(
    token: FlowToken,
    work_names: dict[str, str],
    user_names: dict[str, str],
) -> str:
    if token.kind == "start":
        return "시작"
    if token.kind == "end":
        return "종료"
    if token.kind == "hitl":
        userid = token.userid or ""
        return user_names.get(userid, userid)
    if token.work_uuid is not None:
        return work_names.get(token.work_uuid, token.work_uuid)
    return token.raw


def _token_size(kind: str) -> tuple[int, int]:
    if kind in {"start", "end"}:
        return (ROUND_R * 2, ROUND_R * 2)
    if kind == "hitl":
        return (HITL_W, HITL_H)
    return (WORK_W, WORK_H)
