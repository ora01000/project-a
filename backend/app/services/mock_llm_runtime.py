"""Runtime LLM provider selection for mock (AGENT_RUNTIME_MODE=mock) environments."""

from __future__ import annotations

import json
import logging
from typing import Literal

from backend.app.config import LLMSettings, PROJECT_ROOT, _env_setting, load_settings

logger = logging.getLogger(__name__)

MockLlmProvider = Literal["local", "openai"]

MOCK_LLM_PROVIDER_LOCAL: MockLlmProvider = "local"
MOCK_LLM_PROVIDER_OPENAI: MockLlmProvider = "openai"

OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
RUNTIME_STATE_PATH = PROJECT_ROOT / "data" / "mock_llm_runtime.json"

MOCK_LLM_PROVIDER_LOCAL: MockLlmProvider = "local"
MOCK_LLM_PROVIDER_OPENAI: MockLlmProvider = "openai"

OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

OPENAI_MODEL_OPTIONS: tuple[str, ...] = (
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4.1",
    "o3-mini",
    "o1-mini",
)

_current_provider: MockLlmProvider = MOCK_LLM_PROVIDER_LOCAL
_runtime_openai_api_key: str = ""
_runtime_openai_model: str = DEFAULT_OPENAI_MODEL


def get_mock_llm_provider() -> MockLlmProvider:
    return _current_provider


def mask_api_key(api_key: str) -> str:
    trimmed = api_key.strip()
    if not trimmed:
        return ""
    if len(trimmed) <= 8:
        return "*" * len(trimmed)
    return f"{trimmed[:4]}...{trimmed[-4:]}"


def resolve_openai_api_key() -> str:
    if _runtime_openai_api_key.strip():
        return _runtime_openai_api_key.strip()
    return (
        _env_setting("MOCK_OPENAI_API_KEY")
        or _env_setting("OPENAI_API_KEY")
    ).strip()


def resolve_openai_model() -> str:
    if _runtime_openai_model.strip():
        return _runtime_openai_model.strip()
    return (_env_setting("MOCK_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip()


def set_mock_llm_provider(
    provider: str,
    *,
    openai_api_key: str | None = None,
    openai_model: str | None = None,
) -> MockLlmProvider:
    global _current_provider, _runtime_openai_api_key, _runtime_openai_model

    normalized = provider.strip().lower()
    if normalized not in (MOCK_LLM_PROVIDER_LOCAL, MOCK_LLM_PROVIDER_OPENAI):
        raise ValueError("provider는 local 또는 openai 만 허용됩니다.")

    if openai_model is not None:
        model = openai_model.strip()
        if not model:
            raise ValueError("OpenAI model을 입력해 주세요.")
        _runtime_openai_model = model

    if openai_api_key is not None:
        key = openai_api_key.strip()
        if key:
            _runtime_openai_api_key = key

    if normalized == MOCK_LLM_PROVIDER_OPENAI and not resolve_openai_api_key():
        raise ValueError("OpenAI API key를 입력해 주세요.")

    _current_provider = normalized  # type: ignore[assignment]
    persist_runtime_state()
    return _current_provider


def persist_runtime_state() -> None:
    try:
        RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, str] = {
            "provider": _current_provider,
            "openai_model": _runtime_openai_model,
        }
        if _runtime_openai_api_key.strip():
            payload["openai_api_key"] = _runtime_openai_api_key.strip()
        RUNTIME_STATE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to persist mock LLM runtime state: %s", exc)


def load_persisted_runtime_state() -> None:
    global _current_provider

    if not RUNTIME_STATE_PATH.exists():
        return
    try:
        payload = json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load mock LLM runtime state: %s", exc)
        return

    if not isinstance(payload, dict):
        return

    provider = str(payload.get("provider") or MOCK_LLM_PROVIDER_LOCAL).strip().lower()
    if provider == MOCK_LLM_PROVIDER_LOCAL:
        _current_provider = MOCK_LLM_PROVIDER_LOCAL
        return

    raw_key = payload.get("openai_api_key")
    openai_api_key = str(raw_key).strip() if raw_key else None
    openai_model = str(payload.get("openai_model") or DEFAULT_OPENAI_MODEL)
    try:
        set_mock_llm_provider(
            MOCK_LLM_PROVIDER_OPENAI,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
        )
    except ValueError as exc:
        logger.warning("Skipped persisted mock OpenAI LLM settings: %s", exc)


def describe_local_llm_settings() -> dict[str, str | int]:
    settings = load_settings()[0]
    return {
        "label": "기존 Local LLM",
        "base_url": settings.base_url,
        "model": settings.model,
        "max_context_tokens": settings.max_context_tokens,
    }


def describe_openai_llm_settings() -> dict[str, str | int | bool | list[str]]:
    api_key = resolve_openai_api_key()
    return {
        "label": "OpenAI",
        "base_url": OPENAI_BASE_URL,
        "model": resolve_openai_model(),
        "configured": bool(api_key),
        "api_key_masked": mask_api_key(api_key),
        "available_models": list(OPENAI_MODEL_OPTIONS),
    }


def list_mock_llm_options() -> list[dict[str, object]]:
    return [
        {
            "id": MOCK_LLM_PROVIDER_LOCAL,
            **describe_local_llm_settings(),
        },
        {
            "id": MOCK_LLM_PROVIDER_OPENAI,
            **describe_openai_llm_settings(),
        },
    ]


def apply_mock_llm_override(settings: LLMSettings) -> LLMSettings:
    if get_mock_llm_provider() != MOCK_LLM_PROVIDER_OPENAI:
        return settings

    api_key = resolve_openai_api_key()
    if not api_key:
        raise RuntimeError("OpenAI provider is selected but API key is not configured.")

    return LLMSettings(
        base_url=OPENAI_BASE_URL,
        api_key=api_key,
        model=resolve_openai_model(),
        max_context_tokens=settings.max_context_tokens,
    )
