"""Workflow / work_node agent conversation logs (separate from dashboard chat logs)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.agents.base import ToolUsage
from backend.app.config import PROJECT_ROOT, load_agent_log_settings
from backend.app.logging.log_retention import enforce_named_retention
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

logger = logging.getLogger(__name__)

WORKFLOW_LOGS_DIR = PROJECT_ROOT / "logs" / "workflow"

_USER_ID_PATTERN = re.compile(r"^[\w.-]+$")
_SCOPE_ID_PATTERN = re.compile(r"^[\w.-]+$")
_file_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_last_cleanup_date = None


def ensure_workflow_logs_dir() -> None:
    WORKFLOW_LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _get_file_lock(key: str) -> threading.Lock:
    with _locks_guard:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


def _sanitize_segment(value: str, *, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized or not _SCOPE_ID_PATTERN.match(normalized):
        raise ValueError(f"Invalid {label} for workflow log: {value!r}")
    return normalized


def _sanitize_userid(user_id: str) -> str:
    normalized = (user_id or "").strip()
    if not normalized or not _USER_ID_PATTERN.match(normalized):
        raise ValueError(f"Invalid user id for workflow log: {user_id!r}")
    return normalized


def _serialize_tools(tools_used: list[ToolUsage] | None) -> list[dict[str, str | None]]:
    return [
        {"name": tool.name, "mcp_server": tool.mcp_server}
        for tool in (tools_used or [])
    ]


def workflow_agent_log_path(userid: str, workflow_key: str) -> Path:
    return (
        WORKFLOW_LOGS_DIR
        / _sanitize_userid(userid)
        / _sanitize_segment(workflow_key, label="workflow key")
        / "workflow.log"
    )


def work_node_agent_log_path(userid: str, work_uuid: str) -> Path:
    return (
        WORKFLOW_LOGS_DIR
        / _sanitize_userid(userid)
        / _sanitize_segment(work_uuid, label="work_node uuid")
        / "work_node.log"
    )


def _file_local_date(path: Path):
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=DISPLAY_TIMEZONE)
    return mtime.date()


def _rotated_sort_key(path: Path) -> str:
    # workflow_YYYYMMDDHHMISS.log / work_node_YYYYMMDDHHMISS.log
    stem = path.name[: -len(".log")] if path.name.endswith(".log") else path.name
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 14:
        return parts[1]
    return path.name


def _enforce_named_log_retention(directory: Path, basename: str) -> None:
    settings = load_agent_log_settings()
    plain = [
        path
        for path in directory.glob(f"{basename}_*.log")
        if path.is_file() and _rotated_sort_key(path).isdigit()
    ]
    enforce_named_retention(
        plain,
        keep_count=settings.keep_count,
        archive_keep_count=settings.archive_keep_count,
        plain_sort_key=_rotated_sort_key,
        archive_glob=f"{basename}_*.log.gz",
        directories=[directory],
    )


def maybe_rotate_named_log(log_path: Path, *, basename: str) -> None:
    """Daily-rotate ``basename.log`` beside itself under the same directory."""
    directory = log_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    lock_key = str(log_path.resolve()) if log_path.exists() else str(log_path)
    with _get_file_lock(lock_key):
        if log_path.is_file() and log_path.stat().st_size > 0:
            today = now_display_datetime().date()
            try:
                file_date = _file_local_date(log_path)
            except OSError:
                file_date = today
            if file_date < today:
                stamp = now_display_datetime().strftime("%Y%m%d%H%M%S")
                rotated = directory / f"{basename}_{stamp}.log"
                if rotated.exists():
                    time.sleep(1.05)
                    stamp = now_display_datetime().strftime("%Y%m%d%H%M%S")
                    rotated = directory / f"{basename}_{stamp}.log"
                try:
                    log_path.rename(rotated)
                except OSError as exc:
                    logger.warning("Failed to rotate workflow log %s: %s", log_path, exc)
        _enforce_named_log_retention(directory, basename)


def _append_jsonl(log_path: Path, entry: dict[str, Any], *, basename: str) -> None:
    maybe_rotate_named_log(log_path, basename=basename)
    line = json.dumps(entry, ensure_ascii=False)
    try:
        with _get_file_lock(str(log_path)):
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as file:
                file.write(f"{line}\n")
    except OSError as exc:
        logger.error("Failed to write workflow log %s: %s", log_path, exc)


def log_workflow_agent_interaction(
    *,
    userid: str,
    workflow_key: str,
    agent_id: str,
    input_message: str,
    output_message: str,
    tools_used: list[ToolUsage] | None = None,
    user_name: str | None = None,
) -> None:
    """Append WORKFLOW_AGENT chat to ``.../{workflow_key}/workflow.log``."""
    global _last_cleanup_date
    try:
        path = workflow_agent_log_path(userid, workflow_key)
    except ValueError as exc:
        logger.warning("Skipped workflow agent log: %s", exc)
        return

    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "kind": "workflow",
        "agent_id": agent_id,
        "user_id": userid.strip(),
        "workflow_key": workflow_key.strip(),
        "input_message": input_message,
        "output_message": output_message,
        "tools": _serialize_tools(tools_used),
    }
    name = (user_name or "").strip()
    if name:
        entry["user_name"] = name
    _append_jsonl(path, entry, basename="workflow")

    today = now_display_datetime().date()
    if _last_cleanup_date != today:
        initialize_workflow_logs()
        _last_cleanup_date = today


def log_work_node_agent_interaction(
    *,
    userid: str,
    work_uuid: str,
    agent_id: str,
    input_message: str,
    output_message: str,
    tools_used: list[ToolUsage] | None = None,
    workflow_uuid: str | None = None,
    user_name: str | None = None,
    event: str | None = None,
    fail_reason: str | None = None,
    status: str | None = None,
) -> None:
    """Append work_node runtime agent chat to ``.../{work_uuid}/work_node.log``."""
    try:
        path = work_node_agent_log_path(userid, work_uuid)
    except ValueError as exc:
        logger.warning("Skipped work_node agent log: %s", exc)
        return

    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "kind": "work_node",
        "agent_id": (agent_id or "").strip(),
        "user_id": userid.strip(),
        "work_uuid": work_uuid.strip(),
        "input_message": input_message,
        "output_message": output_message,
        "tools": _serialize_tools(tools_used),
    }
    wf = (workflow_uuid or "").strip()
    if wf:
        entry["workflow_uuid"] = wf
    name = (user_name or "").strip()
    if name:
        entry["user_name"] = name
    event_name = (event or "").strip()
    if event_name:
        entry["event"] = event_name
    reason = (fail_reason or "").strip()
    if reason:
        entry["fail_reason"] = reason
    status_name = (status or "").strip()
    if status_name:
        entry["status"] = status_name
    _append_jsonl(path, entry, basename="work_node")


def read_work_node_agent_log(userid: str, work_uuid: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """Read active + rotated plain ``work_node`` JSONL entries (newest last)."""
    try:
        active = work_node_agent_log_path(userid, work_uuid)
    except ValueError:
        return []
    directory = active.parent
    if not directory.is_dir():
        return []

    paths = sorted(
        [path for path in directory.glob("work_node_*.log") if path.is_file()],
        key=_rotated_sort_key,
    )
    if active.is_file():
        paths.append(active)

    entries: list[dict[str, Any]] = []
    for path in paths:
        try:
            with path.open(encoding="utf-8") as file:
                for line in file:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        payload = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        entries.append(payload)
        except OSError as exc:
            logger.warning("Failed to read work_node log %s: %s", path, exc)

    if limit > 0 and len(entries) > limit:
        return entries[-limit:]
    return entries


def initialize_workflow_logs() -> Path:
    """Ensure root exists and enforce retention on known log trees."""
    ensure_workflow_logs_dir()
    if not WORKFLOW_LOGS_DIR.is_dir():
        return WORKFLOW_LOGS_DIR
    for user_dir in WORKFLOW_LOGS_DIR.iterdir():
        if not user_dir.is_dir():
            continue
        for scope_dir in user_dir.iterdir():
            if not scope_dir.is_dir():
                continue
            if (scope_dir / "workflow.log").exists() or list(scope_dir.glob("workflow_*.log")):
                maybe_rotate_named_log(scope_dir / "workflow.log", basename="workflow")
                _enforce_named_log_retention(scope_dir, "workflow")
            if (scope_dir / "work_node.log").exists() or list(scope_dir.glob("work_node_*.log")):
                maybe_rotate_named_log(scope_dir / "work_node.log", basename="work_node")
                _enforce_named_log_retention(scope_dir, "work_node")
    return WORKFLOW_LOGS_DIR
