from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    mcp_transport: Literal["stdio"] = "stdio"
    mcp_server_name: Literal["PolicyLens Policy Data Server"] = "PolicyLens Policy Data Server"


def get_settings() -> McpSettings:
    return McpSettings()
