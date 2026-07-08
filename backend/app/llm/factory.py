from langchain_openai import ChatOpenAI

from backend.app.config import LLMSettings, load_settings


def get_llm(settings: LLMSettings | None = None) -> ChatOpenAI:
    llm_settings = settings or load_settings()[0]
    return ChatOpenAI(
        base_url=llm_settings.base_url,
        api_key=llm_settings.api_key,
        model=llm_settings.model,
        temperature=0,
        streaming=False,
        disable_streaming="tool_calling",
    )
