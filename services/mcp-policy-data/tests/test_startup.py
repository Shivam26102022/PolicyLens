import sys

import anyio
from mcp import Client, StdioServerParameters

from policylens_mcp import server


def test_stdio_handshake_reports_canonical_server_identity() -> None:
    async def connect() -> tuple[
        str | None,
        str | None,
        str | None,
        list[str],
        list[str],
    ]:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "policylens_mcp"],
        )
        with anyio.fail_after(10):
            async with Client(parameters) as client:
                server_name = client.server_info.name if client.server_info else None
                server_version = client.server_info.version if client.server_info else None
                tools = await client.list_tools()
                templates = await client.list_resource_templates()
                return (
                    server_name,
                    server_version,
                    client.protocol_version,
                    [tool.name for tool in tools.tools],
                    [template.uri_template for template in templates.resource_templates],
                )

    (
        server_name,
        server_version,
        protocol_version,
        tool_names,
        resource_templates,
    ) = anyio.run(connect)

    assert server_name == "PolicyLens Policy Data Server"
    assert server_version == "0.1.0"
    assert protocol_version == "2026-07-28"
    assert tool_names == ["query_statistics"]
    assert resource_templates == ["policy://sources/{source_id}/passages/{passage_id}"]


def test_stdio_server_advertises_and_renders_the_brief_prompt() -> None:
    async def fetch() -> tuple[list[str], str]:
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "policylens_mcp"])
        with anyio.fail_after(10):
            async with Client(parameters) as client:
                prompts = await client.list_prompts()
                rendered = await client.get_prompt(
                    "cited_policy_brief", {"topic": "youth unemployment"}
                )
                content = rendered.messages[0].content
                return [p.name for p in prompts.prompts], getattr(content, "text", "")

    names, text = anyio.run(fetch)

    assert names == ["cited_policy_brief"]
    assert "youth unemployment" in text
    assert "untrusted" in text


def test_server_entrypoint_starts_stdio_transport(monkeypatch) -> None:
    started: list[bool] = []
    monkeypatch.setattr(server.mcp, "run", lambda: started.append(True))

    server.main()

    assert started == [True]
