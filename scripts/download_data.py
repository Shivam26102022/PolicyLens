from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx2
import pymupdf
import yaml

TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"
USER_AGENT = "PolicyLensDataAcquirer/1.0 (public policy research corpus)"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
TRANSIENT_ERROR_NAMES = {
    "ConnectError",
    "ConnectTimeout",
    "PoolTimeout",
    "ReadError",
    "ReadTimeout",
    "RemoteProtocolError",
    "TimeoutException",
    "WriteError",
    "WriteTimeout",
}
ALLOWED_URL_PATHS = {
    "api.worldbank.org": ("/v2/country/",),
    "data.worldbank.org": ("/indicator/",),
    "www.ilo.org": ("/publications/", "/sites/default/files/"),
    "stats.mom.gov.sg": ("/Pages/", "/iMAS_PdfLibrary/"),
    "documents.worldbank.org": (
        "/en/publication/documents-reports/documentdetail/",
        "/curated/",
    ),
    "documents1.worldbank.org": ("/curated/",),
}
SENSITIVE_QUERY_NAMES = {"api_key", "key", "password", "secret", "token"}
ROOT = Path(__file__).resolve().parents[1]


class DownloadError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
        final_url: str | None = None,
        content_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.http_status = http_status
        self.final_url = final_url
        self.content_type = content_type

    def __str__(self) -> str:
        return f"{self.code}: {self.safe_message}"


