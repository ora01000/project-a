from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
ENV_FILE = PROJECT_ROOT / ".env"


class LLMSettings(BaseModel):
    base_url: str = "http://localhost:8001/v1"
    api_key: str = "not-needed"
    model: str = "./llm_model/qwen3-4b-4bit-mlx"
    max_context_tokens: int = 32768


class ServerSettings(BaseModel):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    frontend_host: str = "0.0.0.0"
    frontend_port: int = 9001
    backend_api_host: str = "localhost"
    backend_api_port: int = 8080
    health_check_interval_seconds: int = 30
    agent_runtime_mode: str = "mock"
    agent_runtime_http_base_url: str = ""
    agent_runtime_http_timeout_seconds: float = 3600.0
    agent_runtime_api_key: str = ""
    control_plane_base_url: str = ""


class MCPServerConfig(BaseModel):
    transport: str = "streamable_http"
    url: str
    enabled: bool = True


class EmailNotificationSettings(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    from_address: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 30.0


class TeamsNotificationSettings(BaseModel):
    enabled: bool = False
    mode: str = "webhook"
    webhook_url: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    team_id: str = ""
    channel_id: str = ""
    timeout_seconds: float = 30.0


class NotificationSettings(BaseModel):
    email: EmailNotificationSettings = Field(default_factory=EmailNotificationSettings)
    teams: TeamsNotificationSettings = Field(default_factory=TeamsNotificationSettings)


class WhatapSettings(BaseModel):
    webhook_secret: str = ""


class UserCommLogSettings(BaseModel):
    log_dir: str = "data/user_comm_logs"
    retention_days: int = 30


class JobRequesterSettings(BaseModel):
    enabled: bool = True
    interval_minutes: int = 60
    initial_delay_seconds: int = 60


class JobProcessorSettings(BaseModel):
    enabled: bool = True
    poll_interval_seconds: int = 60
    initial_delay_seconds: int = 0
    # http 모드: agentruntime.local_agent_id (기본 helpdesk, 대안 sys-helpdesk)
    helpdesk_local_agent_id: str = "helpdesk"
    # http 모드: AXIT agent_id 직접 지정 시 local_agent_id 조회 생략
    helpdesk_axit_agent_id: str = ""


class JobAuditorSettings(BaseModel):
    # http 모드: agentruntime.local_agent_id (기본 JOB_AUDITOR_AGENT)
    local_agent_id: str = "JOB_AUDITOR_AGENT"
    # http 모드: AXIT agent_id 직접 지정 (선택)
    axit_agent_id: str = ""


class MyNotesSettings(BaseModel):
    enabled: bool = True
    flush_interval_seconds: int = 300
    initial_delay_seconds: int = 0


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_base_url: str = Field(default="http://localhost:8001/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="not-needed", alias="LLM_API_KEY")
    llm_model: str = Field(default="./llm_model/qwen3-4b-4bit-mlx", alias="LLM_MODEL")
    llm_max_context_tokens: int = Field(default=32768, alias="LLM_MAX_CONTEXT_TOKENS")
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8080, alias="BACKEND_PORT")
    frontend_host: str = Field(default="0.0.0.0", alias="FRONTEND_HOST")
    frontend_port: int = Field(default=9001, alias="FRONTEND_PORT")
    backend_api_host: str = Field(default="localhost", alias="BACKEND_API_HOST")
    backend_api_port: int | None = Field(default=None, alias="BACKEND_API_PORT")
    database_path: str = Field(default="data/app.db", alias="DATABASE_PATH")
    health_check_interval_seconds: int = Field(default=30, alias="HEALTH_CHECK_INTERVAL_SECONDS")
    agent_runtime_mode: str = Field(default="mock", alias="AGENT_RUNTIME_MODE")
    agent_runtime_http_base_url: str = Field(default="", alias="AGENT_RUNTIME_HTTP_BASE_URL")
    agent_runtime_http_timeout_seconds: float = Field(
        default=300.0,
        alias="AGENT_RUNTIME_HTTP_TIMEOUT_SECONDS",
    )
    agent_runtime_api_key: str = Field(default="", alias="AGENT_RUNTIME_API_KEY")
    control_plane_base_url: str = Field(default="", alias="CONTROL_PLANE_BASE_URL")
    agent_runtime_host: str = Field(default="0.0.0.0", alias="AGENT_RUNTIME_HOST")
    agent_runtime_port: int = Field(default=8090, alias="AGENT_RUNTIME_PORT")

    email_enabled: bool = Field(default=False, alias="EMAIL_ENABLED")
    email_smtp_host: str = Field(default="", alias="EMAIL_SMTP_HOST")
    email_smtp_port: int = Field(default=587, alias="EMAIL_SMTP_PORT")
    email_smtp_username: str = Field(default="", alias="EMAIL_SMTP_USERNAME")
    email_smtp_password: str = Field(default="", alias="EMAIL_SMTP_PASSWORD")
    email_from_address: str = Field(default="", alias="EMAIL_FROM_ADDRESS")
    email_use_tls: bool = Field(default=True, alias="EMAIL_USE_TLS")
    email_use_ssl: bool = Field(default=False, alias="EMAIL_USE_SSL")
    email_timeout_seconds: float = Field(default=30.0, alias="EMAIL_TIMEOUT_SECONDS")

    teams_enabled: bool = Field(default=False, alias="TEAMS_ENABLED")
    teams_mode: str = Field(default="webhook", alias="TEAMS_MODE")
    teams_webhook_url: str = Field(default="", alias="TEAMS_WEBHOOK_URL")
    teams_tenant_id: str = Field(default="", alias="TEAMS_TENANT_ID")
    teams_client_id: str = Field(default="", alias="TEAMS_CLIENT_ID")
    teams_client_secret: str = Field(default="", alias="TEAMS_CLIENT_SECRET")
    teams_team_id: str = Field(default="", alias="TEAMS_TEAM_ID")
    teams_channel_id: str = Field(default="", alias="TEAMS_CHANNEL_ID")
    teams_timeout_seconds: float = Field(default=30.0, alias="TEAMS_TIMEOUT_SECONDS")

    whatap_webhook_secret: str = Field(default="", alias="WHATAP_WEBHOOK_SECRET")

    user_comm_log: str = Field(default="data/user_comm_logs", alias="USER_COMM_LOG")
    user_comm_retention: int = Field(default=30, alias="USER_COMM_RETENTION")

    job_requester_enabled: bool | None = Field(default=None, alias="JOB_REQUESTER_ENABLED")
    job_requester_interval_minutes: int | None = Field(default=None, alias="JOB_REQUESTER_INTERVAL_MINUTES")
    job_requester_initial_delay_seconds: int | None = Field(
        default=None,
        alias="JOB_REQUESTER_INITIAL_DELAY_SECONDS",
    )

    job_processor_enabled: bool | None = Field(default=None, alias="JOB_PROCESSOR_ENABLED")
    job_processor_poll_interval_seconds: int | None = Field(
        default=None,
        alias="JOB_PROCESSOR_POLL_INTERVAL_SECONDS",
    )
    job_processor_initial_delay_seconds: int | None = Field(
        default=None,
        alias="JOB_PROCESSOR_INITIAL_DELAY_SECONDS",
    )
    job_processor_helpdesk_local_agent_id: str | None = Field(
        default=None,
        alias="JOB_PROCESSOR_HELPDESK_LOCAL_AGENT_ID",
    )
    job_processor_helpdesk_axit_agent_id: str | None = Field(
        default=None,
        alias="JOB_PROCESSOR_HELPDESK_AXIT_AGENT_ID",
    )
    job_auditor_local_agent_id: str | None = Field(
        default=None,
        alias="JOB_AUDITOR_LOCAL_AGENT_ID",
    )
    job_auditor_axit_agent_id: str | None = Field(
        default=None,
        alias="JOB_AUDITOR_AXIT_AGENT_ID",
    )

    mynotes_flush_enabled: bool | None = Field(default=None, alias="MY_NOTES_FLUSH_ENABLED")
    mynotes_flush_interval_seconds: int | None = Field(
        default=None,
        alias="MY_NOTES_FLUSH_INTERVAL_SECONDS",
    )
    mynotes_flush_initial_delay_seconds: int | None = Field(
        default=None,
        alias="MY_NOTES_FLUSH_INITIAL_DELAY_SECONDS",
    )

    auth_provider_type: str = Field(default="db", alias="AUTH_PROVIDER_TYPE")
    oauth_proxy: str = Field(default="", alias="OAUTH_PROXY")
    oauth_url: str = Field(default="", alias="OAUTH_URL")
    oauth_client_id: str = Field(default="", alias="OAUTH_CLIENT_ID")
    oauth_client_secret: str = Field(default="", alias="OAUTH_CLIENT_SECRET")
    oauth_grant_type: str = Field(default="password", alias="OAUTH_GRANT_TYPE")
    oauth_scope: str = Field(default="EA", alias="OAUTH_SCOPE")
    oauth_auth_type: str = Field(default="IM", alias="OAUTH_AUTH_TYPE")
    oauth_verify_ssl: bool | None = Field(default=None, alias="OAUTH_VERIFY_SSL")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    auth_session_ttl_seconds: int | None = Field(default=None, alias="AUTH_SESSION_TTL_SECONDS")
    auth_session_absolute_max_seconds: int | None = Field(
        default=None,
        alias="AUTH_SESSION_ABSOLUTE_MAX_SECONDS",
    )

    @field_validator("backend_port", mode="before")
    @classmethod
    def _normalize_backend_port(cls, value: object) -> int:
        explicit = _merged_env().get("BACKEND_LISTEN_PORT", "").strip()
        if explicit:
            return parse_listen_port(explicit, default=8080)
        return parse_listen_port(value, default=8080)

    @field_validator("frontend_port", mode="before")
    @classmethod
    def _normalize_frontend_port(cls, value: object) -> int:
        explicit = _merged_env().get("FRONTEND_LISTEN_PORT", "").strip()
        if explicit:
            return parse_listen_port(explicit, default=9001)
        return parse_listen_port(value, default=9001)

    @field_validator("agent_runtime_port", mode="before")
    @classmethod
    def _normalize_agent_runtime_port(cls, value: object) -> int:
        explicit = _merged_env().get("AGENT_RUNTIME_LISTEN_PORT", "").strip()
        if explicit:
            return parse_listen_port(explicit, default=8090)
        return parse_listen_port(value, default=8090)

    @field_validator("backend_api_port", mode="before")
    @classmethod
    def _normalize_backend_api_port(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        explicit = _merged_env().get("BACKEND_API_LISTEN_PORT", "").strip()
        if explicit:
            return parse_listen_port(explicit, default=8080)
        return parse_listen_port(value, default=8080)


def _merged_env() -> dict[str, str]:
    import os

    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for key, value in dotenv_values(ENV_FILE).items():
            if value is not None:
                values[key] = value
    values.update(os.environ)
    return values


def _env_setting(name: str, *, default: str = "") -> str:
    return _merged_env().get(name, default).strip()


def parse_listen_port(raw: object | None, *, default: int) -> int:
    """Parse a listen port from int, plain string, or Kubernetes service-link URL (tcp://host:port)."""
    if raw is None:
        return default
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if not text:
        return default
    if text.startswith("tcp://"):
        host_port = text[6:]
        if ":" in host_port:
            port_text = host_port.rsplit(":", 1)[-1]
            try:
                return int(port_text)
            except ValueError:
                return default
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def resolve_backend_listen_port(
    *,
    env_settings: AppSettings | None = None,
    server_yaml: dict[str, Any] | None = None,
) -> int:
    explicit = _env_setting("BACKEND_LISTEN_PORT")
    if explicit:
        return parse_listen_port(explicit, default=8080)
    merged = _merged_env().get("BACKEND_PORT", "")
    if merged:
        return parse_listen_port(merged, default=8080)
    if env_settings is not None:
        return parse_listen_port(env_settings.backend_port, default=8080)
    yaml = server_yaml or {}
    return parse_listen_port(yaml.get("backend_port"), default=8080)


def resolve_agent_runtime_mode(
    *,
    env_settings: AppSettings | None = None,
    server_yaml: dict[str, Any] | None = None,
) -> str:
    """Resolve runtime mode from AGENT_RUNTIME_MODE (env/.env) with yaml fallback."""
    explicit = _env_setting("AGENT_RUNTIME_MODE")
    if explicit:
        return explicit
    settings = env_settings or AppSettings()
    if settings.agent_runtime_mode:
        return settings.agent_runtime_mode
    yaml = server_yaml or {}
    return str(yaml.get("agent_runtime_mode") or "mock")


def _mcp_server_key_from_env_suffix(suffix: str) -> str:
    return suffix.lower()


def _apply_mcp_env_overrides(mcp_servers: dict[str, MCPServerConfig]) -> dict[str, MCPServerConfig]:
    updated = {key: config.model_copy() for key, config in mcp_servers.items()}

    for env_key, raw_value in _merged_env().items():
        if not env_key.startswith("MCP_"):
            continue

        if env_key.endswith("_URL"):
            server_key = _mcp_server_key_from_env_suffix(env_key.removeprefix("MCP_").removesuffix("_URL"))
            url = raw_value.strip()
            if not url or server_key not in updated:
                continue
            updated[server_key] = updated[server_key].model_copy(update={"url": url})
            continue

        if env_key.endswith("_ENABLED"):
            server_key = _mcp_server_key_from_env_suffix(env_key.removeprefix("MCP_").removesuffix("_ENABLED"))
            enabled = raw_value.strip().lower() in {"1", "true", "yes", "on"}
            if server_key not in updated:
                continue
            updated[server_key] = updated[server_key].model_copy(update={"enabled": enabled})

    return updated


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_notification_settings() -> NotificationSettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    notify_yaml = yaml_settings.get("notifications", {})
    email_yaml = notify_yaml.get("email", {})
    teams_yaml = notify_yaml.get("teams", {})
    env_settings = AppSettings()

    email = EmailNotificationSettings(
        enabled=_as_bool(env_settings.email_enabled, email_yaml.get("enabled", False)),
        smtp_host=env_settings.email_smtp_host or email_yaml.get("smtp_host", ""),
        smtp_port=env_settings.email_smtp_port or email_yaml.get("smtp_port", 587),
        smtp_username=env_settings.email_smtp_username or email_yaml.get("smtp_username", ""),
        smtp_password=env_settings.email_smtp_password or email_yaml.get("smtp_password", ""),
        from_address=env_settings.email_from_address or email_yaml.get("from_address", ""),
        use_tls=_as_bool(env_settings.email_use_tls, email_yaml.get("use_tls", True)),
        use_ssl=_as_bool(env_settings.email_use_ssl, email_yaml.get("use_ssl", False)),
        timeout_seconds=env_settings.email_timeout_seconds or email_yaml.get("timeout_seconds", 30.0),
    )
    teams = TeamsNotificationSettings(
        enabled=_as_bool(env_settings.teams_enabled, teams_yaml.get("enabled", False)),
        mode=(env_settings.teams_mode or teams_yaml.get("mode", "webhook")).strip().lower(),
        webhook_url=env_settings.teams_webhook_url or teams_yaml.get("webhook_url", ""),
        tenant_id=env_settings.teams_tenant_id or teams_yaml.get("tenant_id", ""),
        client_id=env_settings.teams_client_id or teams_yaml.get("client_id", ""),
        client_secret=env_settings.teams_client_secret or teams_yaml.get("client_secret", ""),
        team_id=env_settings.teams_team_id or teams_yaml.get("team_id", ""),
        channel_id=env_settings.teams_channel_id or teams_yaml.get("channel_id", ""),
        timeout_seconds=env_settings.teams_timeout_seconds or teams_yaml.get("timeout_seconds", 30.0),
    )
    return NotificationSettings(email=email, teams=teams)


def load_whatap_settings() -> WhatapSettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    whatap_yaml = yaml_settings.get("whatap", {})
    env_settings = AppSettings()

    return WhatapSettings(
        webhook_secret=env_settings.whatap_webhook_secret or whatap_yaml.get("webhook_secret", ""),
    )


def load_user_comm_log_settings() -> UserCommLogSettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    comm_yaml = yaml_settings.get("user_comm_log", {})
    env_settings = AppSettings()

    retention_raw = env_settings.user_comm_retention or comm_yaml.get("retention_days", 30)
    try:
        retention_days = int(retention_raw)
    except (TypeError, ValueError):
        retention_days = 30

    return UserCommLogSettings(
        log_dir=env_settings.user_comm_log or comm_yaml.get("log_dir", "data/user_comm_logs"),
        retention_days=max(1, retention_days),
    )


def load_job_requester_settings() -> JobRequesterSettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    requester_yaml = yaml_settings.get("job_requester", {})
    env_settings = AppSettings()

    if env_settings.job_requester_interval_minutes is not None:
        interval_raw = env_settings.job_requester_interval_minutes
    else:
        interval_raw = requester_yaml.get("interval_minutes", 60)

    if env_settings.job_requester_initial_delay_seconds is not None:
        delay_raw = env_settings.job_requester_initial_delay_seconds
    else:
        delay_raw = requester_yaml.get("initial_delay_seconds", 60)

    try:
        interval_minutes = int(interval_raw)
    except (TypeError, ValueError):
        interval_minutes = 60
    try:
        initial_delay_seconds = int(delay_raw)
    except (TypeError, ValueError):
        initial_delay_seconds = 60

    if env_settings.job_requester_enabled is not None:
        enabled = env_settings.job_requester_enabled
    else:
        enabled = _as_bool(requester_yaml.get("enabled"), False)

    return JobRequesterSettings(
        enabled=enabled,
        interval_minutes=max(1, interval_minutes),
        initial_delay_seconds=max(0, initial_delay_seconds),
    )


def load_job_processor_settings() -> JobProcessorSettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    processor_yaml = yaml_settings.get("job_processor", {})
    env_settings = AppSettings()

    if env_settings.job_processor_poll_interval_seconds is not None:
        interval_raw = env_settings.job_processor_poll_interval_seconds
    else:
        interval_raw = processor_yaml.get("poll_interval_seconds", 60)

    if env_settings.job_processor_initial_delay_seconds is not None:
        delay_raw = env_settings.job_processor_initial_delay_seconds
    else:
        delay_raw = processor_yaml.get("initial_delay_seconds", 0)

    try:
        poll_interval_seconds = int(interval_raw)
    except (TypeError, ValueError):
        poll_interval_seconds = 60
    try:
        initial_delay_seconds = int(delay_raw)
    except (TypeError, ValueError):
        initial_delay_seconds = 0

    if env_settings.job_processor_enabled is not None:
        enabled = env_settings.job_processor_enabled
    else:
        enabled = _as_bool(processor_yaml.get("enabled"), True)

    if env_settings.job_processor_helpdesk_local_agent_id is not None:
        helpdesk_local_agent_id = env_settings.job_processor_helpdesk_local_agent_id.strip()
    else:
        helpdesk_local_agent_id = str(
            processor_yaml.get("helpdesk_local_agent_id", "helpdesk"),
        ).strip()

    if env_settings.job_processor_helpdesk_axit_agent_id is not None:
        helpdesk_axit_agent_id = env_settings.job_processor_helpdesk_axit_agent_id.strip()
    else:
        helpdesk_axit_agent_id = str(processor_yaml.get("helpdesk_axit_agent_id", "")).strip()

    return JobProcessorSettings(
        enabled=enabled,
        poll_interval_seconds=max(1, poll_interval_seconds),
        initial_delay_seconds=max(0, initial_delay_seconds),
        helpdesk_local_agent_id=helpdesk_local_agent_id or "helpdesk",
        helpdesk_axit_agent_id=helpdesk_axit_agent_id,
    )


def load_job_auditor_settings() -> JobAuditorSettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    auditor_yaml = yaml_settings.get("job_auditor", {})
    env_settings = AppSettings()

    if env_settings.job_auditor_local_agent_id is not None:
        local_agent_id = env_settings.job_auditor_local_agent_id.strip()
    else:
        local_agent_id = str(
            auditor_yaml.get("local_agent_id", "JOB_AUDITOR_AGENT"),
        ).strip()

    if env_settings.job_auditor_axit_agent_id is not None:
        axit_agent_id = env_settings.job_auditor_axit_agent_id.strip()
    else:
        axit_agent_id = str(auditor_yaml.get("axit_agent_id", "")).strip()

    return JobAuditorSettings(
        local_agent_id=local_agent_id or "JOB_AUDITOR_AGENT",
        axit_agent_id=axit_agent_id,
    )


def load_mynotes_settings() -> MyNotesSettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    mynotes_yaml = yaml_settings.get("mynotes", {})
    env_settings = AppSettings()

    if env_settings.mynotes_flush_interval_seconds is not None:
        interval_raw = env_settings.mynotes_flush_interval_seconds
    else:
        interval_raw = mynotes_yaml.get("flush_interval_seconds", 300)

    if env_settings.mynotes_flush_initial_delay_seconds is not None:
        delay_raw = env_settings.mynotes_flush_initial_delay_seconds
    else:
        delay_raw = mynotes_yaml.get("initial_delay_seconds", 0)

    try:
        flush_interval_seconds = int(interval_raw)
    except (TypeError, ValueError):
        flush_interval_seconds = 300
    try:
        initial_delay_seconds = int(delay_raw)
    except (TypeError, ValueError):
        initial_delay_seconds = 0

    if env_settings.mynotes_flush_enabled is not None:
        enabled = env_settings.mynotes_flush_enabled
    else:
        enabled = _as_bool(mynotes_yaml.get("enabled"), True)

    return MyNotesSettings(
        enabled=enabled,
        flush_interval_seconds=max(30, flush_interval_seconds),
        initial_delay_seconds=max(0, initial_delay_seconds),
    )


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"


class AuthSessionSettings(BaseModel):
    ttl_seconds: int = 3600
    absolute_max_seconds: int = 28800


class AuthProviderSettings(BaseModel):
    provider_type: str = "db"
    oauth_proxy: str = ""
    oauth_url: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_grant_type: str = "password"
    oauth_scope: str = "EA"
    oauth_auth_type: str = "IM"
    oauth_verify_ssl: bool = False


class AgentRuntimeSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8090
    api_key: str = ""


def load_redis_settings() -> RedisSettings:
    env_settings = AppSettings()
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    redis_yaml = yaml_settings.get("redis", {})

    url = (env_settings.redis_url or redis_yaml.get("url") or "redis://localhost:6379/0").strip()
    return RedisSettings(url=url)


def load_auth_session_settings() -> AuthSessionSettings:
    env_settings = AppSettings()
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    session_yaml = yaml_settings.get("auth_session", {})

    ttl_raw = (
        env_settings.auth_session_ttl_seconds
        if env_settings.auth_session_ttl_seconds is not None
        else session_yaml.get("ttl_seconds", 3600)
    )
    absolute_raw = (
        env_settings.auth_session_absolute_max_seconds
        if env_settings.auth_session_absolute_max_seconds is not None
        else session_yaml.get("absolute_max_seconds", 28800)
    )

    try:
        ttl_seconds = int(ttl_raw)
    except (TypeError, ValueError):
        ttl_seconds = 3600
    try:
        absolute_max_seconds = int(absolute_raw)
    except (TypeError, ValueError):
        absolute_max_seconds = 28800

    return AuthSessionSettings(
        ttl_seconds=max(60, ttl_seconds),
        absolute_max_seconds=max(60, absolute_max_seconds),
    )


def load_auth_provider_settings() -> AuthProviderSettings:
    env_settings = AppSettings()
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    auth_yaml = yaml_settings.get("auth", {})

    raw_type = (env_settings.auth_provider_type or auth_yaml.get("provider_type") or "db").strip().lower()
    if raw_type not in {"db", "madang"}:
        raw_type = "db"

    oauth_proxy = (env_settings.oauth_proxy or auth_yaml.get("oauth_proxy") or "").strip()
    oauth_url = (env_settings.oauth_url or auth_yaml.get("oauth_url") or "").strip()
    oauth_client_id = (env_settings.oauth_client_id or auth_yaml.get("oauth_client_id") or "").strip()
    oauth_client_secret = (
        env_settings.oauth_client_secret or auth_yaml.get("oauth_client_secret") or ""
    ).strip()
    oauth_grant_type = (
        env_settings.oauth_grant_type or auth_yaml.get("oauth_grant_type") or "password"
    ).strip()
    oauth_scope = (env_settings.oauth_scope or auth_yaml.get("oauth_scope") or "EA").strip()
    oauth_auth_type = (env_settings.oauth_auth_type or auth_yaml.get("oauth_auth_type") or "IM").strip()
    verify_raw = (
        env_settings.oauth_verify_ssl
        if env_settings.oauth_verify_ssl is not None
        else auth_yaml.get("oauth_verify_ssl")
    )
    oauth_verify_ssl = _as_bool(verify_raw, default=False)

    return AuthProviderSettings(
        provider_type=raw_type,
        oauth_proxy=oauth_proxy,
        oauth_url=oauth_url,
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
        oauth_grant_type=oauth_grant_type,
        oauth_scope=oauth_scope,
        oauth_auth_type=oauth_auth_type,
        oauth_verify_ssl=oauth_verify_ssl,
    )


def load_settings() -> tuple[LLMSettings, ServerSettings, dict[str, MCPServerConfig], str]:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    mcp_yaml = _load_yaml(CONFIG_DIR / "mcp_servers.yaml")
    env_settings = AppSettings()

    llm_yaml = yaml_settings.get("llm", {})
    server_yaml = yaml_settings.get("server", {})

    llm = LLMSettings(
        base_url=env_settings.llm_base_url or llm_yaml.get("base_url", LLMSettings.model_fields["base_url"].default),
        api_key=env_settings.llm_api_key or llm_yaml.get("api_key", LLMSettings.model_fields["api_key"].default),
        model=env_settings.llm_model or llm_yaml.get("model", LLMSettings.model_fields["model"].default),
        max_context_tokens=(
            env_settings.llm_max_context_tokens
            or llm_yaml.get("max_context_tokens", LLMSettings.model_fields["max_context_tokens"].default)
        ),
    )
    server = ServerSettings(
        backend_host=env_settings.backend_host or server_yaml.get("backend_host", "0.0.0.0"),
        backend_port=resolve_backend_listen_port(
            env_settings=env_settings,
            server_yaml=server_yaml,
        ),
        frontend_host=env_settings.frontend_host or server_yaml.get("frontend_host", "0.0.0.0"),
        frontend_port=env_settings.frontend_port or server_yaml.get("frontend_port", 9001),
        backend_api_host=env_settings.backend_api_host or server_yaml.get("backend_api_host", "localhost"),
        backend_api_port=(
            env_settings.backend_api_port
            or server_yaml.get("backend_api_port")
            or env_settings.backend_port
            or server_yaml.get("backend_port", 8080)
        ),
        health_check_interval_seconds=(
            env_settings.health_check_interval_seconds
            or server_yaml.get("health_check_interval_seconds", 30)
        ),
        agent_runtime_mode=resolve_agent_runtime_mode(
            env_settings=env_settings,
            server_yaml=server_yaml,
        ),
        agent_runtime_http_base_url=(
            env_settings.agent_runtime_http_base_url
            or server_yaml.get("agent_runtime_http_base_url", "")
        ),
        agent_runtime_http_timeout_seconds=float(
            env_settings.agent_runtime_http_timeout_seconds
            or server_yaml.get("agent_runtime_http_timeout_seconds", 3600.0)
        ),
        agent_runtime_api_key=(
            env_settings.agent_runtime_api_key
            or server_yaml.get("agent_runtime_api_key", "")
        ),
        control_plane_base_url=(
            env_settings.control_plane_base_url
            or server_yaml.get("control_plane_base_url", "")
        ),
    )

    mcp_servers: dict[str, MCPServerConfig] = {}
    for name, config in (mcp_yaml.get("servers") or {}).items():
        mcp_servers[name] = MCPServerConfig(**config)

    mcp_servers = _apply_mcp_env_overrides(mcp_servers)

    database_path = env_settings.database_path or server_yaml.get("database_path", "data/app.db")

    return llm, server, mcp_servers, database_path


def load_agent_runtime_settings() -> AgentRuntimeSettings:
    env_settings = AppSettings()
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    runtime_yaml = yaml_settings.get("agent_runtime", {})

    return AgentRuntimeSettings(
        host=env_settings.agent_runtime_host or runtime_yaml.get("host", "0.0.0.0"),
        port=env_settings.agent_runtime_port or runtime_yaml.get("port", 8090),
        api_key=env_settings.agent_runtime_api_key or runtime_yaml.get("api_key", ""),
    )


def resolve_control_plane_base_url(server: ServerSettings) -> str:
    explicit = (server.control_plane_base_url or "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = (server.backend_api_host or "localhost").strip()
    port = server.backend_api_port
    return f"http://{host}:{port}".rstrip("/")
