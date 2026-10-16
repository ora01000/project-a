"""Process-wide backend logging (stdout or file) for crashloop / startup debugging."""

from __future__ import annotations

import logging
import os
import re
import socket
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.app.config import PROJECT_ROOT, BackendLogSettings, load_backend_log_settings

# Below DEBUG; not always present in stdlib.
TRACE_LEVEL = 5
if not hasattr(logging, "TRACE"):
    logging.addLevelName(TRACE_LEVEL, "TRACE")

    def _trace(self: logging.Logger, message: object, *args: object, **kwargs: object) -> None:
        if self.isEnabledFor(TRACE_LEVEL):
            self._log(TRACE_LEVEL, message, args, **kwargs)

    logging.Logger.trace = _trace  # type: ignore[attr-defined]

_LEVEL_MAP: dict[str, int] = {
    "trace": TRACE_LEVEL,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "fatal": logging.CRITICAL,
}

_CONFIGURED = False


def resolve_log_level(name: str) -> int:
    key = (name or "error").strip().lower()
    return _LEVEL_MAP.get(key, logging.ERROR)


def resolve_pod_name() -> str:
    """Pod/hostname identity for log file naming.

    Prefer ``POD_NAME`` (Downward API), then ``HOSTNAME`` (K8s default = pod name),
    then ``socket.gethostname()``.
    """
    for key in ("POD_NAME", "HOSTNAME"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return (socket.gethostname() or "unknown").strip() or "unknown"


_PATH_PLACEHOLDER_RE = re.compile(
    r"\{(pod_name|pod|hostname|POD_NAME|HOSTNAME)\}|\$\{(POD_NAME|HOSTNAME)\}|\$\((POD_NAME|HOSTNAME)\)"
)


def expand_backend_log_path_template(path_value: str, *, pod_name: str | None = None) -> str:
    """Expand pod placeholders in BACKEND_LOG_PATH.

    Supported tokens: ``{pod_name}``, ``{pod}``, ``{hostname}``,
    ``${POD_NAME}``, ``$(POD_NAME)``, ``${HOSTNAME}``, ``$(HOSTNAME)``.
    """
    identity = (pod_name or resolve_pod_name()).strip() or "unknown"
    # Sanitize for filesystem safety (K8s names are usually already safe).
    safe = re.sub(r"[^\w.\-]+", "_", identity)

    def _replace(match: re.Match[str]) -> str:
        return safe

    return _PATH_PLACEHOLDER_RE.sub(_replace, path_value)


def resolve_backend_log_path(path_value: str) -> Path:
    raw = (path_value or "").strip() or "logs/backend/backend.log"
    raw = expand_backend_log_path_template(raw)
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def configure_backend_logging(settings: BackendLogSettings | None = None) -> BackendLogSettings:
    """Configure root + uvicorn loggers. Safe to call more than once (idempotent)."""
    global _CONFIGURED
    cfg = settings or load_backend_log_settings()
    level = resolve_log_level(cfg.level)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handlers: list[logging.Handler] = []
    destination = (cfg.enabled or "stdout").strip().lower()
    if destination == "file":
        log_path = resolve_backend_log_path(cfg.path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=20 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
        # Keep a stderr mirror so OKD `oc logs` still shows fatal startup lines.
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(max(level, logging.WARNING))
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)
    else:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    root = logging.getLogger()
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)

    def _excepthook(exc_type, exc, tb) -> None:  # noqa: ANN001
        logging.getLogger("backend.uncaught").critical(
            "Uncaught exception",
            exc_info=(exc_type, exc, tb),
        )

    sys.excepthook = _excepthook

    _CONFIGURED = True
    logging.getLogger(__name__).info(
        "backend logging configured enabled=%s level=%s path=%s",
        destination,
        (cfg.level or "error").strip().lower(),
        resolve_backend_log_path(cfg.path) if destination == "file" else "-",
    )
    return cfg