@dataclass(frozen=True)
class DownloadConfig:
    max_bytes: int = DEFAULT_MAX_BYTES
    connect_timeout_seconds: float = 8.0
    read_timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0
    minimum_interval_seconds: float = 0.25
    max_redirects: int = 5
    max_pdf_pages: int = 2000
    min_pdf_text_characters: int = 200
    chunk_size: int = 64 * 1024


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    title: str
    publisher: str
    source_kind: str
    format: str
    acquisition_method: str
    canonical_url: str
    download_url: str
    expected_media_type: str
    indicator_id: str | None
    countries: tuple[str, ...]
    year_range: tuple[int, int] | None
    publication_date: str | None
    retrieved_at: str | None
    sha256: str | None
    etag: str | None
    last_modified: str | None
    parser: str
    parser_version: str
    licence: str | None
    license_review_status: str
    attribution: str
    usage_constraints: str | None
    refresh_policy: str
    sensitivity: str
    allowed_usage: tuple[str, ...]
    local_path: str
    acquisition_enabled: bool
    mandatory: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SourceDefinition:
        required = {
            "source_id",
            "title",
            "publisher",
            "source_kind",
            "format",
            "acquisition_method",
            "canonical_url",
            "download_url",
            "expected_media_type",
            "countries",
            "year_range",
            "publication_date",
            "retrieved_at",
            "sha256",
            "parser",
            "parser_version",
            "licence",
            "license_review_status",
            "attribution",
            "usage_constraints",
            "refresh_policy",
            "sensitivity",
            "allowed_usage",
            "local_path",
            "acquisition_enabled",
        }
        missing = sorted(required - set(value))
        if missing:
            raise DownloadError(
                "SOURCE_REGISTRY_INVALID",
                f"Source is missing required fields: {', '.join(missing)}",
            )

        source_id = _required_string(value, "source_id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,95}", source_id):
            raise DownloadError("SOURCE_REGISTRY_INVALID", "Source ID has invalid syntax")

        source_kind = _required_string(value, "source_kind")
        source_format = _required_string(value, "format")
        acquisition_method = _required_string(value, "acquisition_method")
        expected_media_type = _required_string(value, "expected_media_type").lower()
        if (source_kind, source_format, acquisition_method, expected_media_type) not in {
            ("structured", "json", "api", "application/json"),
            ("unstructured", "pdf", "https_download", "application/pdf"),
        }:
            raise DownloadError(
                "SOURCE_REGISTRY_INVALID",
                f"Unsupported source kind/format/method for {source_id}",
            )

        canonical_url = _required_string(value, "canonical_url")
        download_url = _required_string(value, "download_url")
        validate_official_url(canonical_url)
        validate_official_url(download_url)

        countries_value = value.get("countries")
        if not isinstance(countries_value, list) or any(
            not isinstance(country, str) or not re.fullmatch(r"[A-Z]{3}", country)
            for country in countries_value
        ):
            raise DownloadError("SOURCE_REGISTRY_INVALID", f"Invalid country list for {source_id}")

        year_range_value = value.get("year_range")
        year_range: tuple[int, int] | None
        if year_range_value is None:
            year_range = None
        elif (
            isinstance(year_range_value, list)
            and len(year_range_value) == 2
            and all(isinstance(year, int) for year in year_range_value)
            and year_range_value[0] <= year_range_value[1]
        ):
            year_range = (year_range_value[0], year_range_value[1])
        else:
            raise DownloadError("SOURCE_REGISTRY_INVALID", f"Invalid year range for {source_id}")

        allowed_usage_value = value.get("allowed_usage")
        if (
            not isinstance(allowed_usage_value, list)
            or any(
                not isinstance(usage, str) or usage not in {"retrieval", "evaluation", "statistics"}
                for usage in allowed_usage_value
            )
            or len(allowed_usage_value) != len(set(allowed_usage_value))
        ):
            raise DownloadError("SOURCE_REGISTRY_INVALID", f"Invalid allowed_usage for {source_id}")

        local_path = _required_string(value, "local_path")
        local_path_parts = PurePosixPath(local_path).parts
        expected_root = "structured" if source_kind == "structured" else "reports"
        if (
            not local_path.startswith(f"data/raw/{expected_root}/")
            or ".." in local_path_parts
            or "{sha256}" not in local_path
        ):
            raise DownloadError("SOURCE_REGISTRY_INVALID", f"Unsafe local path for {source_id}")

        license_status = _required_string(value, "license_review_status")
        if license_status not in {"verified", "manual_review_required"}:
            raise DownloadError(
                "SOURCE_REGISTRY_INVALID", f"Invalid license status for {source_id}"
            )

        licence = _optional_string(value.get("licence"))
        attribution = _required_string(value, "attribution")
        if (
            value.get("acquisition_enabled") is not True
            and value.get("acquisition_enabled") is not False
        ):
            raise DownloadError(
                "SOURCE_REGISTRY_INVALID", f"Invalid acquisition_enabled for {source_id}"
            )
        if value.get("mandatory", True) is not True and value.get("mandatory", True) is not False:
            raise DownloadError(
                "SOURCE_REGISTRY_INVALID", f"Invalid mandatory flag for {source_id}"
            )
        if value["acquisition_enabled"] and (
            license_status != "verified"
            or not licence
            or not allowed_usage_value
            or not attribution
        ):
            raise DownloadError(
                "RIGHTS_NOT_APPROVED",
                f"Enabled source {source_id} lacks verified rights or allowed usage",
            )

        return cls(
            source_id=source_id,
            title=_required_string(value, "title"),
            publisher=_required_string(value, "publisher"),
            source_kind=source_kind,
            format=source_format,
            acquisition_method=acquisition_method,
            canonical_url=canonical_url,
            download_url=download_url,
            expected_media_type=expected_media_type,
            indicator_id=_optional_string(value.get("indicator_id")),
            countries=tuple(countries_value),
            year_range=year_range,
            publication_date=_normalize_date(value.get("publication_date")),
            retrieved_at=_optional_string(value.get("retrieved_at")),
            sha256=_optional_string(value.get("sha256")),
            etag=_optional_string(value.get("etag")),
            last_modified=_optional_string(value.get("last_modified")),
            parser=_required_string(value, "parser"),
            parser_version=_required_string(value, "parser_version"),
            licence=licence,
            license_review_status=license_status,
            attribution=attribution,
            usage_constraints=_optional_string(value.get("usage_constraints")),
            refresh_policy=_required_string(value, "refresh_policy"),
            sensitivity=_required_string(value, "sensitivity"),
            allowed_usage=tuple(allowed_usage_value),
            local_path=local_path,
            acquisition_enabled=value["acquisition_enabled"],
            mandatory=value.get("mandatory", True),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "publisher": self.publisher,
            "source_kind": self.source_kind,
            "format": self.format,
            "acquisition_method": self.acquisition_method,
            "canonical_url": self.canonical_url,
            "download_url": self.download_url,
            "expected_media_type": self.expected_media_type,
            "indicator_id": self.indicator_id,
            "countries": list(self.countries),
            "year_range": list(self.year_range) if self.year_range else None,
            "publication_date": self.publication_date,
            "retrieved_at": self.retrieved_at,
            "sha256": self.sha256,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "parser": self.parser,
            "parser_version": self.parser_version,
            "licence": self.licence,
            "license_review_status": self.license_review_status,
            "attribution": self.attribution,
            "usage_constraints": self.usage_constraints,
            "refresh_policy": self.refresh_policy,
            "sensitivity": self.sensitivity,
            "allowed_usage": list(self.allowed_usage),
            "local_path": self.local_path,
            "acquisition_enabled": self.acquisition_enabled,
            "mandatory": self.mandatory,
        }


