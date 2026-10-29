from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from policylens.ingestion.models import (
    CanonicalBlock,
    CanonicalDocument,
    DocumentPage,
    SourceMetadata,
    StructuredDataset,
    StructuredObservation,
)
from policylens.retrieval.chunking import chunk_report, chunk_structured_dataset
from policylens.retrieval.models import ChunkerConfig, SourceArtifact


class WordCounter:
    def count_tokens(self, text: str) -> int:
        return len(text.split())


def _source(source_id: str = "report") -> SourceArtifact:
    return SourceArtifact(
        source_id=source_id,
        canonical_path=f"data/canonical/reports/{source_id}/parser/input.json",
        canonical_sha256="a" * 64,
        source_content_sha256="b" * 64,
        parser_version="parser-1",
        source_type="report",
        title="Report title",
        publisher="World Bank",
        source_uri="https://example.test/report",
        licence="CC BY 4.0",
        sensitivity="public",
        allowed_usage=("retrieval", "evaluation"),
    )


def _document(
    blocks: Iterable[CanonicalBlock], document_id: str = "doc:report"
) -> CanonicalDocument:
    source = SourceMetadata(
        source_id="report",
        title="Report title",
        publisher="World Bank",
        canonical_url="https://example.test/report",
        retrieved_at="2026-10-25T00:00:00Z",
        published_at="2024-01-01T00:00:00Z",
        licence="CC BY 4.0",
        usage_constraints=None,
        sensitivity="public",
        sha256="b" * 64,
    )
    return CanonicalDocument(
        document_id=document_id,
        source_id="report",
        title="Report title",
        language="en",
        pages=(DocumentPage(page_number=1, blocks=tuple(blocks)),),
        provenance=source,
        content_sha256="b" * 64,
        parser_version="parser-1",
    )


def _block(block_id: str, text: str, start: int, section: tuple[str, ...]) -> CanonicalBlock:
    return CanonicalBlock(
        block_id=block_id,
        block_type="paragraph",
        text=text,
        section_path=section,
        bbox=None,
        start_char=start,
        end_char=start + len(text),
    )


def _config(
    strategy: Literal["fixed-size", "structure-aware"],
    target: int,
    minimum: int,
    maximum: int,
    overlap: int,
) -> ChunkerConfig:
    return ChunkerConfig(
        strategy=strategy,
        version=f"{strategy}-test-v1",
        target_tokens=target,
        min_tokens=minimum,
        max_tokens=maximum,
        overlap_tokens=overlap,
        tokenizer="word-counter-test-v1",
    )


def test_structure_aware_chunks_keep_section_locations_and_stable_ids() -> None:
    document = _document(
        [
            _block("b1", "Jobs policy evidence covers skills and wages.", 0, ("1 Findings",)),
            _block("b2", "The program improved employment outcomes.", 50, ("1 Findings",)),
            _block("b3", "A different section reports barriers.", 100, ("2 Barriers",)),
        ]
    )
    config = _config("structure-aware", 40, 1, 40, 0)

    first = chunk_report(_source(), document, config, WordCounter())
    second = chunk_report(_source(), document, config, WordCounter())

    assert [passage.passage_id for passage in first] == [passage.passage_id for passage in second]
    assert len(first) == 2
    assert first[0].section_path == ("1 Findings",)
    assert len(first[0].locations) == 2
    assert "program improved employment" in first[0].text
    assert first[0].locations[0].start_char == 0
    assert first[0].locations[1].end_char == 91


def test_fixed_chunks_enforce_model_token_limit_and_cover_long_blocks() -> None:
    words = [f"word{index}" for index in range(45)]
    text = " ".join(words)
    document = _document([_block("long", text, 0, ("1 Findings",))])
    config = _config("fixed-size", 12, 4, 14, 3)

    passages = chunk_report(_source(), document, config, WordCounter())

    assert len(passages) > 1
    assert all(passage.token_count <= 14 for passage in passages)
    assert passages[0].text.startswith("word0 word1")
    assert passages[-1].text.endswith("word44")


def test_structure_aware_chunks_bound_location_metadata() -> None:
    blocks = [
        _block(f"b{index}", f"Employment finding number {index}.", index * 40, ("1 Findings",))
        for index in range(25)
    ]
    document = _document(blocks)

    passages = chunk_report(
        _source(),
        document,
        _config("structure-aware", 500, 1, 500, 0),
        WordCounter(),
    )

    assert len(passages) == 2
    assert all(1 <= len(passage.locations) <= 20 for passage in passages)
    assert "Employment finding number 24." in passages[-1].text


