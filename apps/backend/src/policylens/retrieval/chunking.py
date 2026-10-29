from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Protocol

from policylens.ingestion.models import CanonicalBlock, CanonicalDocument, StructuredDataset
from policylens.retrieval.models import (
    BlockLocation,
    ChunkerConfig,
    CorpusPassage,
    SourceArtifact,
    StructuredRowKey,
    passage_text_sha256,
)


class TokenCounter(Protocol):
    def count_tokens(self, text: str) -> int: ...


class ChunkingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _TextSpan:
    text: str
    page_number: int
    block_id: str
    start_char: int
    end_char: int
    section_path: tuple[str, ...]
    atomic: bool = False
    identity_suffix: str = ""


def fixed_chunker_config() -> ChunkerConfig:
    return ChunkerConfig(
        strategy="fixed-size",
        version="fixed-500-75-v4",
        target_tokens=500,
        min_tokens=120,
        max_tokens=500,
        overlap_tokens=75,
        tokenizer="BAAI/bge-small-en-v1.5",
    )


def structure_aware_chunker_config(*, target_tokens: int = 450) -> ChunkerConfig:
    if target_tokens == 450:
        minimum, maximum, overlap, version = 120, 500, 75, "structure-aware-450-v4"
    elif target_tokens == 250:
        minimum, maximum, overlap, version = 80, 350, 50, "structure-aware-250-v4"
    else:
        raise ValueError("supported structure-aware targets are 250 and 450 tokens")
    return ChunkerConfig(
        strategy="structure-aware",
        version=version,
        target_tokens=target_tokens,
        min_tokens=minimum,
        max_tokens=maximum,
        overlap_tokens=overlap,
        tokenizer="BAAI/bge-small-en-v1.5",
    )


def _require_retrieval_source(source: SourceArtifact, expected_type: str) -> None:
    if source.source_type != expected_type:
        raise ChunkingError(
            "SOURCE_TYPE_MISMATCH", "Canonical source type does not match parser input"
        )
    if "retrieval" not in source.allowed_usage:
        raise ChunkingError("RETRIEVAL_NOT_ALLOWED", "Source is not allowed for retrieval")


def _embedding_text(title: str, section_path: tuple[str, ...], text: str) -> str:
    breadcrumb = " > ".join(section_path)
    header = "\n".join(part for part in (title, breadcrumb) if part)
    return f"{header}\n\n{text}" if header else text


def _count_embedding(
    title: str,
    section_path: tuple[str, ...],
    text: str,
    token_counter: TokenCounter,
) -> int:
    return token_counter.count_tokens(_embedding_text(title, section_path, text))


