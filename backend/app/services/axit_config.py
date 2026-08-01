"""AXIT platform URL and credential resolution from environment."""

from __future__ import annotations

from backend.app.config import (
    _env_setting,
    load_settings,
    resolve_agent_runtime_mode,
    resolve_control_plane_base_url,
)
from backend.app.services.agent_runtime_client import normalize_runtime_mode

AXIT_TOKEN_PATH = "/portal/auths/v1/token"
AXIT_AGENT_PATH = "/aihub/agents/v1"

AXIT_HTTP_TOKEN_URL = f"https://test.nudp.lguplus.co.kr{AXIT_TOKEN_PATH}"
AXIT_HTTP_AGENT_URL = f"https://test.nudp.lguplus.co.kr{AXIT_AGENT_PATH}"

AXIT_MOCK_CLIENT_ID = "mock-client-id"
AXIT_MOCK_CLIENT_SECRET = "mock-client-secret"

AXIT_HTTP_CLIENT_ID = "4afb927e-74fe-400f-81d6-c01c369757ae"
AXIT_HTTP_CLIENT_SECRET = "23pXFlLdy5LhYbHbJvBZcDe5P84EXVmZPjxzI-hEwX8"

AXIT_DEFAULT_SERVICE_ID = "prvops"
AXIT_ACCESS_TOKEN_TTL_SECONDS = 3600


def _resolved_mode(runtime_mode: str | None = None) -> str:
    if runtime_mode is not None:
        return normalize_runtime_mode(runtime_mode)
    return normalize_runtime_mode(resolve_agent_runtime_mode())


def resolve_axit_token_url(*, runtime_mode: str | None = None) -> str:
    explicit = _env_setting("TOKEN_URL") or _env_setting("AXIT_TOKEN_URL")
    if explicit:
        return explicit.rstrip("/")
    if _resolved_mode(runtime_mode) == "http":
        return AXIT_HTTP_TOKEN_URL
    _, server_settings, _, _ = load_settings()
    base_url = resolve_control_plane_base_url(server_settings)
    return f"{base_url.rstrip('/')}{AXIT_TOKEN_PATH}"


def resolve_axit_agent_url(*, runtime_mode: str | None = None) -> str:
    explicit = _env_setting("AGENT_URL") or _env_setting("AXIT_AGENT_URL")
    if explicit:
        return explicit.rstrip("/")
    if _resolved_mode(runtime_mode) == "http":
        return AXIT_HTTP_AGENT_URL
    _, server_settings, _, _ = load_settings()
    base_url = resolve_control_plane_base_url(server_settings)
    return f"{base_url.rstrip('/')}{AXIT_AGENT_PATH}"


def resolve_axit_client_id(*, runtime_mode: str | None = None) -> str:
    explicit = _env_setting("CLIENT_ID") or _env_setting("AXIT_CLIENT_ID")
    if explicit:
        return explicit
    if _resolved_mode(runtime_mode) == "http":
        return AXIT_HTTP_CLIENT_ID
    return AXIT_MOCK_CLIENT_ID


def resolve_axit_client_secret(*, runtime_mode: str | None = None) -> str:
    explicit = _env_setting("CLIENT_SECRET") or _env_setting("AXIT_CLIENT_SECRET")
    if explicit:
        return explicit
    if _resolved_mode(runtime_mode) == "http":
        return AXIT_HTTP_CLIENT_SECRET
    return AXIT_MOCK_CLIENT_SECRET


def resolve_axit_service_id() -> str:
    return (
        _env_setting("SERVICE_ID")
        or _env_setting("AXIT_SERVICE_ID")
        or AXIT_DEFAULT_SERVICE_ID
    )


def resolve_axit_credential_source() -> str:
    if _env_setting("CLIENT_ID") or _env_setting("AXIT_CLIENT_ID"):
        return "env"
    return "default"