def test_oversized_table_splits_by_rows_and_repeats_header() -> None:
    rows = (("Year", "Rate"), ("2021", "8.1"), ("2022", "7.9"), ("2023", "7.5"))
    text = "\n".join("\t".join(cell for cell in row) for row in rows)
    block = CanonicalBlock(
        block_id="table-1",
        block_type="table",
        text=text,
        section_path=("1 Findings",),
        bbox=None,
        table_rows=rows,
        start_char=0,
        end_char=len(text),
    )
    document = _document([block])

    passages = chunk_report(
        _source(),
        document,
        _config("structure-aware", 8, 1, 10, 0),
        WordCounter(),
    )

    assert len(passages) == 3
    assert all(passage.text.startswith("Year\tRate") for passage in passages)
    assert all(passage.locations[0].block_id == "table-1" for passage in passages)
    assert {line for passage in passages for line in passage.text.splitlines()[1:]} == {
        "2021\t8.1",
        "2022\t7.9",
        "2023\t7.5",
    }


def test_single_cell_table_candidate_falls_back_to_bounded_text_splitting() -> None:
    text = " ".join(f"policyword{index}" for index in range(35))
    block = CanonicalBlock(
        block_id="b0154",
        block_type="table",
        text=text,
        section_path=("Survey",),
        bbox=None,
        table_rows=((None, ""), (None, text)),
        start_char=25,
        end_char=25 + len(text),
    )
    document = _document([block])

    passages = chunk_report(
        _source(),
        document,
        _config("fixed-size", 12, 4, 14, 3),
        WordCounter(),
    )

    assert len(passages) > 1
    assert all(passage.token_count <= 14 for passage in passages)
    assert all(passage.locations[0].block_id == "b0154" for passage in passages)
    assert passages[0].text.startswith("policyword0")
    assert passages[-1].text.endswith("policyword34")


def test_oversized_table_row_splits_cells_with_repeated_column_labels() -> None:
    left = " ".join(f"leftword{index}" for index in range(35))
    right = " ".join(f"rightword{index}" for index in range(37))
    rows = (("Program type", "Operational definition"), (left, right), (left, right))
    text = "\n".join("\t".join(cell for cell in row) for row in rows)
    block = CanonicalBlock(
        block_id="large-row",
        block_type="table",
        text=text,
        section_path=("Definitions",),
        bbox=None,
        table_rows=rows,
        start_char=40,
        end_char=40 + len(text),
    )
    document = _document([block])

    passages = chunk_report(
        _source(),
        document,
        _config("structure-aware", 12, 4, 20, 3),
        WordCounter(),
    )

    assert len(passages) > 2
    assert all(passage.token_count <= 20 for passage in passages)
    assert all(
        passage.text.startswith(("Program type: ", "Operational definition: "))
        for passage in passages
    )
    joined = " ".join(passage.text for passage in passages)
    assert "leftword34" in joined
    assert "rightword36" in joined
    assert all(passage.locations[0].start_char == block.start_char for passage in passages)
    passage_ids = [passage.passage_id for passage in passages]
    assert len(passage_ids) == len(set(passage_ids))


def test_structured_rows_keep_observation_keys_and_rendered_value() -> None:
    provenance = SourceMetadata(
        source_id="indicator",
        title="Youth unemployment",
        publisher="World Bank Data",
        canonical_url="https://data.worldbank.org/indicator/SL.UEM.1524.ZS",
        retrieved_at="2026-10-25T00:00:00Z",
        published_at=None,
        licence="CC BY 4.0",
        usage_constraints="Modeled estimate",
        sensitivity="public",
        sha256="c" * 64,
        indicator_id="SL.UEM.1524.ZS",
        countries=("IND",),
        year_range=(2025, 2025),
    )
    dataset = StructuredDataset(
        dataset_id="doc:indicator:hash",
        source_id="indicator",
        title="Youth unemployment",
        indicator_id="SL.UEM.1524.ZS",
        indicator_label="Youth unemployment (% of labor force ages 15-24)",
        country_codes=("IND",),
        year_range=(2025, 2025),
        api_metadata={"lastupdated": "2026-10-08"},
        observations=(
            StructuredObservation(
                observation_id="indicator:IND:2025",
                country_iso2="IN",
                country_iso3="IND",
                country_name="India",
                year=2025,
                value=16.0,
                unit="",
                observation_status="",
                decimal=1,
            ),
        ),
        missing_value_semantics="JSON null is unknown",
        provenance=provenance,
        content_sha256="c" * 64,
        parser_version="structured-1",
    )
    source = SourceArtifact(
        source_id="indicator",
        canonical_path="data/canonical/structured/indicator/parser/input.json",
        canonical_sha256="d" * 64,
        source_content_sha256="c" * 64,
        parser_version="structured-1",
        source_type="structured",
        title="Youth unemployment",
        publisher="World Bank Data",
        source_uri=provenance.canonical_url,
        licence="CC BY 4.0",
        usage_constraints="Modeled estimate",
        sensitivity="public",
        allowed_usage=("retrieval",),
        indicator_id="SL.UEM.1524.ZS",
        countries=("IND",),
        year_range=(2025, 2025),
    )

    passages = chunk_structured_dataset(
        source, dataset, _config("structure-aware", 40, 1, 40, 0), WordCounter()
    )

    assert len(passages) == 1
    assert passages[0].row_key is not None
    assert passages[0].row_key.observation_id == "indicator:IND:2025"
    assert passages[0].country_iso3 == "IND"
    assert "Value: 16.0" in passages[0].text