@dataclass(frozen=True)
class JsonValidationResult:
    record_count: int
    null_value_count: int
    countries: set[str]
    years: set[str]


@dataclass(frozen=True)
class PdfValidationResult:
    page_count: int
    extracted_text_characters: int


@dataclass
class RequestPacer:
    minimum_interval_seconds: float = 0.25
    sleeper: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    last_request_at: float | None = None

    def wait(self) -> None:
        if self.last_request_at is not None:
            remaining = self.minimum_interval_seconds - (self.clock() - self.last_request_at)
            if remaining > 0:
                self.sleeper(remaining)
        self.last_request_at = self.clock()


@dataclass(frozen=True)
class DownloadAttempt:
    source_id: str
    status: str
    retrieved_at: str
    http_status: int | None
    final_url: str | None
    content_type: str | None
    bytes: int | None
    sha256: str | None
    local_path: str | None
    elapsed_seconds: float
    etag: str | None = None
    last_modified: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "retrieved_at": self.retrieved_at,
            "http_status": self.http_status,
            "final_url": self.final_url,
            "content_type": self.content_type,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "local_path": self.local_path,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "etag": self.etag,
            "last_modified": self.last_modified,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


def _required_string(value: Mapping[str, Any], field_name: str) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value.strip():
        raise DownloadError("SOURCE_REGISTRY_INVALID", f"{field_name} must be a non-empty string")
    return field_value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DownloadError("SOURCE_REGISTRY_INVALID", "Optional source values must be strings")
    return value


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise DownloadError("SOURCE_REGISTRY_INVALID", "Date values must be ISO strings or null")


def validate_official_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise DownloadError(
            "URL_NOT_ALLOWED", "Source URL must be HTTPS with no embedded credentials"
        )
    if parsed.hostname not in ALLOWED_URL_PATHS:
        raise DownloadError("URL_NOT_ALLOWED", f"Host is not approved: {parsed.hostname}")
    if not any(parsed.path.startswith(prefix) for prefix in ALLOWED_URL_PATHS[parsed.hostname]):
        raise DownloadError("URL_NOT_ALLOWED", f"Path is not approved for {parsed.hostname}")
    sensitive_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if sensitive_keys & SENSITIVE_QUERY_NAMES:
        raise DownloadError("URL_NOT_ALLOWED", "Credentials are not allowed in URL query strings")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_content_type(content_type: str | None, expected: str) -> None:
    actual = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    accepted = {expected.lower()}
    if expected == "application/json":
        accepted.add("text/json")
    if actual not in accepted:
        raise DownloadError(
            "CONTENT_TYPE_INVALID",
            f"Expected {expected}, received {actual or 'no content type'}",
            content_type=content_type,
        )


