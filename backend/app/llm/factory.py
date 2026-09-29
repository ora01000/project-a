from langchain_openai import ChatOpenAI

from backend.app.config import LLMSettings, load_settings


def get_effective_llm_settings() -> LLMSettings:
    from backend.app.config import resolve_agent_runtime_mode
    from backend.app.services.agent_runtime_client import normalize_runtime_mode
    from backend.app.services.mock_llm_runtime import apply_mock_llm_override

    llm_settings = load_settings()[0]
    if normalize_runtime_mode(resolve_agent_runtime_mode()) == "mock":
        llm_settings = apply_mock_llm_override(llm_settings)
    return llm_settings


def is_openai_billing_llm(settings: LLMSettings | None = None) -> bool:
    effective = settings or get_effective_llm_settings()
    return "api.openai.com" in effective.base_url.lower()


def get_llm(settings: LLMSettings | None = None) -> ChatOpenAI:
    from backend.app.config import resolve_agent_runtime_mode
    from backend.app.services.agent_runtime_client import normalize_runtime_mode
    from backend.app.services.mock_llm_runtime import apply_mock_llm_override

    llm_settings = settings or load_settings()[0]
    if normalize_runtime_mode(resolve_agent_runtime_mode()) == "mock":
        llm_settings = apply_mock_llm_override(llm_settings)
    return ChatOpenAI(
        base_url=llm_settings.base_url,
        api_key=llm_settings.api_key,
        model=llm_settings.model,
        temperature=0,
        streaming=False,
        disable_streaming="tool_calling",
    )
