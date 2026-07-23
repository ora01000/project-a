import json
import logging
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.agents.base import ToolUsage
from backend.app.config import PROJECT_ROOT, UserCommLogSettings, load_user_comm_log_settings
from backend.app.timezone import now_display_datetime

logger = logging.getLogger(__name__)

_USER_ID_PATTERN = re.compile(r"^[\w.-]+$")
_file_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_last_retention_cleanup_date: date | None = None


def _sanitize_user_id(user_id: str) -> str:
    normalized = user_id.strip()
    if not normalized or not _USER_ID_PATTERN.match(normalized):
        raise ValueError(f"Invalid user id for comm log: {user_id!r}")
    return normalized


def _resolve_log_dir(settings: UserCommLogSettings) -> Path:
    path = Path(settings.log_dir)
    if not path.is_absolute():
        return PROJECT_ROOT / path
    return path


def _local_date() -> date:
    return now_display_datetime().date()


def _log_file_path(log_dir: Path, user_id: str, log_date: date) -> Path:
    return log_dir / user_id / f"{log_date.isoformat()}.json"


def _get_file_lock(key: str) -> threading.Lock:
    with _locks_guard:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


def _serialize_tools(tools_used: list[ToolUsage]) -> list[dict[str, str | None]]:
    return [
        {"name": tool.name, "mcp_server": tool.mcp_server}
        for tool in tools_used
    ]


def _load_log_file(path: Path, user_id: str, log_date: date) -> dict[str, Any]:
    if not path.exists():
        return {"user_id": user_id, "date": log_date.isoformat(), "entries": []}

    try:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
        if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
            return payload
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read user comm log %s: %s", path, exc)

    return {"user_id": user_id, "date": log_date.isoformat(), "entries": []}


def cleanup_expired_logs(settings: UserCommLogSettings | None = None) -> int:
    settings = settings or load_user_comm_log_settings()
    log_dir = _resolve_log_dir(settings)
    if not log_dir.exists():
        return 0

    retention_days = max(1, settings.retention_days)
    cutoff = _local_date() - timedelta(days=retention_days)
    removed = 0

    for user_dir in log_dir.iterdir():
        if not user_dir.is_dir():
            continue

        for log_file in user_dir.glob("*.json"):
            try:
                file_date = date.fromisoformat(log_file.stem)
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    log_file.unlink()
                    removed += 1
                except OSError as exc:
                    logger.warning("Failed to remove expired comm log %s: %s", log_file, exc)

        try:
            if user_dir.exists() and not any(user_dir.iterdir()):
                user_dir.rmdir()
        except OSError:
            pass

    if removed:
        logger.info("Removed %s expired user comm log file(s)", removed)
    return removed


def _maybe_cleanup_retention(settings: UserCommLogSettings) -> None:
    global _last_retention_cleanup_date

    today = _local_date()
    if _last_retention_cleanup_date == today:
        return

    cleanup_expired_logs(settings)
    _last_retention_cleanup_date = today


def initialize_user_comm_logs(settings: UserCommLogSettings | None = None) -> Path:
    settings = settings or load_user_comm_log_settings()
    log_dir = _resolve_log_dir(settings)
    log_dir.mkdir(parents=True, exist_ok=True)
    cleanup_expired_logs(settings)
    return log_dir


def log_user_communication(
    user_id: str,
    *,
    agent_id: str,
    agent_name: str,
    user_message: str,
    assistant_message: str,
    tools_used: list[ToolUsage] | None = None,
    settings: UserCommLogSettings | None = None,
) -> None:
    settings = settings or load_user_comm_log_settings()
    safe_user_id = _sanitize_user_id(user_id)
    log_date = _local_date()
    log_dir = _resolve_log_dir(settings)
    user_dir = log_dir / safe_user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    log_path = _log_file_path(log_dir, safe_user_id, log_date)
    lock_key = f"{safe_user_id}:{log_date.isoformat()}"
    entry = {
        "timestamp": now_display_datetime().isoformat(),
        "agent_id": agent_id,
        "agent_name": agent_name,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "tools": _serialize_tools(tools_used or []),
    }

    with _get_file_lock(lock_key):
        payload = _load_log_file(log_path, safe_user_id, log_date)
        payload["entries"].append(entry)
        try:
            with log_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error("Failed to write user comm log for %s: %s", safe_user_id, exc)
            return

    _maybe_cleanup_retention(settings)


def list_user_communications(
    user_id: str,
    *,
    log_date: date | None = None,
    settings: UserCommLogSettings | None = None,
) -> dict[str, Any]:
    settings = settings or load_user_comm_log_settings()
    safe_user_id = _sanitize_user_id(user_id)
    target_date = log_date or _local_date()
    log_dir = _resolve_log_dir(settings)
    log_path = _log_file_path(log_dir, safe_user_id, target_date)
    lock_key = f"{safe_user_id}:{target_date.isoformat()}"

    with _get_file_lock(lock_key):
        payload = _load_log_file(log_path, safe_user_id, target_date)

    return payload
