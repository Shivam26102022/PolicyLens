from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
import pymupdf
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from scripts.download_data import (
    DownloadConfig,
    DownloadError,
    RequestPacer,
    SourceDefinition,
    download_source,
    load_manifest,
    sha256_bytes,
    validate_json_payload,
    validate_pdf_payload,
    write_manifest,
)

COUNTRIES = ("SGP", "MYS", "IDN", "IND")
YEARS = tuple(str(year) for year in range(2015, 2026))
INDICATOR = "SL.UEM.1524.ZS"


def make_source(**overrides: Any) -> SourceDefinition:
    raw: dict[str, Any] = {
        "source_id": "worldbank-youth-test",
        "title": "Youth unemployment test source",
        "publisher": "International Labour Organization via World Bank Data",
        "source_kind": "structured",
        "format": "json",
        "acquisition_method": "api",
        "canonical_url": "https://data.worldbank.org/indicator/SL.UEM.1524.ZS",
        "download_url": (
            "https://api.worldbank.org/v2/country/SGP;MYS;IDN;IND/indicator/"
            "SL.UEM.1524.ZS?date=2015:2025&format=json&per_page=1000"
        ),
        "expected_media_type": "application/json",
        "indicator_id": INDICATOR,
        "countries": list(COUNTRIES),
        "year_range": [2015, 2025],
        "publication_date": None,
        "retrieved_at": None,
        "sha256": None,
        "etag": None,
        "last_modified": None,
        "parser": "worldbank-json-validation",
        "parser_version": "1.0",
        "licence": "CC BY 4.0",
        "license_review_status": "verified",
        "attribution": "Attribute ILOSTAT and World Bank Data; state changes.",
        "usage_constraints": "Public modeled estimates; values may be revised.",
        "refresh_policy": "manual",
        "sensitivity": "public",
        "allowed_usage": ["retrieval", "evaluation"],
        "local_path": "data/raw/structured/worldbank-youth-test/{sha256}.json",
        "acquisition_enabled": True,
        "mandatory": True,
    }
    raw.update(overrides)
    return SourceDefinition.from_mapping(raw)


