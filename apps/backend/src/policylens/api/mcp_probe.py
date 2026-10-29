import json
from typing import Literal, Protocol

import anyio
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from policylens.mcp.client import MCPClientError, MCPStatisticsAdapter
from policylens.mcp.models import MCPHostErrorCode
from policylens.settings import PROJECT_ROOT


class MCPProbeConfig(Protocol):
    mcp_server_command: str
    mcp_timeout_seconds: int


class MCPProbeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    mcp_server_command: str = "uv run --package policylens-mcp python -m policylens_mcp"
    mcp_timeout_seconds: int = 15


class MCPProbeResult(BaseModel):
    status: Literal["ready", "unavailable"]
    error_code: MCPHostErrorCode | None = None


async def probe_mcp(settings: MCPProbeConfig) -> MCPProbeResult:
    try:
        await MCPStatisticsAdapter(settings).probe()
    except MCPClientError as error:
        return MCPProbeResult(status="unavailable", error_code=error.code)
    except Exception:
        return MCPProbeResult(status="unavailable", error_code="MCP_UNAVAILABLE")
    return MCPProbeResult(status="ready")


def main() -> int:
    settings = MCPProbeSettings()
    result = anyio.run(probe_mcp, settings)
    print(json.dumps(result.model_dump(exclude_none=True), separators=(",", ":")))
    return 0 if result.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
