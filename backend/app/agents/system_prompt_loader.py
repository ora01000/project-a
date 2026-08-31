"""Load agent system prompts from docs/system-prompt/{agent_name}_PROMPT.md."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.app.config import PROJECT_ROOT

SYSTEM_PROMPT_DIR = PROJECT_ROOT / "docs" / "system-prompt"


def system_prompt_path(agent_name: str) -> Path:
    normalized = agent_name.strip()
    if not normalized:
        raise ValueError("agent_name is required")
    return SYSTEM_PROMPT_DIR / f"{normalized}_PROMPT.md"


def read_system_prompt(agent_name: str) -> str:
    path = system_prompt_path(agent_name)
    if not path.is_file():
        raise FileNotFoundError(f"System prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=128)
def load_system_prompt(agent_name: str) -> str:
    return read_system_prompt(agent_name)


def load_system_prompt_template(agent_name: str, **values: str) -> str:
    template = load_system_prompt(agent_name)
    if not values:
        return template
    return template.format(**values)
