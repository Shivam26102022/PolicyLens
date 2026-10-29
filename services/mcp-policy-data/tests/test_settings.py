from policylens_mcp.settings import McpSettings


def settings_without_dotenv() -> McpSettings:
    return McpSettings(_env_file=None)  # type: ignore[call-arg]


def test_mcp_settings_use_the_canonical_identity_and_stdio() -> None:
    settings = settings_without_dotenv()

    assert settings.mcp_server_name == "PolicyLens Policy Data Server"
    assert settings.mcp_transport == "stdio"
