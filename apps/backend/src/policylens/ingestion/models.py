from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    title: str
    publisher: str
    canonical_url: str
    retrieved_at: str
    published_at: str | None
    licence: str
    usage_constraints: str | None
    sensitivity: Literal["public", "synthetic", "anonymised"]
    language: str = "en"
    sha256: str
    indicator_id: str | None = None
    countries: tuple[str, ...] = ()
    year_range: tuple[int, int] | None = None


class StructuredObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str
    country_iso2: str
    country_iso3: str
    country_name: str
    year: int
    value: float | None
    unit: str
    observation_status: str
    decimal: int


class StructuredDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    dataset_id: str
    source_id: str
    title: str
    indicator_id: str
    indicator_label: str
    country_codes: tuple[str, ...]
    year_range: tuple[int, int]
    api_metadata: dict[str, Any]
    observations: tuple[StructuredObservation, ...]
    missing_value_semantics: str
    provenance: SourceMetadata
    content_sha256: str
    parser_version: str


class CanonicalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    block_id: str
    block_type: Literal["heading", "paragraph", "list", "table", "caption", "footnote"]
    text: str
    section_path: tuple[str, ...]
    bbox: tuple[float, float, float, float] | None
    table_rows: tuple[tuple[str | None, ...], ...] | None = None
    start_char: int
    end_char: int


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: int
    blocks: tuple[CanonicalBlock, ...]


class CanonicalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    document_id: str
    source_id: str
    title: str
    content_type: Literal["policy_report"] = "policy_report"
    language: str
    pages: tuple[DocumentPage, ...]
    provenance: SourceMetadata
    content_sha256: str
    parser_version: str