def validate_json_payload(
    payload: bytes,
    source: SourceDefinition,
    *,
    content_type: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> JsonValidationResult:
    if len(payload) > max_bytes:
        raise DownloadError("FILE_TOO_LARGE", f"JSON response exceeds {max_bytes} bytes")
    if content_type is not None:
        _check_content_type(content_type, "application/json")
    try:
        response = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DownloadError("JSON_INVALID", "Response is not valid UTF-8 JSON") from error
    if not isinstance(response, list) or len(response) != 2:
        raise DownloadError(
            "JSON_STRUCTURE_INVALID", "World Bank response must contain metadata and records"
        )
    metadata, records = response
    if not isinstance(metadata, dict) or not isinstance(records, list):
        raise DownloadError(
            "JSON_STRUCTURE_INVALID", "World Bank response envelope has invalid types"
        )
    if metadata.get("page") != 1 or metadata.get("pages") != 1:
        raise DownloadError(
            "JSON_PAGINATION_UNEXPECTED", "World Bank response must fit on one page"
        )
    if metadata.get("total") != 44 or len(records) != 44:
        raise DownloadError("JSON_COVERAGE_INVALID", "Expected 44 country-year records")
    if source.indicator_id is None or source.year_range is None:
        raise DownloadError(
            "SOURCE_REGISTRY_INVALID", "Structured source lacks indicator or year range"
        )

    countries: set[str] = set()
    years: set[str] = set()
    row_keys: set[tuple[str, str]] = set()
    null_value_count = 0
    expected_years = {str(year) for year in range(source.year_range[0], source.year_range[1] + 1)}
    for record in records:
        if not isinstance(record, dict):
            raise DownloadError("JSON_STRUCTURE_INVALID", "World Bank record must be an object")
        indicator = record.get("indicator")
        if not isinstance(indicator, dict) or indicator.get("id") != source.indicator_id:
            raise DownloadError(
                "JSON_INDICATOR_MISMATCH", "World Bank response has an unexpected indicator"
            )
        country = record.get("countryiso3code")
        year = record.get("date")
        if country not in source.countries or year not in expected_years:
            raise DownloadError(
                "JSON_SCOPE_MISMATCH", "World Bank response is outside the approved scope"
            )
        row_key = (country, year)
        if row_key in row_keys:
            raise DownloadError(
                "JSON_DUPLICATE_ROW", "World Bank response contains a duplicate country-year row"
            )
        row_keys.add(row_key)
        countries.add(country)
        years.add(year)
        value = record.get("value")
        if value is None:
            null_value_count += 1
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            raise DownloadError("JSON_VALUE_INVALID", "Indicator value must be numeric or null")

    expected_pairs = {(country, year) for country in source.countries for year in expected_years}
    if row_keys != expected_pairs:
        raise DownloadError(
            "JSON_COVERAGE_INVALID", "Response does not contain every approved country-year pair"
        )
    return JsonValidationResult(len(records), null_value_count, countries, years)


def validate_pdf_payload(
    payload: bytes,
    config: DownloadConfig,
    *,
    content_type: str | None = None,
) -> PdfValidationResult:
    if len(payload) > config.max_bytes:
        raise DownloadError("FILE_TOO_LARGE", f"PDF exceeds {config.max_bytes} bytes")
    if content_type is not None:
        _check_content_type(content_type, "application/pdf")
    if not payload.startswith(b"%PDF-"):
        raise DownloadError("PDF_SIGNATURE_INVALID", "PDF does not start with the %PDF- signature")
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")
        with document:
            if document.needs_pass:
                raise DownloadError("PDF_ENCRYPTED", "Password-protected PDFs are not accepted")
            page_count = document.page_count
            if page_count < 1 or page_count > config.max_pdf_pages:
                raise DownloadError(
                    "PDF_PAGE_COUNT_INVALID", "PDF page count is outside the allowed range"
                )
            text_characters = sum(
                len(document.load_page(page_number).get_text("text").strip())
                for page_number in range(page_count)
            )
    except DownloadError:
        raise
    except Exception as error:
        raise DownloadError("PDF_INVALID", "PyMuPDF could not open the PDF structure") from error
    if text_characters < config.min_pdf_text_characters:
        raise DownloadError(
            "PDF_NO_EXTRACTABLE_TEXT", "PDF has insufficient extractable text; OCR is not enabled"
        )
    return PdfValidationResult(page_count, text_characters)


def validate_payload(
    payload: bytes,
    source: SourceDefinition,
    config: DownloadConfig,
    content_type: str | None,
) -> JsonValidationResult | PdfValidationResult:
    if len(payload) > config.max_bytes:
        raise DownloadError("FILE_TOO_LARGE", f"Response exceeds {config.max_bytes} bytes")
    if source.format == "json":
        return validate_json_payload(
            payload,
            source,
            content_type=content_type,
            max_bytes=config.max_bytes,
        )
    return validate_pdf_payload(payload, config, content_type=content_type)


def load_source_registry(path: Path) -> tuple[dict[str, Any], list[SourceDefinition]]:
    try:
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DownloadError(
            "SOURCE_REGISTRY_MISSING", "Source registry file does not exist"
        ) from error
    except yaml.YAMLError as error:
        raise DownloadError(
            "SOURCE_REGISTRY_INVALID", "Source registry is not valid YAML"
        ) from error
    if not isinstance(registry, dict) or registry.get("schema_version") != SCHEMA_VERSION:
        raise DownloadError("SOURCE_REGISTRY_INVALID", "Source registry schema_version must be 1.0")
    raw_sources = registry.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise DownloadError(
            "SOURCE_REGISTRY_INVALID", "Source registry must contain a non-empty sources list"
        )
    sources = [SourceDefinition.from_mapping(raw_source) for raw_source in raw_sources]
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise DownloadError(
            "SOURCE_REGISTRY_INVALID", "Source registry contains duplicate source IDs"
        )
    return registry, sources


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "runs": []}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DownloadError("MANIFEST_INVALID", "Download manifest is not valid JSON") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA_VERSION
        or not isinstance(manifest.get("runs"), list)
    ):
        raise DownloadError("MANIFEST_INVALID", "Download manifest has an unsupported structure")
    return manifest


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".part", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file_handle:
            file_handle.write(payload)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    payload = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    _atomic_write(path, payload)