def test_statistics_usage_is_explicit_and_limited_to_approved_indicators() -> None:
    root = Path(__file__).resolve().parents[2]
    registry = yaml.safe_load((root / "data/manifests/sources.yaml").read_text(encoding="utf-8"))
    schema = json.loads(
        (root / "specs/002-corpus-ingestion/contracts/sources.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(registry)
    statistics_sources = {
        source["source_id"]
        for source in registry["sources"]
        if "statistics" in source["allowed_usage"]
    }

    assert statistics_sources == {
        "wb-youth-unemployment-1524-2015-2025",
        "wb-total-unemployment-2015-2025",
    }


def test_runtime_source_parser_accepts_only_declared_statistics_permission() -> None:
    source = make_source(allowed_usage=["retrieval", "statistics"])

    assert source.allowed_usage == ("retrieval", "statistics")

    with pytest.raises(DownloadError, match="Invalid allowed_usage"):
        make_source(allowed_usage=["retrieval", "write"])


def make_api_payload(
    *, indicator_id: str = INDICATOR, value_for: tuple[str, str] = ("SGP", "2025")
) -> bytes:
    records = [
        {
            "indicator": {"id": indicator_id, "value": "Youth unemployment"},
            "country": {"id": "XX", "value": "Test"},
            "countryiso3code": country,
            "date": year,
            "value": 7.4 if (country, year) == value_for else None,
            "unit": "",
            "obs_status": "",
            "decimal": 1,
        }
        for country in COUNTRIES
        for year in YEARS
    ]
    return json.dumps([{"page": 1, "pages": 1, "per_page": 1000, "total": 44}, records]).encode()


def make_pdf(*, with_text: bool = True) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    if with_text:
        for line_number in range(10):
            page.insert_text(
                (72, 72 + line_number * 24),
                "Youth employment findings, methodology, and policy recommendations.",
            )
    payload = document.tobytes()
    document.close()
    return payload


def test_acq_002_03_source_host_must_be_allowlisted() -> None:
    with pytest.raises(DownloadError, match="URL_NOT_ALLOWED"):
        make_source(download_url="https://unapproved.example/data.json")


def test_acq_002_04_request_pacer_enforces_minimum_interval() -> None:
    current_time = [10.0]
    sleep_calls: list[float] = []

    def clock() -> float:
        return current_time[0]

    def sleep_for(duration: float) -> None:
        sleep_calls.append(duration)
        current_time[0] += duration

    pacer = RequestPacer(minimum_interval_seconds=0.25, sleeper=sleep_for, clock=clock)
    pacer.wait()
    current_time[0] += 0.1
    pacer.wait()

    assert sleep_calls == [pytest.approx(0.15)]


def test_acq_002_05_checksum_generation_is_stable() -> None:
    payload = b"PolicyLens raw source"

    assert sha256_bytes(payload) == sha256_bytes(payload)
    assert len(sha256_bytes(payload)) == 64


def test_acq_002_05_world_bank_json_validation_preserves_null_rows() -> None:
    payload = make_api_payload()

    result = validate_json_payload(payload, make_source())

    assert result.record_count == 44
    assert result.null_value_count == 43
    assert result.countries == set(COUNTRIES)
    assert result.years == set(YEARS)


def test_acq_002_05_malformed_json_is_rejected() -> None:
    with pytest.raises(DownloadError, match="JSON_INVALID"):
        validate_json_payload(b"{not json", make_source())


def test_acq_002_05_json_with_wrong_indicator_is_rejected() -> None:
    with pytest.raises(DownloadError, match="JSON_INDICATOR_MISMATCH"):
        validate_json_payload(make_api_payload(indicator_id="SL.UEM.TOTL.ZS"), make_source())


def test_acq_002_05_pdf_signature_and_extractable_text_are_validated() -> None:
    result = validate_pdf_payload(make_pdf(), DownloadConfig())

    assert result.page_count == 1
    assert result.extracted_text_characters > 200


def test_acq_002_05_malformed_pdf_is_rejected() -> None:
    with pytest.raises(DownloadError, match="PDF_SIGNATURE_INVALID"):
        validate_pdf_payload(b"not a pdf", DownloadConfig())


def test_acq_002_05_scanned_only_pdf_is_rejected_without_ocr() -> None:
    with pytest.raises(DownloadError, match="PDF_NO_EXTRACTABLE_TEXT"):
        validate_pdf_payload(make_pdf(with_text=False), DownloadConfig())


def test_acq_002_05_file_size_limit_is_enforced() -> None:
    with pytest.raises(DownloadError, match="FILE_TOO_LARGE"):
        validate_json_payload(make_api_payload(), make_source(), max_bytes=20)


def test_acq_002_05_invalid_content_type_is_rejected() -> None:
    with pytest.raises(DownloadError, match="CONTENT_TYPE_INVALID"):
        validate_json_payload(
            make_api_payload(), make_source(), content_type="text/html", max_bytes=100_000
        )


def test_acq_002_06_partial_download_is_removed_after_size_failure(tmp_path: Path) -> None:
    source = make_source()
    payload = make_api_payload()

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "application/json"},
            stream=ChunkStream([payload[:100], payload[100:]]),
        )

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises(DownloadError, match="FILE_TOO_LARGE"):
            download_source(
                source,
                tmp_path,
                client,
                DownloadConfig(max_bytes=120),
                RequestPacer(minimum_interval_seconds=0),
                sleep=lambda _: None,
            )
    finally:
        client.close()

    assert list(tmp_path.rglob("*.part")) == []
    assert list(tmp_path.rglob("*.json")) == []


