from __future__ import annotations

import pytest
from pydantic import ValidationError

from policylens_mcp.models import StatisticsQueryRequest


def _query() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "indicator": "SL.UEM.1524.ZS",
        "geographies": ["IND"],
        "start_year": 2020,
        "end_year": 2022,
        "aggregation": "mean",
        "group_by": [],
        "row_limit": 10,
    }


def test_mcp_request_rejects_unrecognized_arguments() -> None:
    with pytest.raises(ValidationError):
        StatisticsQueryRequest.model_validate(_query() | {"source_path": "../private"})


def test_mcp_request_enforces_supported_indicator_and_result_limit() -> None:
    with pytest.raises(ValidationError):
        StatisticsQueryRequest.model_validate(_query() | {"indicator": "unknown-indicator"})
    with pytest.raises(ValidationError):
        StatisticsQueryRequest.model_validate(_query() | {"row_limit": 45})