def write_source_registry(path: Path, registry: dict[str, Any]) -> None:
    payload = yaml.safe_dump(registry, sort_keys=False, allow_unicode=True).encode("utf-8")
    _atomic_write(path, payload)


def _snapshot_path(root: Path, source: SourceDefinition, checksum: str) -> Path:
    relative = source.local_path.format(sha256=checksum)
    target = (root / relative).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise DownloadError("LOCAL_PATH_UNSAFE", "Resolved local path escapes the repository root")
    return target


def _retry_after_seconds(response: httpx2.Response, fallback: float) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after is None:
        return fallback
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        try:
            retry_time = parsedate_to_datetime(retry_after)
            if retry_time.tzinfo is None:
                retry_time = retry_time.replace(tzinfo=UTC)
            return max(0.0, (retry_time - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return fallback


def _is_transient_request_error(error: httpx2.RequestError) -> bool:
    return any(error_type.__name__ in TRANSIENT_ERROR_NAMES for error_type in type(error).mro())


def _request_response(
    source: SourceDefinition,
    client: httpx2.Client,
    config: DownloadConfig,
    pacer: RequestPacer,
    headers: dict[str, str],
    sleep: Callable[[float], None],
) -> httpx2.Response:
    for retry_number in range(config.max_retries + 1):
        current_url = source.download_url
        redirect_count = 0
        try:
            while True:
                validate_official_url(current_url)
                pacer.wait()
                request = client.build_request("GET", current_url, headers=headers)
                response = client.send(request, stream=True, follow_redirects=False)
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    response.close()
                    if not location:
                        raise DownloadError(
                            "REDIRECT_INVALID", "Redirect did not include a Location header"
                        )
                    redirect_count += 1
                    if redirect_count > config.max_redirects:
                        raise DownloadError("REDIRECT_LIMIT", "Source exceeded the redirect limit")
                    current_url = urljoin(current_url, location)
                    validate_official_url(current_url)
                    continue
                if response.status_code == 304:
                    return response
                if response.status_code in RETRYABLE_STATUSES:
                    retry_delay = min(
                        config.backoff_max_seconds,
                        config.backoff_base_seconds * (2**retry_number),
                    )
                    retry_delay = min(
                        config.backoff_max_seconds, _retry_after_seconds(response, retry_delay)
                    )
                    status_code = response.status_code
                    response.close()
                    if retry_number >= config.max_retries:
                        raise DownloadError(
                            "HTTP_STATUS",
                            f"HTTP {status_code} from {urlsplit(current_url).hostname}",
                            http_status=status_code,
                            final_url=current_url,
                        )
                    sleep(retry_delay)
                    break
                if response.status_code != 200:
                    status_code = response.status_code
                    response.close()
                    raise DownloadError(
                        "HTTP_STATUS",
                        f"HTTP {status_code} from {urlsplit(current_url).hostname}",
                        http_status=status_code,
                        final_url=current_url,
                    )
                return response
        except DownloadError:
            raise
        except httpx2.RequestError as error:
            if not _is_transient_request_error(error) or retry_number >= config.max_retries:
                raise DownloadError(
                    "NETWORK_ERROR",
                    f"{type(error).__name__} while contacting {urlsplit(current_url).hostname}",
                    final_url=current_url,
                ) from error
            retry_delay = min(
                config.backoff_max_seconds,
                config.backoff_base_seconds * (2**retry_number),
            )
            sleep(retry_delay)
    raise DownloadError("RETRIES_EXHAUSTED", "Transient retries were exhausted")


def download_source(
    source: SourceDefinition,
    project_root: Path,
    client: httpx2.Client,
    config: DownloadConfig,
    pacer: RequestPacer,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], str] | None = None,
) -> DownloadAttempt:
    start_time = clock()
    retrieved_at = now() if now is not None else utc_now()
    previous_path: Path | None = None
    if source.sha256:
        previous_path = _snapshot_path(project_root, source, source.sha256)
        if previous_path.exists() and sha256_file(previous_path) != source.sha256:
            raise DownloadError(
                "LOCAL_CHECKSUM_MISMATCH", "Existing raw snapshot failed its recorded SHA-256"
            )
        if not previous_path.exists():
            previous_path = None

    request_headers = {
        "Accept": source.expected_media_type,
        "User-Agent": USER_AGENT,
    }
    if previous_path is not None:
        if source.etag:
            request_headers["If-None-Match"] = source.etag
        elif source.last_modified:
            request_headers["If-Modified-Since"] = source.last_modified

    response = _request_response(source, client, config, pacer, request_headers, sleep)
    final_url = str(response.url)
    content_type = response.headers.get("content-type")
    etag = response.headers.get("etag") or source.etag
    last_modified = response.headers.get("last-modified") or source.last_modified
    try:
        if response.status_code == 304:
            if previous_path is None or source.sha256 is None:
                raise DownloadError(
                    "NOT_MODIFIED_WITHOUT_SNAPSHOT",
                    "Server returned 304 without a verified local snapshot",
                )
            return DownloadAttempt(
                source_id=source.source_id,
                status="unchanged",
                retrieved_at=retrieved_at,
                http_status=304,
                final_url=final_url,
                content_type=content_type,
                bytes=previous_path.stat().st_size,
                sha256=source.sha256,
                local_path=previous_path.relative_to(project_root.resolve()).as_posix(),
                elapsed_seconds=clock() - start_time,
                etag=etag,
                last_modified=last_modified,
            )

        _check_content_type(content_type, source.expected_media_type)
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > config.max_bytes:
                    raise DownloadError(
                        "FILE_TOO_LARGE", f"Response exceeds {config.max_bytes} bytes"
                    )
            except ValueError:
                pass

        download_root = _snapshot_path(project_root, source, "0" * 64).parent
        download_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{source.source_id}.", suffix=".part", dir=download_root
        )
        temporary_path = Path(temporary_name)
        byte_count = 0
        try:
            with os.fdopen(descriptor, "wb") as file_handle:
                for chunk in response.iter_bytes(chunk_size=config.chunk_size):
                    if not chunk:
                        continue
                    byte_count += len(chunk)
                    if byte_count > config.max_bytes:
                        raise DownloadError(
                            "FILE_TOO_LARGE", f"Response exceeds {config.max_bytes} bytes"
                        )
                    file_handle.write(chunk)
                file_handle.flush()
                os.fsync(file_handle.fileno())

            payload = temporary_path.read_bytes()
            validate_payload(payload, source, config, content_type)
            checksum = sha256_bytes(payload)
            if previous_path is not None and checksum == source.sha256:
                temporary_path.unlink(missing_ok=True)
                return DownloadAttempt(
                    source_id=source.source_id,
                    status="unchanged",
                    retrieved_at=retrieved_at,
                    http_status=200,
                    final_url=final_url,
                    content_type=content_type,
                    bytes=byte_count,
                    sha256=checksum,
                    local_path=previous_path.relative_to(project_root.resolve()).as_posix(),
                    elapsed_seconds=clock() - start_time,
                    etag=etag,
                    last_modified=last_modified,
                )

            final_path = _snapshot_path(project_root, source, checksum)
            if final_path.exists():
                if sha256_file(final_path) != checksum:
                    raise DownloadError(
                        "LOCAL_CHECKSUM_MISMATCH",
                        "Content-addressed path contains unexpected bytes",
                    )
                temporary_path.unlink(missing_ok=True)
                status = "unchanged"
            else:
                os.replace(temporary_path, final_path)
                status = "downloaded"
            return DownloadAttempt(
                source_id=source.source_id,
                status=status,
                retrieved_at=retrieved_at,
                http_status=200,
                final_url=final_url,
                content_type=content_type,
                bytes=byte_count,
                sha256=checksum,
                local_path=final_path.relative_to(project_root.resolve()).as_posix(),
                elapsed_seconds=clock() - start_time,
                etag=etag,
                last_modified=last_modified,
            )
        finally:
            temporary_path.unlink(missing_ok=True)
    except DownloadError as error:
        if error.http_status is None:
            error.http_status = response.status_code
        if error.final_url is None:
            error.final_url = final_url
        if error.content_type is None:
            error.content_type = content_type
        raise
    finally:
        response.close()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _script_sha256() -> str:
    return sha256_file(Path(__file__).resolve())