class ChunkStream(httpx2.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def test_acq_002_08_manifest_is_written_atomically(tmp_path: Path) -> None:
    manifest_path = tmp_path / "download-manifest.json"
    manifest = {"schema_version": "1.0", "runs": []}

    write_manifest(manifest_path, manifest)

    assert load_manifest(manifest_path) == manifest
    assert list(tmp_path.glob("*.part")) == []


def test_acq_002_07_conditional_not_modified_reuses_verified_snapshot(tmp_path: Path) -> None:
    last_modified = "Sat, 24 Oct 2026 00:00:00 GMT"
    source = make_source(
        retrieved_at="2026-10-24T00:00:00Z",
        sha256=sha256_bytes(make_api_payload()),
        last_modified=last_modified,
    )
    snapshot = tmp_path / source.local_path.format(sha256=source.sha256)
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(make_api_payload())
    observed_conditionals: list[str | None] = []
    observed_user_agents: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed_conditionals.append(request.headers.get("if-modified-since"))
        observed_user_agents.append(request.headers.get("user-agent"))
        return httpx2.Response(304, headers={"last-modified": last_modified})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        result = download_source(
            source,
            tmp_path,
            client,
            DownloadConfig(),
            RequestPacer(minimum_interval_seconds=0),
            sleep=lambda _: None,
        )
    finally:
        client.close()

    assert result.status == "unchanged"
    assert result.sha256 == source.sha256
    assert observed_conditionals == [last_modified]
    assert observed_user_agents[0] is not None
    assert observed_user_agents[0].startswith("PolicyLensDataAcquirer/")
    assert snapshot.read_bytes() == make_api_payload()


def test_acq_002_03_redirect_to_unapproved_host_is_rejected(tmp_path: Path) -> None:
    source = make_source()
    calls = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(302, headers={"location": "https://unapproved.example/data.json"})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises(DownloadError, match="URL_NOT_ALLOWED"):
            download_source(
                source,
                tmp_path,
                client,
                DownloadConfig(minimum_interval_seconds=0),
                RequestPacer(minimum_interval_seconds=0),
                sleep=lambda _: None,
            )
    finally:
        client.close()

    assert calls == 1


def test_acq_002_02_changed_snapshot_does_not_overwrite_previous_file(tmp_path: Path) -> None:
    old_payload = make_api_payload()
    new_payload = make_api_payload(value_for=("MYS", "2025"))
    source = make_source(
        retrieved_at="2026-10-24T00:00:00Z",
        sha256=sha256_bytes(old_payload),
    )
    old_path = tmp_path / source.local_path.format(sha256=source.sha256)
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(old_payload)

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, headers={"content-type": "application/json"}, content=new_payload
        )

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        result = download_source(
            source,
            tmp_path,
            client,
            DownloadConfig(),
            RequestPacer(minimum_interval_seconds=0),
            sleep=lambda _: None,
        )
    finally:
        client.close()

    new_path = tmp_path / source.local_path.format(sha256=result.sha256)
    assert result.sha256 == sha256_bytes(new_payload)
    assert new_path != old_path
    assert old_path.read_bytes() == old_payload
    assert new_path.read_bytes() == new_payload


def test_acq_002_08_successful_fetch_updates_registry_and_manifest(tmp_path: Path) -> None:
    from scripts.download_data import run_fetch

    source = make_source()
    sources_path = tmp_path / "data/manifests/sources.yaml"
    sources_path.parent.mkdir(parents=True)
    sources_path.write_text(
        yaml.safe_dump({"schema_version": "1.0", "sources": [source.to_mapping()]}),
        encoding="utf-8",
    )
    payload = make_api_payload()
    observed_user_agents: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed_user_agents.append(request.headers.get("user-agent"))
        return httpx2.Response(
            200,
            headers={
                "content-type": "application/json; charset=utf-8",
                "last-modified": "Sun, 25 Oct 2026 10:00:00 GMT",
                "etag": '"worldbank-test"',
            },
            content=payload,
        )

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        result = run_fetch(
            tmp_path,
            DownloadConfig(minimum_interval_seconds=0),
            client=client,
            sleep=lambda _: None,
            now=lambda: "2026-10-25T10:00:00Z",
        )
    finally:
        client.close()

    updated_registry = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    updated_source = updated_registry["sources"][0]
    manifest = load_manifest(tmp_path / "data/manifests/download-manifest.json")
    attempt = manifest["runs"][-1]["attempts"][0]
    raw_path = tmp_path / attempt["local_path"]
    assert result == 0
    assert observed_user_agents[0] is not None
    assert observed_user_agents[0].startswith("PolicyLensDataAcquirer/")
    assert updated_source["retrieved_at"] == "2026-10-25T10:00:00Z"
    assert updated_source["sha256"] == sha256_bytes(payload)
    assert updated_source["etag"] == '"worldbank-test"'
    assert attempt["status"] == "downloaded"
    assert attempt["bytes"] == len(payload)
    assert attempt["sha256"] == sha256_bytes(payload)
    assert raw_path.read_bytes() == payload


