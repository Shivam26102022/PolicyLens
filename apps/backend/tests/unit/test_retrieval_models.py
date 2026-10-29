from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from policylens.retrieval.models import (
    ActiveIndexPointer,
    BlockLocation,
    RetrievalFilters,
    RetrievalRequest,
    StructuredRowKey,
)

HASH = "a" * 64


def test_retrieval_request_clamps_top_k_and_normalizes_query() -> None:
    request = RetrievalRequest(
        query="  youth unemployment in India  ",
        mode="hybrid",
        top_k=99,
        filters=RetrievalFilters(country_iso3=("IND",), years=(2025,)),
    )

    assert request.query == "youth unemployment in India"
    assert request.top_k == 20
    assert request.filters.country_iso3 == ("IND",)


def test_retrieval_request_rejects_permission_escalation() -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest.model_validate(
            {
                "query": "unemployment",
                "mode": "bm25",
                "filters": {"permission_scope": ["restricted"]},
            }
        )


def test_block_location_and_row_key_validate_stable_coordinates() -> None:
    location = BlockLocation(
        page_number=1,
        block_id="p0001-b0001",
        start_char=0,
        end_char=12,
    )
    row_key = StructuredRowKey(
        dataset_id="dataset:unemployment",
        observation_id="youth:IND:2025",
        indicator_id="SL.UEM.1524.ZS",
        country_iso3="IND",
        year=2025,
    )

    assert location.end_char > location.start_char
    assert row_key.country_iso3 == "IND"

    with pytest.raises(ValidationError):
        BlockLocation(page_number=0, block_id="bad", start_char=8, end_char=2)


def test_active_pointer_requires_hashed_versions() -> None:
    pointer = ActiveIndexPointer(
        schema_version="1.0",
        build_id=UUID("9a734d29-8d52-4afe-97f6-14963f251f1b"),
        index_version=HASH,
        manifest_path="data/manifests/retrieval-index-manifest.json",
        manifest_sha256=HASH,
        previous=None,
    )

    assert pointer.index_version == HASH
    assert pointer.updated_at.tzinfo is not None
    with pytest.raises(ValidationError):
        ActiveIndexPointer(
            schema_version="1.0",
            build_id=UUID("9a734d29-8d52-4afe-97f6-14963f251f1b"),
            index_version="latest",
            manifest_path="manifest.json",
            manifest_sha256=HASH,
            previous=None,
        )
