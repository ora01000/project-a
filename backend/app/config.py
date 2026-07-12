from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field
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


class InventorySettings(BaseModel):
    chroma_data_path: str = "data/chroma"
    csv_path: str = "data/inventory/inventory.csv"
    upload_path: str = "data/inventory/uploads"


class WhatapSettings(BaseModel):
    webhook_secret: str = ""


class UserCommLogSettings(BaseModel):
    log_dir: str = "data/user_comm_logs"
    retention_days: int = 30


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
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

    chroma_data_path: str = Field(default="data/chroma", alias="CHROMA_DATA_PATH")
    inventory_csv_path: str = Field(default="data/inventory/inventory.csv", alias="INVENTORY_CSV_PATH")
    inventory_upload_path: str = Field(default="data/inventory/uploads", alias="INVENTORY_UPLOAD_PATH")
    whatap_webhook_secret: str = Field(default="", alias="WHATAP_WEBHOOK_SECRET")

    user_comm_log: str = Field(default="data/user_comm_logs", alias="USER_COMM_LOG")
    user_comm_retention: int = Field(default=30, alias="USER_COMM_RETENTION")


def _merged_env() -> dict[str, str]:
    import os

    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for key, value in dotenv_values(ENV_FILE).items():
            if value is not None:
                values[key] = value
    values.update(os.environ)
    return values


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


def load_inventory_settings() -> InventorySettings:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    inventory_yaml = yaml_settings.get("inventory", {})
    env_settings = AppSettings()

    return InventorySettings(
        chroma_data_path=env_settings.chroma_data_path or inventory_yaml.get("chroma_data_path", "data/chroma"),
        csv_path=env_settings.inventory_csv_path or inventory_yaml.get("csv_path", "data/inventory/inventory.csv"),
        upload_path=env_settings.inventory_upload_path or inventory_yaml.get("upload_path", "data/inventory/uploads"),
    )


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
        backend_port=env_settings.backend_port or server_yaml.get("backend_port", 8080),
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
    )

    mcp_servers: dict[str, MCPServerConfig] = {}
    for name, config in (mcp_yaml.get("servers") or {}).items():
        mcp_servers[name] = MCPServerConfig(**config)

    mcp_servers = _apply_mcp_env_overrides(mcp_servers)

    database_path = env_settings.database_path or server_yaml.get("database_path", "data/app.db")

    return llm, server, mcp_servers, database_path
