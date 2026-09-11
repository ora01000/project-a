"""Plain-file keep + gzip archive retention for agent / user-comm logs."""

from __future__ import annotations

import gzip
import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_ROTATED_AGENT_LOG_RE = re.compile(r"^(?P<agent>.+)_(?P<stamp>\d{14})\.log$")
_DATE_JSON_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
_DATE_JSON_GZ_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json\.gz$")


def parse_agent_id_from_log_name(path: Path) -> str:
    """Return agent_id from ``AGENT.log`` or ``AGENT_YYYYMMDDHHMISS.log``."""
    match = _ROTATED_AGENT_LOG_RE.match(path.name)
    if match:
        return match.group("agent")
    if path.suffix == ".log":
        return path.stem
    return path.stem


def gzip_replace(path: Path) -> Path | None:
    """Compress ``path`` to ``path.gz`` and remove the original. Return gz path."""
    if not path.is_file():
        return None
    dest = Path(f"{path}.gz")
    if dest.exists():
        try:
            dest.unlink()
        except OSError as exc:
            logger.warning("Failed to replace existing archive %s: %s", dest, exc)
            return None
    try:
        with path.open("rb") as src, gzip.open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        path.unlink()
    except OSError as exc:
        logger.warning("Failed to gzip %s: %s", path, exc)
        return None
    return dest


def enforce_named_retention(
    plain_files: list[Path],
    *,
    keep_count: int,
    archive_keep_count: int,
    plain_sort_key,
    archive_glob: str,
    directories: list[Path] | None = None,
) -> None:
    """Keep newest ``keep_count`` plain files; gzip the rest; keep newest archives."""
    keep = max(0, int(keep_count))
    archive_keep = max(0, int(archive_keep_count))

    plains = sorted(
        [path for path in plain_files if path.is_file()],
        key=plain_sort_key,
        reverse=True,
    )
    for path in plains[keep:]:
        gzip_replace(path)

    parents = {path.parent for path in plain_files}
    if directories:
        parents.update(directories)
    archives: list[Path] = []
    for directory in parents:
        if not directory.is_dir():
            continue
        archives.extend(path for path in directory.glob(archive_glob) if path.is_file())

    def archive_key(path: Path):
        plain_name = path.name[: -len(".gz")] if path.name.endswith(".gz") else path.name
        return plain_sort_key(path.parent / plain_name)

    archives = sorted(archives, key=archive_key, reverse=True)
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in archives:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)

    for path in deduped[archive_keep:]:
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove old archive %s: %s", path, exc)


def rotated_agent_log_sort_key(path: Path) -> str:
    match = _ROTATED_AGENT_LOG_RE.match(path.name)
    if match:
        return match.group("stamp")
    return path.name


def list_rotated_agent_logs(directory: Path, agent_id: str) -> list[Path]:
    found: list[Path] = []
    for path in directory.glob(f"{agent_id}_*.log"):
        if not path.is_file():
            continue
        match = _ROTATED_AGENT_LOG_RE.match(path.name)
        if match and match.group("agent") == agent_id:
            found.append(path)
    return found


def is_date_json_name(name: str) -> bool:
    return bool(_DATE_JSON_RE.match(name))


def is_date_json_gz_name(name: str) -> bool:
    return bool(_DATE_JSON_GZ_RE.match(name))


def date_json_sort_key(path: Path) -> str:
    """Sort key for ``YYYY-MM-DD.json`` / ``YYYY-MM-DD.json.gz``."""
    name = path.name
    if name.endswith(".json.gz"):
        return name[: -len(".json.gz")]
    if name.endswith(".json"):
        return name[: -len(".json")]
    return name