def _tool_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "httpx2": httpx2.__version__,
        "pymupdf": pymupdf.__version__,
        "pyyaml": yaml.__version__,
    }


def _failure_attempt(
    source: SourceDefinition,
    error: DownloadError,
    retrieved_at: str,
    elapsed_seconds: float,
) -> DownloadAttempt:
    return DownloadAttempt(
        source_id=source.source_id,
        status="failed",
        retrieved_at=retrieved_at,
        http_status=error.http_status,
        final_url=error.final_url,
        content_type=error.content_type,
        bytes=None,
        sha256=None,
        local_path=None,
        elapsed_seconds=elapsed_seconds,
        error_code=error.code,
        error_message=error.safe_message,
    )


def _write_registry_attempt(
    registry: dict[str, Any],
    source: SourceDefinition,
    attempt: DownloadAttempt,
    registry_path: Path,
) -> None:
    raw_sources = registry["sources"]
    for index, raw_source in enumerate(raw_sources):
        if raw_source.get("source_id") != source.source_id:
            continue
        updated = source.to_mapping()
        updated["retrieved_at"] = attempt.retrieved_at
        if attempt.status in {"downloaded", "unchanged"} and attempt.sha256:
            updated["sha256"] = attempt.sha256
        if attempt.etag:
            updated["etag"] = attempt.etag
        if attempt.last_modified:
            updated["last_modified"] = attempt.last_modified
        raw_sources[index] = updated
        write_source_registry(registry_path, registry)
        return
    raise DownloadError(
        "SOURCE_REGISTRY_INVALID", f"Source disappeared from registry: {source.source_id}"
    )