def _split_table_block(
    source: SourceArtifact,
    page_number: int,
    block: CanonicalBlock,
    text: str,
    leading: int,
    config: ChunkerConfig,
    token_counter: TokenCounter,
) -> list[_TextSpan] | None:
    if not block.table_rows:
        return None
    nonempty_rows = [row for row in block.table_rows if any(cell and cell.strip() for cell in row)]
    if (
        len(nonempty_rows) == 1
        and sum(bool(cell and cell.strip()) for cell in nonempty_rows[0]) == 1
    ):
        return None
    if _count_embedding(source.title, block.section_path, text, token_counter) <= config.max_tokens:
        return [
            _TextSpan(
                text=text,
                page_number=page_number,
                block_id=block.block_id,
                start_char=block.start_char + leading,
                end_char=block.start_char + leading + len(text),
                section_path=block.section_path,
                atomic=True,
            )
        ]

    rows: list[tuple[str, int, int, tuple[str | None, ...]]] = []
    cursor = 0
    exact_row_offsets = True
    for table_row in block.table_rows:
        row_text = "\t".join(cell or "" for cell in table_row).strip()
        if not row_text.strip():
            continue
        row_start = text.find(row_text, cursor)
        if row_start < 0:
            exact_row_offsets = False
            break
        row_end = row_start + len(row_text)
        rows.append((row_text, row_start, row_end, tuple(table_row)))
        cursor = row_end
    if not exact_row_offsets:
        rows = [
            (row_text, 0, len(text), tuple(table_row))
            for table_row in block.table_rows
            if (row_text := "\t".join(cell or "" for cell in table_row).strip())
        ]
    if not rows:
        return []

    header = rows[0]
    if (
        _count_embedding(source.title, block.section_path, header[0], token_counter)
        > config.max_tokens
    ):
        raise ChunkingError(
            "TABLE_HEADER_TOO_LARGE",
            f"Table header in block {block.block_id} exceeds the embedding token limit",
        )
    if any(
        _count_embedding(
            source.title,
            block.section_path,
            f"{header[0]}\n{row[0]}",
            token_counter,
        )
        > config.max_tokens
        for row in rows[1:]
    ):
        return _split_oversized_table_cells(
            source,
            page_number,
            block,
            leading,
            header[3],
            [row[3] for row in rows[1:]],
            config,
            token_counter,
        )
    groups: list[list[tuple[str, int, int, tuple[str | None, ...]]]] = []
    current = [header]
    for row_span in rows[1:]:
        candidate_text = "\n".join(item[0] for item in (*current, row_span))
        candidate_count = _count_embedding(
            source.title,
            block.section_path,
            candidate_text,
            token_counter,
        )
        if len(current) > 1 and candidate_count > config.target_tokens:
            groups.append(current)
            current = [header]
            candidate_text = f"{header[0]}\n{row_span[0]}"
            candidate_count = _count_embedding(
                source.title,
                block.section_path,
                candidate_text,
                token_counter,
            )
        if candidate_count > config.max_tokens:
            raise ChunkingError(
                "TABLE_ROW_TOO_LARGE",
                f"A logical table row in block {block.block_id} exceeds the embedding token limit",
            )
        current.append(row_span)
        if candidate_count >= config.target_tokens:
            groups.append(current)
            current = [header]
    if len(current) > 1 or not groups:
        groups.append(current)

    spans: list[_TextSpan] = []
    for group in groups:
        span_text = "\n".join(row[0] for row in group)
        spans.append(
            _TextSpan(
                text=span_text,
                page_number=page_number,
                block_id=block.block_id,
                start_char=block.start_char + leading + min(row[1] for row in group),
                end_char=block.start_char + leading + max(row[2] for row in group),
                section_path=block.section_path,
                atomic=True,
            )
        )
    return spans


def _split_block(
    source: SourceArtifact,
    page_number: int,
    block: CanonicalBlock,
    config: ChunkerConfig,
    token_counter: TokenCounter,
) -> list[_TextSpan]:
    text = block.text.strip()
    if not text:
        return []
    leading = len(block.text) - len(block.text.lstrip())
    if block.block_type == "table":
        table_spans = _split_table_block(
            source,
            page_number,
            block,
            text,
            leading,
            config,
            token_counter,
        )
        if table_spans is not None:
            return table_spans
    if _count_embedding(source.title, block.section_path, text, token_counter) <= config.max_tokens:
        return [
            _TextSpan(
                text=text,
                page_number=page_number,
                block_id=block.block_id,
                start_char=block.start_char + leading,
                end_char=block.start_char + leading + len(text),
                section_path=block.section_path,
            )
        ]

    words = list(re.finditer(r"\S+", text))
    spans: list[_TextSpan] = []
    start_word = 0
    while start_word < len(words):
        low = start_word + 1
        high = len(words)
        best_end = start_word
        while low <= high:
            candidate_end = (low + high) // 2
            candidate = text[words[start_word].start() : words[candidate_end - 1].end()]
            if (
                _count_embedding(source.title, block.section_path, candidate, token_counter)
                <= config.max_tokens
            ):
                best_end = candidate_end
                low = candidate_end + 1
            else:
                high = candidate_end - 1
        if best_end == start_word:
            raise ChunkingError(
                "TOKEN_LIMIT_UNSATISFIABLE",
                f"A word plus its title/section context exceeds {config.max_tokens} tokens",
            )
        start_offset = words[start_word].start()
        end_offset = words[best_end - 1].end()
        spans.append(
            _TextSpan(
                text=text[start_offset:end_offset],
                page_number=page_number,
                block_id=block.block_id,
                start_char=block.start_char + leading + start_offset,
                end_char=block.start_char + leading + end_offset,
                section_path=block.section_path,
            )
        )
        if best_end >= len(words):
            break
        next_start = best_end
        while config.overlap_tokens > 0 and next_start > start_word + 1:
            overlap = text[words[next_start - 1].start() : words[best_end - 1].end()]
            if token_counter.count_tokens(overlap) > config.overlap_tokens:
                break
            next_start -= 1
        start_word = max(start_word + 1, next_start)
    return spans


