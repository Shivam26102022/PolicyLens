from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from statistics import median
from typing import Any

import pymupdf

from policylens.ingestion.models import (
    CanonicalBlock,
    CanonicalDocument,
    DocumentPage,
    SourceMetadata,
)

MAX_PDF_PAGES = 2000
MIN_EXTRACTABLE_CHARACTERS = 200
HEADING_SIZE_RATIO = 1.2
MAX_HEADING_CHARACTERS = 180
REPORT_PARSER_VERSION = f"report-1.0.0-pymupdf-{pymupdf.VersionBind}"
LIST_PREFIX = re.compile(r"^\s*(?:[•●▪*-]|\d+[.)])\s+")
NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")
CAPTION_PREFIX = re.compile(r"^\s*(?:figure|table|box|chart)\s+\d+", re.IGNORECASE)


class PdfParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class _BlockCandidate:
    text: str
    bbox: tuple[float, float, float, float]
    block_type: str
    table_rows: tuple[tuple[str | None, ...], ...] | None = None


def _text_from_block(block: dict[str, Any]) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        line_text = "".join(span.get("text", "") for span in spans)
        if line_text:
            lines.append(line_text)
    return "\n".join(lines).strip()


def _box(raw_box: Any) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in raw_box)  # type: ignore[return-value]


def _overlap_ratio(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    first_x0, first_y0, first_x1, first_y1 = first
    second_x0, second_y0, second_x1, second_y1 = second
    width = max(0.0, min(first_x1, second_x1) - max(first_x0, second_x0))
    height = max(0.0, min(first_y1, second_y1) - max(first_y0, second_y0))
    first_area = max(0.0, first_x1 - first_x0) * max(0.0, first_y1 - first_y0)
    if first_area == 0:
        return 0.0
    return width * height / first_area


def _table_candidates(page: pymupdf.Page) -> list[_BlockCandidate]:
    candidates: list[_BlockCandidate] = []
    for table in page.find_tables().tables:
        rows = tuple(
            tuple(None if cell is None else str(cell).strip() for cell in row)
            for row in table.extract()
        )
        text = "\n".join("\t".join(cell or "" for cell in row) for row in rows).strip()
        if text:
            candidates.append(
                _BlockCandidate(
                    text=text,
                    bbox=_box(table.bbox),
                    block_type="table",
                    table_rows=rows,
                )
            )
    return candidates


def _classify_text_block(
    text: str,
    spans: list[dict[str, Any]],
    base_font_size: float,
) -> str:
    if CAPTION_PREFIX.match(text):
        return "caption"
    if LIST_PREFIX.match(text):
        return "list"
    max_size = max((float(span.get("size", 0)) for span in spans), default=base_font_size)
    if max_size >= base_font_size * HEADING_SIZE_RATIO and len(text) <= MAX_HEADING_CHARACTERS:
        return "heading"
    return "paragraph"


def _heading_level(text: str) -> int:
    match = NUMBERED_HEADING.match(text)
    if match is None:
        return 1
    return len(match.group(1).split("."))


def parse_pdf_report(payload: bytes, source: SourceMetadata) -> CanonicalDocument:
    content_sha256 = hashlib.sha256(payload).hexdigest()
    if content_sha256 != source.sha256:
        raise PdfParseError("CHECKSUM_MISMATCH", "Payload hash does not match source metadata")
    if not payload.startswith(b"%PDF-"):
        raise PdfParseError("INVALID_PDF", "Payload does not have a PDF signature")

    try:
        pdf = pymupdf.open(stream=payload, filetype="pdf")
    except Exception as error:
        raise PdfParseError("INVALID_PDF", "PDF structure could not be opened") from error

    try:
        if pdf.page_count < 1:
            raise PdfParseError("EMPTY_PDF", "PDF has no pages")
        if pdf.page_count > MAX_PDF_PAGES:
            raise PdfParseError("PDF_TOO_LARGE", "PDF exceeds the maximum page count")

        page_dicts = [
            pdf.load_page(page_index).get_text("dict") for page_index in range(pdf.page_count)
        ]
        font_sizes = [
            float(span.get("size", 0))
            for page_dict in page_dicts
            for block in page_dict.get("blocks", [])
            if block.get("type") == 0
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            if span.get("text", "").strip()
        ]
        if not font_sizes:
            raise PdfParseError("PDF_NO_TEXT", "PDF has no extractable text")
        if (
            sum(
                len(_text_from_block(block))
                for page_dict in page_dicts
                for block in page_dict.get("blocks", [])
                if block.get("type") == 0
            )
            < MIN_EXTRACTABLE_CHARACTERS
        ):
            raise PdfParseError("PDF_NO_TEXT", "PDF has too little extractable text")

        base_font_size = median(font_sizes)
        section_stack: list[str] = []
        document_pages: list[DocumentPage] = []
        character_offset = 0
        next_block_number = 1

        for page_index, page_dict in enumerate(page_dicts):
            page = pdf.load_page(page_index)
            page_number = page_index + 1
            candidates = _table_candidates(page)
            table_boxes = [candidate.bbox for candidate in candidates]
            for raw_block in page_dict.get("blocks", []):
                if raw_block.get("type") != 0:
                    continue
                text = _text_from_block(raw_block)
                if not text:
                    continue
                bbox = _box(raw_block["bbox"])
                if any(_overlap_ratio(bbox, table_box) >= 0.5 for table_box in table_boxes):
                    continue
                spans = [
                    span for line in raw_block.get("lines", []) for span in line.get("spans", [])
                ]
                candidates.append(
                    _BlockCandidate(
                        text=text,
                        bbox=bbox,
                        block_type=_classify_text_block(text, spans, base_font_size),
                    )
                )

            candidates.sort(key=lambda candidate: (candidate.bbox[1], candidate.bbox[0]))
            canonical_blocks: list[CanonicalBlock] = []
            for candidate in candidates:
                if candidate.block_type == "heading":
                    level = _heading_level(candidate.text)
                    del section_stack[level - 1 :]
                    section_stack.append(candidate.text)
                start_char = character_offset
                end_char = start_char + len(candidate.text)
                canonical_blocks.append(
                    CanonicalBlock(
                        block_id=f"b{next_block_number:04d}",
                        block_type=candidate.block_type,  # type: ignore[arg-type]
                        text=candidate.text,
                        section_path=tuple(section_stack),
                        bbox=candidate.bbox,
                        table_rows=candidate.table_rows,
                        start_char=start_char,
                        end_char=end_char,
                    )
                )
                character_offset = end_char + 1
                next_block_number += 1
            document_pages.append(
                DocumentPage(page_number=page_number, blocks=tuple(canonical_blocks))
            )
    except PdfParseError:
        raise
    except Exception as error:
        raise PdfParseError("PDF_PARSE_FAILED", "PDF content could not be parsed") from error
    finally:
        pdf.close()

    return CanonicalDocument(
        document_id=f"doc:{source.source_id}:{content_sha256}",
        source_id=source.source_id,
        title=source.title,
        language=source.language,
        pages=tuple(document_pages),
        provenance=source,
        content_sha256=content_sha256,
        parser_version=REPORT_PARSER_VERSION,
    )
