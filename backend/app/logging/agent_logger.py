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
from backend.app.logging.log_retention import (
    enforce_named_retention,
    list_rotated_agent_logs,
    parse_agent_id_from_log_name,
    rotated_agent_log_sort_key,
)
from backend.app.services.whatap_constants import (
    WHATAP_EVENT_LOG_SOURCE,
    WHATAP_LOG_AGENT_IDS,
    is_whatap_log_agent_id,
)
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

logger = logging.getLogger(__name__)

AGENT_LOGS_DIR = PROJECT_ROOT / "logs" / "agents"
_ROTATED_SUFFIX_RE = re.compile(r"_\d{14}\.log$")

_file_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_last_rotation_cleanup_date = None


def ensure_agent_logs_dir() -> None:
    AGENT_LOGS_DIR.mkdir(parents=True, exist_ok=True)


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


def _active_log_path(agent_id: str) -> Path:
    return AGENT_LOGS_DIR / f"{agent_id}.log"


def _file_local_date(path: Path):
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=DISPLAY_TIMEZONE)
    return mtime.date()


def enforce_agent_log_retention(agent_id: str | None = None) -> None:
    """Apply keep/archive policy for one agent or every rotated agent log set."""
    ensure_agent_logs_dir()
    settings = load_agent_log_settings()
    agent_ids: set[str] = set()
    if agent_id:
        agent_ids.add(agent_id.strip())
    else:
        for path in AGENT_LOGS_DIR.glob("*.log"):
            if path.is_file():
                agent_ids.add(parse_agent_id_from_log_name(path))
        for path in AGENT_LOGS_DIR.glob("*.log.gz"):
            # AGENT_stamp.log.gz → stem is AGENT_stamp.log
            plain = Path(str(path)[: -len(".gz")])
            agent_ids.add(parse_agent_id_from_log_name(plain))

    for aid in sorted(a for a in agent_ids if a):
        rotated = list_rotated_agent_logs(AGENT_LOGS_DIR, aid)
        if not rotated and not list(AGENT_LOGS_DIR.glob(f"{aid}_*.log.gz")):
            continue
        enforce_named_retention(
            rotated,
            keep_count=settings.keep_count,
            archive_keep_count=settings.archive_keep_count,
            plain_sort_key=rotated_agent_log_sort_key,
            archive_glob=f"{aid}_*.log.gz",
            directories=[AGENT_LOGS_DIR],
        )


def maybe_rotate_agent_log(agent_id: str) -> None:
    """Rotate ``{agent}.log`` once per calendar day (display timezone)."""
    global _last_rotation_cleanup_date

    ensure_agent_logs_dir()
    normalized = (agent_id or "").strip()
    if not normalized:
        return

    log_path = _active_log_path(normalized)
    with _get_file_lock(normalized):
        if log_path.is_file() and log_path.stat().st_size > 0:
            today = now_display_datetime().date()
            try:
                file_date = _file_local_date(log_path)
            except OSError:
                file_date = today
            if file_date < today:
                stamp = now_display_datetime().strftime("%Y%m%d%H%M%S")
                rotated = AGENT_LOGS_DIR / f"{normalized}_{stamp}.log"
                if rotated.exists():
                    time.sleep(1.05)
                    stamp = now_display_datetime().strftime("%Y%m%d%H%M%S")
                    rotated = AGENT_LOGS_DIR / f"{normalized}_{stamp}.log"
                try:
                    log_path.rename(rotated)
                except OSError as exc:
                    logger.warning("Failed to rotate agent log %s: %s", log_path, exc)

        enforce_agent_log_retention(normalized)

    today = now_display_datetime().date()
    if _last_rotation_cleanup_date != today:
        enforce_agent_log_retention(None)
        _last_rotation_cleanup_date = today


def initialize_agent_logs() -> Path:
    ensure_agent_logs_dir()
    for path in list(AGENT_LOGS_DIR.glob("*.log")):
        if not path.is_file():
            continue
        if _ROTATED_SUFFIX_RE.search(path.name):
            continue
        maybe_rotate_agent_log(path.stem)
    enforce_agent_log_retention(None)
    return AGENT_LOGS_DIR