def _split_oversized_table_cells(
    source: SourceArtifact,
    page_number: int,
    block: CanonicalBlock,
    leading: int,
    header_cells: tuple[str | None, ...],
    rows: list[tuple[str | None, ...]],
    config: ChunkerConfig,
    token_counter: TokenCounter,
) -> list[_TextSpan]:
    spans: list[_TextSpan] = []
    block_start = block.start_char + leading
    block_end = block.start_char + leading + len(block.text.strip())
    for row_index, row in enumerate(rows):
        for cell_index, cell in enumerate(row):
            cell_text = (cell or "").strip()
            if not cell_text:
                continue
            header_value = header_cells[cell_index] if cell_index < len(header_cells) else None
            header = (
                header_value.strip()
                if isinstance(header_value, str) and header_value.strip()
                else f"Column {cell_index + 1}"
            )
            label = f"{header}: "
            prefix_tokens = _count_embedding(
                source.title,
                block.section_path,
                label,
                token_counter,
            )
            content_limit = config.max_tokens - prefix_tokens
            if content_limit < 1:
                raise ChunkingError(
                    "TABLE_HEADER_TOO_LARGE",
                    f"A table column heading in block {block.block_id} exceeds the embedding limit",
                )
            minimum = min(config.min_tokens, content_limit)
            cell_config = config.model_copy(
                update={
                    "min_tokens": minimum,
                    "target_tokens": max(minimum, min(config.target_tokens, content_limit)),
                    "max_tokens": content_limit,
                    "overlap_tokens": min(config.overlap_tokens, max(0, minimum - 1)),
                }
            )
            cell_block = CanonicalBlock(
                block_id=block.block_id,
                block_type="paragraph",
                text=cell_text,
                section_path=block.section_path,
                bbox=block.bbox,
                start_char=0,
                end_char=len(cell_text),
            )
            for fragment_index, fragment in enumerate(
                _split_block(
                    source,
                    page_number,
                    cell_block,
                    cell_config,
                    token_counter,
                )
            ):
                labelled_text = label + fragment.text
                if (
                    _count_embedding(
                        source.title,
                        block.section_path,
                        labelled_text,
                        token_counter,
                    )
                    > config.max_tokens
                ):
                    raise ChunkingError(
                        "TABLE_CELL_TOKEN_LIMIT",
                        f"A labelled table-cell fragment in block {block.block_id} "
                        "exceeds the embedding limit",
                    )
                spans.append(
                    _TextSpan(
                        text=labelled_text,
                        page_number=page_number,
                        block_id=block.block_id,
                        start_char=block_start,
                        end_char=block_end,
                        section_path=block.section_path,
                        atomic=True,
                        identity_suffix=(
                            f"table-row-{row_index}-cell-{cell_index}-fragment-{fragment_index}"
                        ),
                    )
                )
    return spans


def _overlap_tail(
    span: _TextSpan,
    overlap_tokens: int,
    token_counter: TokenCounter,
) -> _TextSpan | None:
    if overlap_tokens <= 0:
        return None
    words = list(re.finditer(r"\S+", span.text))
    if len(words) < 2:
        return None
    for start_word in range(len(words) - 1, 0, -1):
        start_offset = words[start_word].start()
        end_offset = words[-1].end()
        suffix = span.text[start_offset:end_offset]
        if token_counter.count_tokens(suffix) <= overlap_tokens:
            return _TextSpan(
                text=suffix,
                page_number=span.page_number,
                block_id=span.block_id,
                start_char=span.start_char + start_offset,
                end_char=span.start_char + end_offset,
                section_path=span.section_path,
            )
    return None


