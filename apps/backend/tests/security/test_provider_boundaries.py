from __future__ import annotations

import pytest
from pydantic import ValidationError

from policylens.agent_runtime.models import (
    AgentModelUsage,
    ModelCapabilities,
    ModelCapabilitySet,
    ModelLimits,
    ModelRunMetadata,
)
from policylens.settings import AppSettings


def test_mlx_provider_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValidationError, match="loopback host"):
        AppSettings(
            _env_file=None,  # type: ignore[call-arg]
            model_provider="mlx",
            mlx_model="local-test-model",
            mlx_base_url="http://203.0.113.10:8080/v1",  # type: ignore[arg-type]
            embedding_provider="local",
        )


def test_run_metadata_rejects_provider_identity_mismatch() -> None:
    capabilities = ModelCapabilities(
        provider="mlx",
        model_id="local-test-model",
        route="mlx_chat_completions",
        ready=True,
        capabilities=ModelCapabilitySet(
            native_tool_calls=False,
            native_json_schema=False,
            host_action_envelope=True,
            streaming=False,
            usage_reporting=True,
        ),
        limits=ModelLimits(max_input_chars=1000, max_output_tokens=100, timeout_seconds=5),
        platform="synthetic test gateway",
    )

    with pytest.raises(ValidationError, match="must match the selected provider"):
        ModelRunMetadata(
            provider="openai",
            model_id="local-test-model",
            prompt_version="test-v1",
            latency_ms=1,
            usage=AgentModelUsage(),
            capabilities=capabilities,
        )
