from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from backend.app.db.roles import ROLE_ADMIN
from backend.app.logging.prompt_debug import aggregate_llm_token_usage
from backend.app.usage.token_tracker import AgentTokenUsage

router = APIRouter(tags=["token-usage"])


class TokenUsageAgentRow(BaseModel):
    agent_id: str
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    call_count: int | None = None
    is_system: bool = False


class CumulativeTokenUsageResponse(BaseModel):
    source: str = "cumulative"
    description: str = "서버 기동 후 TokenTracker 누적 (에이전트 타일과 동일)"
    agents: list[TokenUsageAgentRow]


class PeriodTokenUsageResponse(BaseModel):
    source: str = "prompt_debug"
    description: str = "Prompt Debug LLM 교환 기록 기간 합산 (메모리 최대 500건)"
    since: str | None = None
    until: str | None = None
    agents: list[TokenUsageAgentRow]


class ResetTokenUsageRequest(BaseModel):
    viewer_role: int


class ResetTokenUsageResponse(BaseModel):
    ok: bool = True
    cleared_agents: int


def _require_admin(viewer_role: int) -> None:
    if viewer_role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="관리자만 토큰 누적을 초기화할 수 있습니다.")


def _row_from_usage(agent_id: str, agent_name: str, usage: AgentTokenUsage) -> TokenUsageAgentRow:
    return TokenUsageAgentRow(
        agent_id=agent_id,
        agent_name=agent_name,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )


def _build_cumulative_rows(request: Request, *, include_all: bool = False) -> list[TokenUsageAgentRow]:
    manager = request.app.state.agent_manager
    tracker = manager.token_tracker
    if tracker is None:
        return []

    usage_by_id = tracker.get_all_usage()
    name_by_id: dict[str, str] = {}
    is_system_by_id: dict[str, bool] = {}
    for definition in manager.agent_definitions:
        name_by_id[definition.agent_id] = definition.name
        is_system_by_id[definition.agent_id] = False
    for definition in manager.system_agent_definitions:
        name_by_id[definition.agent_id] = definition.name
        is_system_by_id[definition.agent_id] = True

    if include_all:
        agent_ids = sorted(name_by_id)
    else:
        agent_ids = sorted(set(name_by_id) | set(usage_by_id))

    rows: list[TokenUsageAgentRow] = []
    for agent_id in agent_ids:
        usage = usage_by_id.get(agent_id, AgentTokenUsage())
        if not include_all and usage.total_tokens == 0 and agent_id not in usage_by_id:
            continue
        rows.append(
            TokenUsageAgentRow(
                agent_id=agent_id,
                agent_name=name_by_id.get(agent_id, agent_id),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                is_system=is_system_by_id.get(agent_id, False),
            ),
        )
    return rows


def _parse_iso_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}은 ISO 8601 형식이어야 합니다.",
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class ResetAgentTokenUsageResponse(BaseModel):
    ok: bool = True
    agent_id: str
    cleared: bool


@router.get("/agents/token-usage", response_model=CumulativeTokenUsageResponse)
async def get_cumulative_token_usage(
    request: Request,
    include_all: bool = Query(default=False, description="등록된 모든 에이전트 포함(0 토큰 포함)"),
) -> CumulativeTokenUsageResponse:
    return CumulativeTokenUsageResponse(agents=_build_cumulative_rows(request, include_all=include_all))


@router.get("/agents/token-usage/period", response_model=PeriodTokenUsageResponse)
async def get_period_token_usage(
    request: Request,
    since: str | None = Query(default=None, description="ISO 8601 시작 시각 (포함)"),
    until: str | None = Query(default=None, description="ISO 8601 종료 시각 (포함)"),
    agent_id: str | None = Query(default=None, description="특정 에이전트만 합산"),
) -> PeriodTokenUsageResponse:
    del request
    since_dt = _parse_iso_datetime(since, field_name="since")
    until_dt = _parse_iso_datetime(until, field_name="until")
    if since_dt and until_dt and since_dt > until_dt:
        raise HTTPException(status_code=400, detail="since는 until보다 이후일 수 없습니다.")

    aggregated: list[dict[str, Any]] = aggregate_llm_token_usage(
        since=since_dt,
        until=until_dt,
        agent_id=agent_id,
    )
    rows = [
        TokenUsageAgentRow(
            agent_id=str(item["agent_id"]),
            agent_name=str(item["agent_name"]),
            input_tokens=int(item["input_tokens"]),
            output_tokens=int(item["output_tokens"]),
            total_tokens=int(item["total_tokens"]),
            call_count=int(item["call_count"]),
        )
        for item in aggregated
    ]
    return PeriodTokenUsageResponse(
        since=since_dt.isoformat() if since_dt else None,
        until=until_dt.isoformat() if until_dt else None,
        agents=rows,
    )


@router.post("/agents/token-usage/reset", response_model=ResetTokenUsageResponse)
async def reset_cumulative_token_usage(
    payload: ResetTokenUsageRequest,
    request: Request,
) -> ResetTokenUsageResponse:
    _require_admin(payload.viewer_role)
    manager = request.app.state.agent_manager
    tracker = manager.token_tracker
    if tracker is None:
        return ResetTokenUsageResponse(cleared_agents=0)
    return ResetTokenUsageResponse(cleared_agents=tracker.reset_all())


@router.post("/agents/token-usage/{agent_id}/reset", response_model=ResetAgentTokenUsageResponse)
async def reset_agent_token_usage(
    agent_id: str,
    payload: ResetTokenUsageRequest,
    request: Request,
) -> ResetAgentTokenUsageResponse:
    _require_admin(payload.viewer_role)
    manager = request.app.state.agent_manager
    try:
        manager.get_definition(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found") from exc

    tracker = manager.token_tracker
    if tracker is None:
        return ResetAgentTokenUsageResponse(agent_id=agent_id, cleared=False)

    cleared = tracker.reset_agent(agent_id)
    return ResetAgentTokenUsageResponse(agent_id=agent_id, cleared=cleared)
