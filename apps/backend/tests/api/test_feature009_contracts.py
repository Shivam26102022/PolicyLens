from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = ROOT / "specs/009-minimal-ui/contracts"


def _schema(name: str) -> dict[str, object]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _model_options() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "default_provider": "openai",
        "embedding_provider": "local",
        "embedding_consent_required": False,
        "options": [
            {
                "provider": "openai",
                "route": "openai_responses",
                "model_id": "configured-openai-model",
                "execution_scope": "external",
                "configured": True,
                "selected_by_default": True,
                "consent_required": True,
                "reasoning_efforts": ["none", "low", "medium", "high"],
            },
            {
                "provider": "mlx",
                "route": "mlx_chat_completions",
                "model_id": None,
                "execution_scope": "loopback",
                "configured": False,
                "selected_by_default": False,
                "consent_required": False,
                "reasoning_efforts": ["none"],
            },
        ],
    }


def _evaluation_summary() -> dict[str, object]:
    return {
        "schema_version": "1.5",
        "status": "empty",
        "case_set": {
            "case_count": 0,
            "approved_case_count": 0,
            "category_count": 0,
            "category_counts": {},
            "split_counts": {"dev": 0, "test": 0},
        },
        "runs": [],
        "reviewed_case_count": 0,
        "error_record_count": 0,
    }


def test_feature009_json_schemas_are_valid() -> None:
    for path in CONTRACTS.glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_model_options_contract_accepts_configured_and_missing_models() -> None:
    Draft202012Validator(_schema("model-options.schema.json")).validate(_model_options())


@pytest.mark.parametrize(
    "update",
    [
        {"consent_required": False},
        {"execution_scope": "loopback"},
    ],
)
def test_model_options_contract_rejects_openai_scope_or_consent_mismatch(
    update: dict[str, object],
) -> None:
    payload = _model_options()
    options = payload["options"]
    assert isinstance(options, list)
    options[0] = options[0] | update

    with pytest.raises(ValidationError):
        Draft202012Validator(_schema("model-options.schema.json")).validate(payload)


def test_model_options_contract_rejects_unconfigured_model_id() -> None:
    payload = _model_options()
    options = payload["options"]
    assert isinstance(options, list)
    options[1] = options[1] | {"model_id": "made-up-model"}

    with pytest.raises(ValidationError):
        Draft202012Validator(_schema("model-options.schema.json")).validate(payload)


@pytest.mark.parametrize(
    "selection",
    [
        {"provider": "openai", "allow_external_provider": True},
        {"provider": "mlx", "allow_external_provider": False},
    ],
)
def test_provider_selection_contract_accepts_only_matching_consent(
    selection: dict[str, object],
) -> None:
    Draft202012Validator(_schema("agent-provider-selection.schema.json")).validate(selection)


@pytest.mark.parametrize(
    "selection",
    [
        {"provider": "openai", "allow_external_provider": False},
        {"provider": "mlx", "allow_external_provider": True},
    ],
)
def test_provider_selection_contract_rejects_inconsistent_consent(
    selection: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema("agent-provider-selection.schema.json")).validate(selection)


def test_evaluation_summary_contract_preserves_empty_metrics_without_raw_case_data() -> None:
    schema = _schema("evaluation-summary.schema.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(_evaluation_summary())

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(_evaluation_summary() | {"prompt": "private query"})