def run_fetch(
    project_root: Path,
    config: DownloadConfig,
    *,
    client: httpx2.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = utc_now,
) -> int:
    registry_path = project_root / "data/manifests/sources.yaml"
    manifest_path = project_root / "data/manifests/download-manifest.json"
    try:
        registry, sources = load_source_registry(registry_path)
        manifest = load_manifest(manifest_path)
    except DownloadError as error:
        print(f"ERROR {error.code}: {error.safe_message}", file=sys.stderr)
        return 2

    run_record: dict[str, Any] = {
        "run_id": str(uuid.uuid4()),
        "started_at": now(),
        "finished_at": None,
        "tool_version": TOOL_VERSION,
        "tool_versions": _tool_versions(),
        "git_commit": None,
        "script_sha256": _script_sha256(),
        "attempts": [],
    }
    manifest["runs"].append(run_record)
    manifest["schema_version"] = SCHEMA_VERSION
    write_manifest(manifest_path, manifest)

    owned_client = client is None
    if client is None:
        timeout = httpx2.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=config.read_timeout_seconds,
            pool=config.connect_timeout_seconds,
        )
        client = httpx2.Client(timeout=timeout, follow_redirects=False)
    pacer = RequestPacer(config.minimum_interval_seconds, sleeper=sleep)
    mandatory_failure = False
    try:
        for source in sources:
            if not source.acquisition_enabled:
                print(f"{source.source_id}: skipped (disabled; {source.license_review_status})")
                continue
            retrieved_at = now()
            started = time.monotonic()
            if source.license_review_status != "verified" or not source.licence:
                rights_error = DownloadError(
                    "RIGHTS_NOT_APPROVED",
                    "Source has no verified licence; no request was made",
                )
                attempt = _failure_attempt(
                    source, rights_error, retrieved_at, time.monotonic() - started
                )
            else:
                try:
                    attempt = download_source(
                        source,
                        project_root,
                        client,
                        config,
                        pacer,
                        sleep=sleep,
                        now=lambda: retrieved_at,
                    )
                except DownloadError as download_error:
                    attempt = _failure_attempt(
                        source, download_error, retrieved_at, time.monotonic() - started
                    )
            _write_registry_attempt(registry, source, attempt, registry_path)
            run_record["attempts"].append(attempt.to_mapping())
            run_record["finished_at"] = now()
            write_manifest(manifest_path, manifest)
            if attempt.status == "failed":
                print(f"{source.source_id}: failed ({attempt.error_code}: {attempt.error_message})")
                mandatory_failure = mandatory_failure or source.mandatory
            else:
                print(
                    f"{source.source_id}: {attempt.status} ({attempt.bytes} bytes, "
                    f"sha256={attempt.sha256})"
                )
    finally:
        if owned_client:
            client.close()

    run_record["finished_at"] = now()
    write_manifest(manifest_path, manifest)
    return 1 if mandatory_failure else 0