def _make_passage(
    source: SourceArtifact,
    document_id: str,
    spans: tuple[_TextSpan, ...],
    config: ChunkerConfig,
    token_counter: TokenCounter,
) -> CorpusPassage:
    text = "\n\n".join(span.text for span in spans).strip()
    section_path = spans[0].section_path
    embedding_text = _embedding_text(source.title, section_path, text)
    token_count = token_counter.count_tokens(embedding_text)
    if token_count > min(config.max_tokens, 500):
        raise ChunkingError(
            "TOKEN_LIMIT_EXCEEDED", "Passage exceeds the configured embedding token limit"
        )
    locations = tuple(
        BlockLocation(
            page_number=span.page_number,
            block_id=span.block_id,
            start_char=span.start_char,
            end_char=span.end_char,
        )
        for span in spans
    )
    text_hash = passage_text_sha256(text)
    embedding_text_hash = passage_text_sha256(embedding_text)
    identity = {
        "source_id": source.source_id,
        "source_content_sha256": source.source_content_sha256,
        "chunker_version": config.version,
        "locations": [location.model_dump(mode="json") for location in locations],
        "span_identity": [span.identity_suffix for span in spans],
        "text_sha256": text_hash,
        "embedding_text_sha256": embedding_text_hash,
    }
    passage_id = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
    return CorpusPassage(
        passage_id=passage_id,
        source_id=source.source_id,
        document_id=document_id,
        title=source.title,
        publisher=source.publisher,
        source_uri=source.source_uri,
        text=text,
        embedding_text=embedding_text,
        text_sha256=text_hash,
        embedding_text_sha256=embedding_text_hash,
        source_content_sha256=source.source_content_sha256,
        chunker_version=config.version,
        locations=locations,
        section_path=section_path,
        token_count=token_count,
        licence=source.licence,
        usage_constraints=source.usage_constraints,
        sensitivity=source.sensitivity,
        permission_scope=source.sensitivity,
        allowed_usage=source.allowed_usage,
    )


def _pack_spans(
    source: SourceArtifact,
    document_id: str,
    spans: list[_TextSpan],
    config: ChunkerConfig,
    token_counter: TokenCounter,
) -> tuple[CorpusPassage, ...]:
    passages: list[CorpusPassage] = []
    current: list[_TextSpan] = []

    def flush(*, overlap: bool = False) -> None:
        nonlocal current
        if not current:
            return
        passages.append(_make_passage(source, document_id, tuple(current), config, token_counter))
        tail = _overlap_tail(current[-1], config.overlap_tokens, token_counter) if overlap else None
        current = [tail] if tail is not None else []

    for span in spans:
        if span.atomic:
            flush()
            passages.append(_make_passage(source, document_id, (span,), config, token_counter))
            continue
        if current and span.section_path != current[-1].section_path:
            flush()
        if len(current) >= 20:
            same_section = span.section_path == current[-1].section_path
            flush(overlap=same_section)
        candidate = [*current, span]
        candidate_text = "\n\n".join(item.text for item in candidate)
        candidate_count = _count_embedding(
            source.title, span.section_path, candidate_text, token_counter
        )
        if current and candidate_count > config.target_tokens:
            same_section = span.section_path == current[-1].section_path
            flush(overlap=same_section)
            candidate = [*current, span]
            candidate_text = "\n\n".join(item.text for item in candidate)
            candidate_count = _count_embedding(
                source.title, span.section_path, candidate_text, token_counter
            )
            if candidate_count > config.max_tokens and current:
                flush()
                candidate = [span]
                candidate_text = span.text
                candidate_count = _count_embedding(
                    source.title, span.section_path, candidate_text, token_counter
                )
        if candidate_count > config.max_tokens:
            raise ChunkingError(
                "TOKEN_LIMIT_EXCEEDED", "Cannot pack passage without truncating text"
            )
        current = candidate
        if candidate_count >= config.target_tokens:
            flush(overlap=True)
    flush()
    return tuple(passages)


