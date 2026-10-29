import io
import json
from uuid import UUID

from policylens.agent_runtime.runtime import _log_model_failure
from policylens.observability.logging import configure_logging


def test_structured_logging_omits_message_contents() -> None:
    stream = io.StringIO()
    logger = configure_logging("policylens-api", stream=stream)

    logger.warning(
        "untrusted message contains sk-test-secret",
        extra={
            "event": "configuration_error",
            "error_code": "INVALID_REQUEST",
            "exception_type": "APIStatusError",
            "http_status": 404,
        },
    )

    output = stream.getvalue()
    record = json.loads(output)
    assert record["service"] == "policylens-api"
    assert record["event"] == "configuration_error"
    assert record["error_code"] == "INVALID_REQUEST"
    assert record["exception_type"] == "APIStatusError"
    assert record["http_status"] == "404"
    assert "sk-test-secret" not in output


def test_mcp_telemetry_logs_only_allowlisted_hash_metadata() -> None:
    stream = io.StringIO()
    logger = configure_logging("policylens-api", stream=stream)

    logger.info(
        "MCP request completed",
        extra={
            "event": "mcp_request",
            "server_name": "PolicyLens Policy Data Server",
            "server_version": "0.1.0",
            "tool_name": "query_statistics",
            "resource_name": None,
            "argument_hash": "a" * 64,
            "status": "succeeded",
            "duration_ms": 12.5,
            "trace_id": "trace-1",
            "error_code": None,
            "arguments": "raw-secret-arguments",
            "result": "raw-private-result",
        },
    )

    output = stream.getvalue()
    record = json.loads(output)
    assert record["server_name"] == "PolicyLens Policy Data Server"
    assert record["server_version"] == "0.1.0"
    assert record["tool_name"] == "query_statistics"
    assert record["argument_hash"] == "a" * 64
    assert record["duration_ms"] == "12.5"
    assert record["trace_id"] == "trace-1"
    assert "raw-secret-arguments" not in output
    assert "raw-private-result" not in output


def test_model_failure_logs_trace_and_status_without_provider_message() -> None:
    stream = io.StringIO()
    configure_logging("policylens-api", stream=stream)
    error = RuntimeError("provider response contains sk-test-secret")
    error.status_code = 404  # type: ignore[attr-defined]

    _log_model_failure(UUID("89ac931b-de5d-41e8-ac34-9c4542dfefd6"), error)

    record = json.loads(stream.getvalue())
    assert record["event"] == "agent_model_failed"
    assert record["trace_id"] == "89ac931b-de5d-41e8-ac34-9c4542dfefd6"
    assert record["error_code"] == "MODEL_UNAVAILABLE"
    assert record["exception_type"] == "RuntimeError"
    assert record["http_status"] == "404"
    assert "sk-test-secret" not in stream.getvalue()
