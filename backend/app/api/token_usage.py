from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from backend.app.disabled_features import raise_token_usage_disabled

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
    description: str = "disabled"
    agents: list[TokenUsageAgentRow]


class PeriodTokenUsageResponse(BaseModel):
    source: str = "prompt_debug"
    description: str = "disabled"
    since: str | None = None
    until: str | None = None
    agents: list[TokenUsageAgentRow]


class ResetTokenUsageRequest(BaseModel):
    viewer_role: int


class ResetTokenUsageResponse(BaseModel):
    ok: bool = True
    cleared_agents: int


class ResetAgentTokenUsageResponse(BaseModel):
    ok: bool = True
    agent_id: str
    cleared: bool


@router.get("/agents/token-usage", response_model=CumulativeTokenUsageResponse)
async def get_cumulative_token_usage(
    request: Request,
    include_all: bool = Query(default=False),
) -> CumulativeTokenUsageResponse:
    raise_token_usage_disabled()


@router.get("/agents/token-usage/period", response_model=PeriodTokenUsageResponse)
async def get_period_token_usage(
    request: Request,
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
) -> PeriodTokenUsageResponse:
    raise_token_usage_disabled()


@router.post("/agents/token-usage/reset", response_model=ResetTokenUsageResponse)
async def reset_cumulative_token_usage(
    payload: ResetTokenUsageRequest,
    request: Request,
) -> ResetTokenUsageResponse:
    raise_token_usage_disabled()


@router.post("/agents/token-usage/{agent_id}/reset", response_model=ResetAgentTokenUsageResponse)
async def reset_agent_token_usage(
    agent_id: str,
    payload: ResetTokenUsageRequest,
    request: Request,
) -> ResetAgentTokenUsageResponse:
    raise_token_usage_disabled()
