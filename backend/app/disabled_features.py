"""Removed agents and disabled product features."""

from __future__ import annotations

from fastapi import HTTPException

REMOVED_AGENT_IDS: frozenset[str] = frozenset()

DISABLED_FEATURE_DETAIL = "요청한 기능이 비활성화되었습니다."

TOKEN_USAGE_DISABLED_DETAIL = "토큰 사용량 조회·관리 기능이 비활성화되었습니다."


def is_removed_agent_id(agent_id: str) -> bool:
    return agent_id in REMOVED_AGENT_IDS


def filter_agent_definitions(definitions: list) -> list:
    return [definition for definition in definitions if not is_removed_agent_id(definition.agent_id)]


def raise_disabled_feature() -> None:
    raise HTTPException(status_code=503, detail=DISABLED_FEATURE_DETAIL)


def raise_token_usage_disabled() -> None:
    raise HTTPException(status_code=503, detail=TOKEN_USAGE_DISABLED_DETAIL)