def log_agent_interaction(
    agent_id: str,
    input_message: str,
    output_message: str,
    tools_used: list[ToolUsage],
    *,
    user_id: str | None = None,
    user_name: str | None = None,
) -> None:
    normalized_agent = (agent_id or "").strip()
    if not normalized_agent:
        return
    maybe_rotate_agent_log(normalized_agent)

    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": normalized_agent,
        "input_message": input_message,
        "output_message": output_message,
        "tools": _serialize_tools(tools_used),
    }
    normalized_user_id = (user_id or "").strip()
    normalized_user_name = (user_name or "").strip()
    if normalized_user_id:
        entry["user_id"] = normalized_user_id
    if normalized_user_name:
        entry["user_name"] = normalized_user_name

    log_path = _active_log_path(normalized_agent)
    line = json.dumps(entry, ensure_ascii=False)

    try:
        with _get_file_lock(normalized_agent):
            with log_path.open("a", encoding="utf-8") as file:
                file.write(f"{line}\n")
    except OSError as exc:
        logger.error("Failed to write agent log for %s: %s", normalized_agent, exc)


def log_agent_error(
    agent_id: str,
    *,
    reason: str,
    input_message: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
) -> None:
    normalized_agent = (agent_id or "").strip()
    if not normalized_agent:
        return
    maybe_rotate_agent_log(normalized_agent)

    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": normalized_agent,
        "event": "agent_operation_error",
        "reason": reason,
    }
    if input_message is not None:
        entry["input_message"] = input_message
    normalized_user_id = (user_id or "").strip()
    normalized_user_name = (user_name or "").strip()
    if normalized_user_id:
        entry["user_id"] = normalized_user_id
    if normalized_user_name:
        entry["user_name"] = normalized_user_name

    log_path = _active_log_path(normalized_agent)
    line = json.dumps(entry, ensure_ascii=False)

    try:
        with _get_file_lock(normalized_agent):
            with log_path.open("a", encoding="utf-8") as file:
                file.write(f"{line}\n")
    except OSError as exc:
        logger.error("Failed to write agent error log for %s: %s", normalized_agent, exc)


def list_all_agent_logs(
    limit: int | None = None,
    *,
    viewer_user_id: str | None = None,
    admin_view: bool = False,
    agent_id: str | None = None,
    exclude_agent_ids: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    ensure_agent_logs_dir()
    entries: list[dict[str, Any]] = []

    for log_path in sorted(AGENT_LOGS_DIR.glob("*.log")):
        if not log_path.is_file():
            continue
        file_agent_id = parse_agent_id_from_log_name(log_path)
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
                        entry["agent_id"] = file_agent_id
                    entries.append(entry)
        except OSError as exc:
            logger.warning("Failed to read agent log %s: %s", log_path, exc)

    normalized_agent_id = (agent_id or "").strip() or None
    if normalized_agent_id:
        if normalized_agent_id == WHATAP_EVENT_LOG_SOURCE:
            entries = [
                entry
                for entry in entries
                if is_whatap_log_agent_id(str(entry.get("agent_id") or ""))
            ]
        else:
            entries = [
                entry
                for entry in entries
                if str(entry.get("agent_id") or "").strip() == normalized_agent_id
            ]

    if exclude_agent_ids:
        expanded_exclude = set(exclude_agent_ids)
        if WHATAP_EVENT_LOG_SOURCE in expanded_exclude:
            expanded_exclude |= set(WHATAP_LOG_AGENT_IDS)
        entries = [
            entry
            for entry in entries
            if str(entry.get("agent_id") or "").strip() not in expanded_exclude
        ]

    if not admin_view:
        if normalized_agent_id == WHATAP_EVENT_LOG_SOURCE:
            pass
        else:
            normalized_viewer = (viewer_user_id or "").strip()
            if normalized_viewer:
                entries = [
                    entry
                    for entry in entries
                    if str(entry.get("user_id") or "").strip() == normalized_viewer
                ]
            else:
                entries = []

    entries.sort(key=lambda entry: str(entry.get("timestamp", "")), reverse=True)
    if limit is not None and limit > 0:
        return entries[:limit]
    return entries
