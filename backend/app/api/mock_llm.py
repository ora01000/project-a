"""Mock-runtime LLM provider selection (admin only)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import resolve_agent_runtime_mode
from backend.app.db.roles import ROLE_ADMIN
from backend.app.services.agent_runtime_client import normalize_runtime_mode
from backend.app.services.mock_llm_runtime import (
    describe_local_llm_settings,
    describe_openai_llm_settings,
    get_mock_llm_provider,
    list_mock_llm_options,
    set_mock_llm_provider,
)

router = APIRouter(tags=["debug"])


class MockLlmOpenAiSettings(BaseModel):
    label: str
    base_url: str
    model: str
    configured: bool
    api_key_masked: str
    available_models: list[str]


class MockLlmStateResponse(BaseModel):
    provider: Literal["local", "openai"]
    options: list[dict[str, object]]
    local: dict[str, str | int]
    openai: MockLlmOpenAiSettings


class MockLlmUpdateRequest(BaseModel):
    viewer_role: int
    provider: Literal["local", "openai"]
    openai_api_key: str | None = Field(default=None, max_length=500)
    openai_model: str | None = Field(default=None, max_length=100)


def _require_admin(viewer_role: int) -> None:
    if viewer_role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _require_mock_runtime(request: Request) -> None:
    mode = normalize_runtime_mode(
        getattr(request.app.state, "agent_runtime_mode", resolve_agent_runtime_mode()),
    )
    if mode != "mock":
        raise HTTPException(
            status_code=403,
            detail="목업 LLM 변경은 AGENT_RUNTIME_MODE=mock 환경에서만 사용할 수 있습니다.",
        )


def _build_state_response() -> MockLlmStateResponse:
    openai_settings = describe_openai_llm_settings()
    return MockLlmStateResponse(
        provider=get_mock_llm_provider(),
        options=list_mock_llm_options(),
        local=describe_local_llm_settings(),
        openai=MockLlmOpenAiSettings(
            label=str(openai_settings["label"]),
            base_url=str(openai_settings["base_url"]),
            model=str(openai_settings["model"]),
            configured=bool(openai_settings["configured"]),
            api_key_masked=str(openai_settings["api_key_masked"]),
            available_models=[
                str(model) for model in openai_settings.get("available_models", [])
            ],
        ),
    )


@router.get("/debug/mock-llm", response_model=MockLlmStateResponse)
async def get_mock_llm_state(request: Request) -> MockLlmStateResponse:
    _require_mock_runtime(request)
    return _build_state_response()


@router.put("/debug/mock-llm", response_model=MockLlmStateResponse)
async def update_mock_llm_state(
    request: Request,
    payload: MockLlmUpdateRequest,
) -> MockLlmStateResponse:
    _require_mock_runtime(request)
    _require_admin(payload.viewer_role)
    try:
        set_mock_llm_provider(
            payload.provider,
            openai_api_key=payload.openai_api_key,
            openai_model=payload.openai_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    manager = getattr(request.app.state, "agent_manager", None)
    if manager is not None:
        await manager.rebuild_langgraph_agents()

    return _build_state_response()
