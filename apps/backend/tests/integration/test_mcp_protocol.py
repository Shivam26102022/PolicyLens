from __future__ import annotations

import asyncio

from policylens.mcp.client import MCPStatisticsAdapter
from policylens.settings import AppSettings


def test_backend_discovers_the_pinned_stdio_mcp_contract() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        model_provider="mlx",
        mlx_model="local-test-model",
        embedding_provider="local",
        mcp_server_command="uv run --locked --package policylens-mcp python -m policylens_mcp",
    )

    asyncio.run(MCPStatisticsAdapter(settings).probe())
