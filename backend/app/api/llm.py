"""LLM runtime status for client-side safeguards."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.llm.factory import get_effective_llm_settings, is_openai_billing_llm

router = APIRouter(tags=["llm"])


class LlmBillingStatusResponse(BaseModel):
    requires_confirmation: bool
    provider: str
    model: str | None = None


@router.get("/llm/billing-status", response_model=LlmBillingStatusResponse)
async def get_llm_billing_status() -> LlmBillingStatusResponse:
    settings = get_effective_llm_settings()
    requires_confirmation = is_openai_billing_llm(settings)
    return LlmBillingStatusResponse(
        requires_confirmation=requires_confirmation,
        provider="openai" if requires_confirmation else "local",
        model=settings.model if requires_confirmation else None,
    )