def chunk_report(
    source: SourceArtifact,
    document: CanonicalDocument,
    config: ChunkerConfig,
    token_counter: TokenCounter,
) -> tuple[CorpusPassage, ...]:
    _require_retrieval_source(source, "report")
    if document.source_id != source.source_id:
        raise ChunkingError(
            "SOURCE_ID_MISMATCH", "Canonical document belongs to a different source"
        )
    if document.content_sha256 != source.source_content_sha256:
        raise ChunkingError(
            "SOURCE_HASH_MISMATCH", "Canonical document hash differs from the raw source"
        )

    spans = [
        span
        for page in document.pages
        for block in page.blocks
        for span in _split_block(source, page.page_number, block, config, token_counter)
    ]
    return _pack_spans(source, document.document_id, spans, config, token_counter)


def _render_observation(
    dataset: StructuredDataset, observation_index: int
) -> tuple[str, StructuredRowKey]:
    observation = dataset.observations[observation_index]
    value = (
        "null"
        if observation.value is None
        else f"{observation.value:.{max(0, observation.decimal)}f}"
    )
    unit = observation.unit if observation.unit else "<empty>"
    status = observation.observation_status if observation.observation_status else "<empty>"
    text = "\n".join(
        (
            f"Indicator: {dataset.indicator_label} ({dataset.indicator_id})",
            f"Country: {observation.country_name} ({observation.country_iso3})",
            f"Year: {observation.year}",
            f"Value: {value}",
            f"Unit: {unit}",
            f"Observation status: {status}",
            f"Decimal precision: {observation.decimal}",
        )
    )
    key = StructuredRowKey(
        dataset_id=dataset.dataset_id,
        observation_id=observation.observation_id,
        indicator_id=dataset.indicator_id,
        country_iso3=observation.country_iso3,
        year=observation.year,
    )
    return text, key


def chunk_structured_dataset(
    source: SourceArtifact,
    dataset: StructuredDataset,
    config: ChunkerConfig,
    token_counter: TokenCounter,
) -> tuple[CorpusPassage, ...]:
    _require_retrieval_source(source, "structured")
    if dataset.source_id != source.source_id:
        raise ChunkingError("SOURCE_ID_MISMATCH", "Canonical dataset belongs to a different source")
    if dataset.content_sha256 != source.source_content_sha256:
        raise ChunkingError(
            "SOURCE_HASH_MISMATCH", "Canonical dataset hash differs from the raw source"
        )

    passages: list[CorpusPassage] = []
    section_path = (dataset.indicator_label,)
    for index, observation in enumerate(dataset.observations):
        text, row_key = _render_observation(dataset, index)
        embedding_text = _embedding_text(source.title, section_path, text)
        token_count = token_counter.count_tokens(embedding_text)
        if token_count > min(config.max_tokens, 500):
            raise ChunkingError(
                "STRUCTURED_ROW_TOKEN_LIMIT",
                f"Observation {observation.observation_id} exceeds the embedding token limit",
            )
        text_hash = passage_text_sha256(text)
        embedding_text_hash = passage_text_sha256(embedding_text)
        identity = {
            "source_id": source.source_id,
            "source_content_sha256": source.source_content_sha256,
            "chunker_version": config.version,
            "row_key": row_key.model_dump(mode="json"),
            "text_sha256": text_hash,
            "embedding_text_sha256": embedding_text_hash,
        }
        passage_id = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )
        passages.append(
            CorpusPassage(
                passage_id=passage_id,
                source_id=source.source_id,
                document_id=dataset.dataset_id,
                title=source.title,
                publisher=source.publisher,
                source_uri=source.source_uri,
                text=text,
                embedding_text=embedding_text,
                text_sha256=text_hash,
                embedding_text_sha256=embedding_text_hash,
                source_content_sha256=source.source_content_sha256,
                chunker_version=config.version,
                row_key=row_key,
                section_path=section_path,
                token_count=token_count,
                licence=source.licence,
                usage_constraints=source.usage_constraints,
                sensitivity=source.sensitivity,
                permission_scope=source.sensitivity,
                allowed_usage=source.allowed_usage,
                country_iso3=observation.country_iso3,
                year=observation.year,
                indicator_id=dataset.indicator_id,
            )
        )
    return tuple(passages)
