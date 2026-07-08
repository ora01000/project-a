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


class ServerSettings(BaseModel):
    backend_port: int = 8080
    frontend_port: int = 9001


class MCPServerConfig(BaseModel):
    transport: str = "streamable_http"
    url: str
    enabled: bool = True


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = Field(default="http://localhost:8001/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="not-needed", alias="LLM_API_KEY")
    llm_model: str = Field(default="./llm_model/qwen3-4b-4bit-mlx", alias="LLM_MODEL")
    backend_port: int = Field(default=8080, alias="BACKEND_PORT")
    frontend_port: int = Field(default=9001, alias="FRONTEND_PORT")


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


def load_settings() -> tuple[LLMSettings, ServerSettings, dict[str, MCPServerConfig]]:
    yaml_settings = _load_yaml(CONFIG_DIR / "settings.yaml")
    mcp_yaml = _load_yaml(CONFIG_DIR / "mcp_servers.yaml")
    env_settings = AppSettings()

    llm_yaml = yaml_settings.get("llm", {})
    server_yaml = yaml_settings.get("server", {})

    llm = LLMSettings(
        base_url=env_settings.llm_base_url or llm_yaml.get("base_url", LLMSettings.model_fields["base_url"].default),
        api_key=env_settings.llm_api_key or llm_yaml.get("api_key", LLMSettings.model_fields["api_key"].default),
        model=env_settings.llm_model or llm_yaml.get("model", LLMSettings.model_fields["model"].default),
    )
    server = ServerSettings(
        backend_port=env_settings.backend_port or server_yaml.get("backend_port", 8080),
        frontend_port=env_settings.frontend_port or server_yaml.get("frontend_port", 9001),
    )

    mcp_servers: dict[str, MCPServerConfig] = {}
    for name, config in (mcp_yaml.get("servers") or {}).items():
        mcp_servers[name] = MCPServerConfig(**config)

    mcp_servers = _apply_mcp_env_overrides(mcp_servers)

    return llm, server, mcp_servers
