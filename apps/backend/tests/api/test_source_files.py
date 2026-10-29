from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl, TypeAdapter

from policylens.api.app import create_app
from policylens.conversations.store import ConversationStore
from policylens.settings import AppSettings


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr("policylens.api.source_files.PROJECT_ROOT", tmp_path)
    settings = AppSettings(
        model_provider="mlx",
        mlx_model="test-model",
        frontend_origin=TypeAdapter(AnyHttpUrl).validate_python("http://localhost:5173"),
    )
    app = create_app(
        settings=settings,
        conversation_store=ConversationStore(tmp_path / "conversations.sqlite3"),
    )
    return TestClient(app)


def _write_registry(
    root: Path,
    *,
    source_id: str = "wb-test-report",
    stored_content: bytes = b"%PDF-1.7\nsynthetic local report\n",
    expected_content: bytes | None = None,
    acquisition_enabled: bool = True,
    license_review_status: str = "verified",
    allowed_usage: list[str] | None = None,
    local_path: str | None = None,
) -> None:
    expected_hash = hashlib.sha256(expected_content or stored_content).hexdigest()
    relative_path = f"data/raw/reports/{source_id}/{expected_hash}.pdf"
    raw_path = root / relative_path
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(stored_content)

    source = {
        "source_id": source_id,
        "title": "Synthetic report",
        "source_kind": "unstructured",
        "format": "pdf",
        "canonical_url": "https://example.test/report",
        "download_url": "https://example.test/report.pdf",
        "sha256": expected_hash,
        "license_review_status": license_review_status,
        "sensitivity": "public",
        "allowed_usage": allowed_usage if allowed_usage is not None else ["retrieval"],
        "local_path": local_path
        if local_path is not None
        else relative_path.replace(expected_hash, "{sha256}"),
        "acquisition_enabled": acquisition_enabled,
    }
    registry_path = root / "data/manifests/sources.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing_sources: list[dict[str, object]] = []
    if registry_path.is_file():
        existing_sources = json.loads(registry_path.read_text(encoding="utf-8"))["sources"]
    sources = [item for item in existing_sources if item.get("source_id") != source_id]
    sources.append(source)
    registry_path.write_text(
        json.dumps({"schema_version": "1.0", "sources": sources}),
        encoding="utf-8",
    )


def test_source_pdf_route_serves_only_the_verified_local_pdf_inline(
    tmp_path: Path, monkeypatch
) -> None:
    pdf_content = b"%PDF-1.7\nsynthetic local report\n"
    _write_registry(tmp_path, stored_content=pdf_content)

    with _client(tmp_path, monkeypatch) as client:
        response = client.get(
            "/sources/wb-test-report/pdf",
            headers={"Origin": "http://localhost:5173"},
        )
        ranged = client.get(
            "/sources/wb-test-report/pdf",
            headers={
                "Origin": "http://localhost:5173",
                "Range": "bytes=0-5",
            },
        )
        openapi = client.get("/openapi.json").json()

    assert response.status_code == 200
    assert response.content == pdf_content
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('inline; filename="source.pdf"')
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers.get("x-frame-options") is None
    assert ranged.status_code == 206
    assert ranged.content == pdf_content[:6]
    assert ranged.headers["content-range"] == f"bytes 0-5/{len(pdf_content)}"
    assert (
        "application/pdf"
        in openapi["paths"]["/sources/{source_id}/pdf"]["get"]["responses"]["200"]["content"]
    )


def test_source_pdf_route_does_not_serve_unapproved_or_unknown_sources(
    tmp_path: Path, monkeypatch
) -> None:
    _write_registry(
        tmp_path,
        source_id="unapproved-report",
        acquisition_enabled=False,
    )

    with _client(tmp_path, monkeypatch) as client:
        unapproved = client.get("/sources/unapproved-report/pdf")
        unknown = client.get("/sources/unknown-report/pdf")

    assert unapproved.status_code == 404
    assert unapproved.json()["error_code"] == "SOURCE_NOT_FOUND"
    assert unknown.status_code == 404
    assert unknown.json()["error_code"] == "SOURCE_NOT_FOUND"


def test_source_pdf_route_rejects_unreviewed_paths_and_hash_mismatches(
    tmp_path: Path, monkeypatch
) -> None:
    _write_registry(
        tmp_path,
        source_id="path-traversal-report",
        local_path="../../outside.pdf",
    )
    _write_registry(
        tmp_path,
        source_id="changed-report",
        stored_content=b"%PDF-1.7\nchanged\n",
        expected_content=b"%PDF-1.7\nexpected\n",
    )

    with _client(tmp_path, monkeypatch) as client:
        unsafe_path = client.get("/sources/path-traversal-report/pdf")
        changed_file = client.get("/sources/changed-report/pdf")

    assert unsafe_path.status_code == 503
    assert unsafe_path.json()["error_code"] == "SOURCE_FILE_UNAVAILABLE"
    assert changed_file.status_code == 503
    assert changed_file.json()["error_code"] == "SOURCE_FILE_UNAVAILABLE"
