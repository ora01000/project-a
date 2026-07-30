"""Assignable agent ID helpers."""

from __future__ import annotations

from pathlib import Path

from backend.app.agents.registry import AGENT_DEFINITIONS_BY_ID
from backend.app.db.agentruntime import list_agentruntime_records
from backend.app.services.agent_runtime_client import normalize_runtime_mode


def known_assignable_agent_ids(database_path: str | Path, *, runtime_mode: str) -> set[str]:
    if normalize_runtime_mode(runtime_mode) == "mock":
        return set(AGENT_DEFINITIONS_BY_ID.keys())
    return {
        record.local_agent_id.strip()
        for record in list_agentruntime_records(database_path, runtime_mode=runtime_mode)
        if record.local_agent_id.strip()
    }
