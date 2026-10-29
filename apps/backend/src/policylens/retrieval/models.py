from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EmbeddingProviderName = Literal["local", "openai"]
RetrievalMode = Literal["bm25", "dense", "hybrid"]
SourceSensitivity = Literal["public", "synthetic", "anonymised"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceArtifact(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    canonical_path: str = Field(min_length=1)
    canonical_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parser_version: str = Field(min_length=1)
    source_type: Literal["structured", "report"]
    title: str = Field(min_length=1, max_length=1000)
    publisher: str = Field(min_length=1, max_length=500)
    source_uri: str | None = None
    retrieved_at: datetime | None = None
    published_at: datetime | None = None
    licence: str = Field(min_length=1, max_length=1000)
    usage_constraints: str | None = None
    query_method: str = Field(default="model-default", min_length=1, max_length=100)
    passage_method: str = Field(default="model-default", min_length=1, max_length=100)
    sensitivity: SourceSensitivity
    allowed_usage: tuple[str, ...] = ()
    indicator_id: str | None = None
    countries: tuple[str, ...] = ()
    year_range: tuple[int, int] | None = None

    @field_validator("canonical_path")
    @classmethod
    def canonical_path_must_be_relative(cls, value: str) -> str:
        from pathlib import PurePosixPath

        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not value.startswith("data/canonical/"):
            raise ValueError("canonical_path must be below data/canonical")
        return value


class BlockLocation(StrictModel):
    page_number: int = Field(ge=1)
    block_id: str = Field(min_length=1, max_length=300)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> BlockLocation:
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class StructuredRowKey(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=500)
    observation_id: str = Field(min_length=1, max_length=500)
    indicator_id: str = Field(min_length=1, max_length=100)
    country_iso3: str = Field(pattern=r"^[A-Z]{3}$")
    year: int = Field(ge=1900, le=2100)


class CorpusPassage(StrictModel):
    passage_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=1000)
    publisher: str = Field(min_length=1, max_length=500)
    source_uri: str | None = None
    text: str = Field(min_length=1, max_length=20000)
    embedding_text: str = Field(min_length=1, max_length=24000)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    embedding_text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    chunker_version: str = Field(min_length=1, max_length=200)
    locations: tuple[BlockLocation, ...] = Field(default=(), max_length=20)
    row_key: StructuredRowKey | None = None
    section_path: tuple[str, ...] = Field(default=(), max_length=20)
    token_count: int = Field(ge=1, le=500)
    licence: str = Field(min_length=1, max_length=1000)
    usage_constraints: str | None = None
    sensitivity: SourceSensitivity
    permission_scope: str = Field(min_length=1, max_length=100)
    allowed_usage: tuple[str, ...] = ()
    country_iso3: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    year: int | None = Field(default=None, ge=1900, le=2100)
    indicator_id: str | None = None

    @model_validator(mode="after")
    def validate_content_identity(self) -> CorpusPassage:
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("text_sha256 does not match passage text")
        if (
            hashlib.sha256(self.embedding_text.encode("utf-8")).hexdigest()
            != self.embedding_text_sha256
        ):
            raise ValueError("embedding_text_sha256 does not match embedding text")
        if bool(self.locations) == (self.row_key is not None):
            raise ValueError("passage must have either block locations or one structured row key")
        if self.allowed_usage and "retrieval" not in self.allowed_usage:
            raise ValueError("passage is not allowed for retrieval")
        return self


class ChunkerConfig(StrictModel):
    strategy: Literal["fixed-size", "structure-aware"]
    version: str = Field(min_length=1, max_length=100)
    target_tokens: int = Field(ge=1, le=500)
    min_tokens: int = Field(ge=1, le=500)
    max_tokens: int = Field(ge=1, le=500)
    overlap_tokens: int = Field(ge=0, le=200)
    tokenizer: str = Field(min_length=1, max_length=200)
    keep_heading_with_body: bool = True
    preserve_lists: bool = True
    preserve_tables: bool = True
    include_section_breadcrumb: bool = True

    @model_validator(mode="after")
    def validate_token_bounds(self) -> ChunkerConfig:
        if not self.min_tokens <= self.target_tokens <= self.max_tokens:
            raise ValueError("target_tokens must be between min_tokens and max_tokens")
        if self.overlap_tokens >= self.min_tokens:
            raise ValueError("overlap_tokens must be smaller than min_tokens")
        return self


class EmbeddingDescriptor(StrictModel):
    provider: EmbeddingProviderName
    model_id: str = Field(min_length=1, max_length=300)
    package_version: str = Field(min_length=1, max_length=100)
    model_revision: str | None = None
    model_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    licence: str = Field(default="unknown", min_length=1, max_length=200)
    pooling: str = Field(default="unknown", min_length=1, max_length=200)
    tokenizer: str = Field(default="unknown", min_length=1, max_length=200)
    query_method: str = Field(default="model-default", min_length=1, max_length=100)
    passage_method: str = Field(default="model-default", min_length=1, max_length=100)
    dimension: int = Field(ge=1, le=10000)
    normalized: bool
    max_input_tokens: int = Field(ge=1, le=100000)


class IndexInput(StrictModel):
    source_id: str = Field(min_length=1)
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    canonical_path: str = Field(min_length=1)
    canonical_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parser_version: str = Field(min_length=1)


class IndexCounts(StrictModel):
    sources: int = Field(ge=0)
    documents: int = Field(ge=0)
    structured_rows: int = Field(ge=0)
    passages: int = Field(ge=0)
    chroma_records: int = Field(ge=0)
    bm25_records: int = Field(ge=0)


class IndexValidation(StrictModel):
    passed: bool
    checks: tuple[str, ...]
    smoke_case_ids: tuple[str, ...] = ()


class IndexOutputs(StrictModel):
    chroma_path: str = Field(min_length=1)
    bm25_path: str = Field(min_length=1)
    chroma_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    bm25_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class IndexBuildManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    build_id: UUID = Field(default_factory=uuid4)
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["validated", "activated", "failed"]
    started_at: datetime
    finished_at: datetime
    corpus_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    inputs: tuple[IndexInput, ...] = Field(min_length=1)
    chunker: dict[str, object]
    tokenizer: dict[str, str]
    embedding: EmbeddingDescriptor
    bm25: dict[str, object]
    counts: IndexCounts
    validation: IndexValidation
    elapsed_seconds: float | None = Field(default=None, ge=0)
    outputs: IndexOutputs
    error_code: str | None = None


class ActiveIndexReference(StrictModel):
    build_id: UUID
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_path: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ActiveIndexPointer(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    build_id: UUID
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_path: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    previous: ActiveIndexReference | None = None
    previous_validation_error: str | None = None


class RetrievalFilters(StrictModel):
    source_ids: tuple[str, ...] = Field(default=(), max_length=20)
    country_iso3: tuple[str, ...] = Field(default=(), max_length=20)
    years: tuple[int, ...] = Field(default=(), max_length=50)
    indicator_ids: tuple[str, ...] = Field(default=(), max_length=20)

    @field_validator("country_iso3")
    @classmethod
    def validate_country_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(len(value) != 3 or not value.isalpha() or not value.isupper() for value in values):
            raise ValueError("country_iso3 values must be three uppercase letters")
        return values

    @field_validator("years")
    @classmethod
    def validate_years(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if any(year < 1900 or year > 2100 for year in values):
            raise ValueError("years must be between 1900 and 2100")
        return values


class RetrievalRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    query: str = Field(min_length=1, max_length=2000)
    mode: RetrievalMode
    top_k: int = Field(default=6, ge=1, le=20)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized

    @field_validator("top_k", mode="before")
    @classmethod
    def clamp_top_k(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("top_k must be an integer")
        if isinstance(value, int):
            return min(20, max(1, value))
        return value


class RetrievedEvidence(StrictModel):
    passage_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    source_uri: str | None = None
    text: str = Field(min_length=1, max_length=20000)
    source_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    locations: tuple[BlockLocation, ...] = Field(default=(), max_length=20)
    row_key: StructuredRowKey | None = None
    section_path: tuple[str, ...] = Field(default=(), max_length=20)
    rank: int = Field(ge=1, le=20)
    score: float
    bm25_rank: int | None = Field(default=None, ge=1)
    dense_rank: int | None = Field(default=None, ge=1)
    bm25_score: float | None = None
    dense_score: float | None = None
    reranker_score: float | None = None
    retrieval_mode: RetrievalMode
    licence: str = Field(min_length=1)


class RetrievalRerankingDiagnostics(StrictModel):
    method: Literal["cross_encoder"] = "cross_encoder"
    status: Literal["completed", "failed"]
    model_id: str = Field(min_length=1, max_length=300)
    candidate_count: int = Field(ge=1, le=20)
    duration_ms: float = Field(ge=0)
    error_code: Literal["RERANKER_UNAVAILABLE", "RERANKER_INVALID_OUTPUT"] | None = None

    @model_validator(mode="after")
    def validate_status_matches_error(self) -> RetrievalRerankingDiagnostics:
        if (self.status == "failed") != (self.error_code is not None):
            raise ValueError("reranking status must match its error code")
        return self


class RetrievalRun(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID = Field(default_factory=uuid4)
    index_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["found", "no_results"]
    evidence: tuple[RetrievedEvidence, ...] = Field(max_length=20)
    context: str = Field(max_length=50000)
    reranking: RetrievalRerankingDiagnostics | None = None

    @model_validator(mode="after")
    def validate_status_matches_evidence(self) -> RetrievalRun:
        if (self.status == "found") != bool(self.evidence):
            raise ValueError("retrieval status must match whether evidence is present")
        return self


class Claim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)


class Citation(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_uri: str | None = None
    passage_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: tuple[str, ...] = Field(default=(), max_length=20)
    row_key: StructuredRowKey | None = None
    excerpt: str = Field(min_length=1, max_length=500)
    source_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    retrieval_rank: int = Field(ge=1, le=20)
    retrieval_score: float
    retrieval_mode: RetrievalMode


class CitationValidationRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    claims: tuple[Claim, ...] = Field(min_length=1, max_length=20)
    citations: tuple[Citation, ...] = Field(default=(), max_length=50)


class RejectedCitation(StrictModel):
    citation: Citation
    reason_code: Literal[
        "RUN_NOT_FOUND",
        "PASSAGE_NOT_RETURNED",
        "CLAIM_NOT_FOUND",
        "SOURCE_MISMATCH",
        "HASH_MISMATCH",
        "LOCATION_MISMATCH",
        "QUOTE_NOT_EXACT",
        "QUOTE_TOO_LONG",
        "DUPLICATE_CITATION",
    ]


class CitationValidationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    status: Literal["valid", "invalid"]
    accepted: tuple[Citation, ...]
    rejected: tuple[RejectedCitation, ...]
    uncovered_claim_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_status_matches_results(self) -> CitationValidationResult:
        if (self.status == "valid") != (not self.rejected and not self.uncovered_claim_ids):
            raise ValueError("validation status must match rejected citations")
        return self


def passage_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
