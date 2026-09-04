"""Load agent skills from docs/skill/{skill_name}.md."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.app.config import PROJECT_ROOT

SKILL_DIR = PROJECT_ROOT / "docs" / "skill"


def skill_path(skill_name: str) -> Path:
    normalized = skill_name.strip()
    if not normalized:
        raise ValueError("skill_name is required")
    return SKILL_DIR / f"{normalized}.md"


def read_skill(skill_name: str) -> str:
    path = skill_path(skill_name)
    if not path.is_file():
        raise FileNotFoundError(f"Skill file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=128)
def load_skill(skill_name: str) -> str:
    return read_skill(skill_name)
