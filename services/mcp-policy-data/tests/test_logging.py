import io
import json

from policylens_mcp.logging import configure_logging


def test_mcp_logging_omits_message_contents() -> None:
    stream = io.StringIO()
    logger = configure_logging("policylens-mcp", stream=stream)

    logger.warning(
        "untrusted message contains sk-test-secret",
        extra={"event": "startup_warning", "error_code": "MCP_UNAVAILABLE"},
    )

    output = stream.getvalue()
    record = json.loads(output)
    assert record["service"] == "policylens-mcp"
    assert record["event"] == "startup_warning"
    assert record["error_code"] == "MCP_UNAVAILABLE"
    assert "sk-test-secret" not in output


def test_mcp_operation_telemetry_uses_an_allowlist() -> None:
    stream = io.StringIO()
    logger = configure_logging("policylens-mcp", stream=stream)

    logger.info(
        "MCP operation completed",
        extra={
            "event": "mcp_tool_call",
            "server_name": "PolicyLens Policy Data Server",
            "server_version": "0.1.0",
            "tool_name": "query_statistics",
            "argument_hash": "b" * 64,
            "status": "failed",
            "duration_ms": 8.25,
            "trace_id": "trace-2",
            "error_code": "STATISTICS_DATA_INVALID",
            "arguments": "raw-secret-arguments",
            "passage_text": "raw-private-passage",
        },
    )

    output = stream.getvalue()
    record = json.loads(output)
    assert record["server_name"] == "PolicyLens Policy Data Server"
    assert record["server_version"] == "0.1.0"
    assert record["tool_name"] == "query_statistics"
    assert record["argument_hash"] == "b" * 64
    assert record["duration_ms"] == "8.25"
    assert record["error_code"] == "STATISTICS_DATA_INVALID"
    assert "raw-secret-arguments" not in output
    assert "raw-private-passage" not in output
