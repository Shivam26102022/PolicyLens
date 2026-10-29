from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from policylens.agent_runtime.models import AgentDraft
from policylens.agent_runtime.tools import (
    AgentToolExecutionError,
    StatisticsQueryRequest,
)


class MLXFinalAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    action: Literal["final"]
    draft: AgentDraft


class MLXStatisticsAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    action: Literal["query_statistics"]
    request: StatisticsQueryRequest


MLXAgentAction = Annotated[MLXFinalAction | MLXStatisticsAction, Field(discriminator="action")]


def parse_mlx_action(content: str | None) -> MLXFinalAction | MLXStatisticsAction:
    if not content or len(content) > 50_000:
        raise AgentToolExecutionError("OUTPUT_SCHEMA_INVALID")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise AgentToolExecutionError("OUTPUT_SCHEMA_INVALID") from error
    if not isinstance(payload, dict):
        raise AgentToolExecutionError("OUTPUT_SCHEMA_INVALID")
    try:
        action = payload.get("action")
        if action == "final":
            return MLXFinalAction.model_validate(payload)
        if action == "query_statistics":
            return MLXStatisticsAction.model_validate(payload)
    except ValidationError as error:
        raise AgentToolExecutionError("OUTPUT_SCHEMA_INVALID") from error
    raise AgentToolExecutionError("OUTPUT_SCHEMA_INVALID")