def run_verify(project_root: Path) -> int:
    registry_path = project_root / "data/manifests/sources.yaml"
    manifest_path = project_root / "data/manifests/download-manifest.json"
    try:
        _, sources = load_source_registry(registry_path)
        manifest = load_manifest(manifest_path)
    except DownloadError as error:
        print(f"ERROR {error.code}: {error.safe_message}", file=sys.stderr)
        return 2

    successful_attempts = {
        (attempt.get("source_id"), attempt.get("sha256"))
        for run_record in manifest["runs"]
        if isinstance(run_record, dict)
        for attempt in run_record.get("attempts", [])
        if isinstance(attempt, dict) and attempt.get("status") in {"downloaded", "unchanged"}
    }
    failures = 0
    config = DownloadConfig()
    for source in sources:
        if not source.acquisition_enabled:
            continue
        if not source.sha256:
            print(f"{source.source_id}: missing successful checksum")
            failures += 1
            continue
        path = _snapshot_path(project_root, source, source.sha256)
        try:
            if not path.is_file() or sha256_file(path) != source.sha256:
                raise DownloadError(
                    "LOCAL_CHECKSUM_MISMATCH", "Local raw snapshot is missing or changed"
                )
            if (source.source_id, source.sha256) not in successful_attempts:
                raise DownloadError(
                    "MANIFEST_ENTRY_MISSING", "No successful matching manifest attempt exists"
                )
            validate_payload(path.read_bytes(), source, config, source.expected_media_type)
        except (DownloadError, OSError) as error:
            code = error.code if isinstance(error, DownloadError) else "LOCAL_FILE_ERROR"
            message = (
                error.safe_message
                if isinstance(error, DownloadError)
                else "Unable to read local snapshot"
            )
            print(f"{source.source_id}: failed ({code}: {message})")
            failures += 1
        else:
            print(
                f"{source.source_id}: verified ({path.stat().st_size} bytes, "
                f"sha256={source.sha256})"
            )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire approved PolicyLens raw data sources.")
    parser.add_argument("command", nargs="?", choices=("fetch", "verify"), default="fetch")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--connect-timeout", type=float, default=8.0)
    parser.add_argument("--read-timeout", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--minimum-interval", type=float, default=0.25)
    arguments = parser.parse_args(argv)
    config = DownloadConfig(
        max_bytes=arguments.max_bytes,
        connect_timeout_seconds=arguments.connect_timeout,
        read_timeout_seconds=arguments.read_timeout,
        max_retries=arguments.max_retries,
        minimum_interval_seconds=arguments.minimum_interval,
    )
    if arguments.max_bytes < 1 or arguments.max_retries < 0 or arguments.minimum_interval < 0:
        parser.error(
            "max-bytes must be positive; retries and minimum-interval must be non-negative"
        )
    if arguments.command == "verify":
        return run_verify(arguments.root.resolve())
    return run_fetch(arguments.root.resolve(), config)


if __name__ == "__main__":
    raise SystemExit(main())
