import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.agents.base import ToolUsage
from backend.app.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

AGENT_LOGS_DIR = PROJECT_ROOT / "logs" / "agents"


def ensure_agent_logs_dir() -> None:
    AGENT_LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _serialize_tools(tools_used: list[ToolUsage]) -> list[dict[str, str | None]]:
    return [
        {"name": tool.name, "mcp_server": tool.mcp_server}
        for tool in tools_used
    ]


def log_agent_interaction(
    agent_id: str,
    input_message: str,
    output_message: str,
    tools_used: list[ToolUsage],
) -> None:
    ensure_agent_logs_dir()

    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": agent_id,
        "input_message": input_message,
        "output_message": output_message,
        "tools": _serialize_tools(tools_used),
    }

    log_path = AGENT_LOGS_DIR / f"{agent_id}.log"
    line = json.dumps(entry, ensure_ascii=False)

    try:
        with log_path.open("a", encoding="utf-8") as file:
            file.write(f"{line}\n")
    except OSError as exc:
        logger.error("Failed to write agent log for %s: %s", agent_id, exc)


def log_agent_error(
    agent_id: str,
    *,
    reason: str,
    input_message: str | None = None,
) -> None:
    ensure_agent_logs_dir()

    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": agent_id,
        "event": "agent_operation_error",
        "reason": reason,
    }
    if input_message is not None:
        entry["input_message"] = input_message

    log_path = AGENT_LOGS_DIR / f"{agent_id}.log"
    line = json.dumps(entry, ensure_ascii=False)

    try:
        with log_path.open("a", encoding="utf-8") as file:
            file.write(f"{line}\n")
    except OSError as exc:
        logger.error("Failed to write agent error log for %s: %s", agent_id, exc)


def list_all_agent_logs(limit: int | None = None) -> list[dict[str, Any]]:
    ensure_agent_logs_dir()
    entries: list[dict[str, Any]] = []

    for log_path in sorted(AGENT_LOGS_DIR.glob("*.log")):
        agent_id = log_path.stem
        try:
            with log_path.open(encoding="utf-8") as file:
                for line in file:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        entry = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    if "agent_id" not in entry:
                        entry["agent_id"] = agent_id
                    entries.append(entry)
        except OSError as exc:
            logger.warning("Failed to read agent log %s: %s", log_path, exc)

    entries.sort(key=lambda entry: str(entry.get("timestamp", "")), reverse=True)
    if limit is not None and limit > 0:
        return entries[:limit]
    return entries
