"""Post-process WORKFLOW_AGENT JSON so agent nodes always carry ``crud``."""

from __future__ import annotations

import json
import re
from typing import Any

_CRUD_ORDER = ("c", "r", "u", "d")

_DELETE_RE = re.compile(
    r"\b(delete|remove|destroy|uninstall)\b|삭제|제거|폐기",
    re.IGNORECASE,
)
_CREATE_RE = re.compile(
    r"\b(create(?!\s+report)|apply|install|deploy|provision)\b|생성|배포|설치|프로비저닝",
    re.IGNORECASE,
)
_UPDATE_RE = re.compile(
    r"\b(update|patch|renew|replace|modify|scale)\b|갱신|수정|변경|교체|패치",
    re.IGNORECASE,
)
_READ_RE = re.compile(
    r"\b(get|list|check|query|inspect|status|report|extract|describe|show|read)\b|"
    r"조회|확인|추출|상태|리포트|보고|검증|필터",
    re.IGNORECASE,
)


def _normalize_crud_list(value: Any) -> list[str] | None:
    """Return normalized crud letters, or None when the field is absent/invalid-empty."""
    if value is None:
        return None
    found: list[str] = []
    seen: set[str] = set()

    def push(token: str) -> None:
        lower = token.strip().lower()
        if not lower:
            return
        if len(lower) == 1 and lower in _CRUD_ORDER and lower not in seen:
            seen.add(lower)
            found.append(lower)
            return
        for ch in lower:
            if ch in _CRUD_ORDER and ch not in seen:
                seen.add(ch)
                found.append(ch)

    if isinstance(value, list):
        if len(value) == 0:
            return []
        for item in value:
            push(str(item or ""))
        return found
    raw = str(value).strip()
    if not raw:
        return None
    for part in re.split(r"[\s,;|/]+", raw):
        push(part)
    return found


def infer_crud_for_work_node(node: dict[str, Any]) -> list[str]:
    """Infer CRUD letters from work-node text when the model omitted ``crud``."""
    blob = " ".join(
        str(node.get(key) or "")
        for key in ("work_name", "work_description", "work_script", "script_type")
    )
    flags: list[str] = []
    if _CREATE_RE.search(blob):
        flags.append("c")
    if _READ_RE.search(blob):
        flags.append("r")
    if _UPDATE_RE.search(blob):
        flags.append("u")
    if _DELETE_RE.search(blob):
        flags.append("d")
    if not flags:
        flags.append("r")
    # Stable order c→r→u→d
    return [letter for letter in _CRUD_ORDER if letter in flags]


def enrich_workflow_agent_json(content: str) -> str:
    """Ensure every agent ``work_node`` has a ``crud`` array; strip HITL ``crud``."""
    stripped = content.strip()
    if not stripped.startswith("{"):
        return content

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return content
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return content

    nodes = data.get("work_node")
    if not isinstance(nodes, list):
        return content

    changed = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        worker = str(node.get("worker") or "agent").strip().lower()
        if worker == "hitl":
            if "crud" in node:
                node.pop("crud", None)
                changed = True
            continue
        if "crud" in node:
            normalized = _normalize_crud_list(node.get("crud"))
            if normalized is None:
                node["crud"] = infer_crud_for_work_node(node)
                changed = True
            elif node.get("crud") != normalized:
                node["crud"] = normalized
                changed = True
            continue
        node["crud"] = infer_crud_for_work_node(node)
        changed = True

    if not changed:
        return content
    return json.dumps(data, ensure_ascii=False, indent=2)