def test_acq_002_04_transient_server_error_is_retried(tmp_path: Path) -> None:
    from scripts.download_data import run_fetch

    source = make_source()
    sources_path = tmp_path / "data/manifests/sources.yaml"
    sources_path.parent.mkdir(parents=True)
    sources_path.write_text(
        yaml.safe_dump({"schema_version": "1.0", "sources": [source.to_mapping()]}),
        encoding="utf-8",
    )
    calls = 0
    payload = make_api_payload()

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(503, headers={"retry-after": "0"}, content=b"busy")
        return httpx2.Response(200, headers={"content-type": "application/json"}, content=payload)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        result = run_fetch(
            tmp_path,
            DownloadConfig(max_retries=1, backoff_base_seconds=0, minimum_interval_seconds=0),
            client=client,
            sleep=lambda _: None,
            now=lambda: "2026-10-25T10:00:00Z",
        )
    finally:
        client.close()

    manifest = load_manifest(tmp_path / "data/manifests/download-manifest.json")
    assert result == 0
    assert calls == 2
    assert manifest["runs"][-1]["attempts"][0]["status"] == "downloaded"


def test_acq_002_10_manual_review_source_is_never_requested(tmp_path: Path) -> None:
    from scripts.download_data import run_fetch

    manual_source = make_source(
        source_id="wb-india-manual-review",
        title="India report pending rights review",
        publisher="World Bank Group",
        source_kind="unstructured",
        format="pdf",
        acquisition_method="https_download",
        canonical_url="https://documents.worldbank.org/en/publication/documents-reports/documentdetail/798601468034846280",
        download_url="https://documents1.worldbank.org/curated/en/798601468034846280/report.pdf",
        expected_media_type="application/pdf",
        indicator_id=None,
        countries=["IND"],
        year_range=None,
        parser="pymupdf",
        licence=None,
        license_review_status="manual_review_required",
        attribution="Not approved pending review.",
        usage_constraints="Manual review required.",
        allowed_usage=[],
        local_path="data/raw/reports/wb-india-manual-review/{sha256}.pdf",
        acquisition_enabled=False,
        mandatory=False,
    )
    sources_path = tmp_path / "data/manifests/sources.yaml"
    sources_path.parent.mkdir(parents=True)
    sources_path.write_text(
        yaml.safe_dump({"schema_version": "1.0", "sources": [manual_source.to_mapping()]}),
        encoding="utf-8",
    )
    calls = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(500)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        result = run_fetch(
            tmp_path,
            DownloadConfig(minimum_interval_seconds=0),
            client=client,
            sleep=lambda _: None,
        )
    finally:
        client.close()

    manifest = load_manifest(tmp_path / "data/manifests/download-manifest.json")
    assert result == 0
    assert calls == 0
    assert manifest["runs"][-1]["attempts"] == []


def test_acq_002_09_failed_mandatory_source_returns_nonzero_and_is_not_downloaded(
    tmp_path: Path,
) -> None:
    from scripts.download_data import run_fetch

    sources_path = tmp_path / "data/manifests/sources.yaml"
    sources_path.parent.mkdir(parents=True)
    sources_path.write_text(
        yaml.safe_dump({"schema_version": "1.0", "sources": [make_source().to_mapping()]}),
        encoding="utf-8",
    )
    calls = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(503, headers={"content-type": "text/plain"}, content=b"unavailable")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    try:
        result = run_fetch(
            tmp_path,
            DownloadConfig(max_retries=1, backoff_base_seconds=0),
            client=client,
            sleep=lambda _: None,
        )
    finally:
        client.close()

    manifest = load_manifest(tmp_path / "data/manifests/download-manifest.json")
    attempts = manifest["runs"][-1]["attempts"]
    assert result == 1
    assert calls == 2
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["error_code"] == "HTTP_STATUS"
    assert not list((tmp_path / "data/raw").rglob("*.json"))
