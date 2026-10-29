from __future__ import annotations

import hashlib
import os
import platform
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from scripts.download_data import DownloadError, load_manifest, load_source_registry, write_manifest

from policylens.ingestion.models import StructuredDataset
from policylens.ingestion.structured import STRUCTURED_PARSER_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]
YOUTH_SOURCE_ID = "wb-youth-unemployment-1524-2015-2025"
TOTAL_SOURCE_ID = "wb-total-unemployment-2015-2025"
YOUTH_INDICATOR_ID = "SL.UEM.1524.ZS"
TOTAL_INDICATOR_ID = "SL.UEM.TOTL.ZS"
OUTPUT_DIRECTORY = Path("docs/data/eda")
EDA_MANIFEST = Path("data/manifests/eda-manifest.json")
COUNTRY_COLORS = {
    "SGP": "#0072B2",
    "MYS": "#E69F00",
    "IDN": "#009E73",
    "IND": "#D55E00",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _value_index(dataset: StructuredDataset) -> dict[tuple[str, int], float | None]:
    return {
        (observation.country_iso3, observation.year): observation.value
        for observation in dataset.observations
    }


def build_eda_results(youth: StructuredDataset, total: StructuredDataset) -> dict[str, Any]:
    if youth.indicator_id != YOUTH_INDICATOR_ID or total.indicator_id != TOTAL_INDICATOR_ID:
        raise ValueError("indicator IDs do not match the youth and total unemployment series")
    if set(youth.country_codes) != set(total.country_codes):
        raise ValueError("country sets must match")
    if youth.year_range != total.year_range:
        raise ValueError("year ranges must match")

    youth_values = _value_index(youth)
    total_values = _value_index(total)
    first_year, latest_year = youth.year_range
    youth_change: list[dict[str, Any]] = []
    youth_trends: list[dict[str, Any]] = []
    latest_comparison: list[dict[str, Any]] = []

    for country_code in youth.country_codes:
        annual_values = [
            {"year": year, "value": youth_values.get((country_code, year))}
            for year in range(first_year, latest_year + 1)
        ]
        youth_trends.append({"country_iso3": country_code, "values": annual_values})

        start_value = youth_values.get((country_code, first_year))
        end_value = youth_values.get((country_code, latest_year))
        change = (
            round(end_value - start_value, 6)
            if start_value is not None and end_value is not None
            else None
        )
        youth_change.append(
            {
                "country_iso3": country_code,
                "start_year": first_year,
                "start_value": start_value,
                "end_year": latest_year,
                "end_value": end_value,
                "change_percentage_points": change,
            }
        )

        youth_rate = youth_values.get((country_code, latest_year))
        total_rate = total_values.get((country_code, latest_year))
        latest_comparison.append(
            {
                "country_iso3": country_code,
                "youth_rate": youth_rate,
                "total_rate": total_rate,
                "difference_percentage_points": (
                    round(youth_rate - total_rate, 6)
                    if youth_rate is not None and total_rate is not None
                    else None
                ),
            }
        )

    return {
        "year_range": [first_year, latest_year],
        "latest_year": latest_year,
        "country_codes": list(youth.country_codes),
        "source_hashes": {
            youth.source_id: youth.content_sha256,
            total.source_id: total.content_sha256,
        },
        "youth_trends": youth_trends,
        "youth_change": youth_change,
        "latest_comparison": latest_comparison,
    }


def _format_rate(value: float | None) -> str:
    return "NA" if value is None else f"{value:.1f}"


def _results_markdown(results: dict[str, Any]) -> str:
    start_year, end_year = results["year_range"]
    lines = [
        "# Youth Employment Descriptive Analysis",
        "",
        (
            f"Input snapshots: `{YOUTH_SOURCE_ID}` "
            f"({results['source_hashes'][YOUTH_SOURCE_ID]}) and `{TOTAL_SOURCE_ID}` "
            f"({results['source_hashes'][TOTAL_SOURCE_ID]})."
        ),
        "",
        "## 1. Youth Unemployment Trends",
        "",
        (
            f"**Question**: How did modeled youth unemployment change from {start_year} to "
            f"{end_year} in the four selected countries?"
        ),
        "",
        (
            "The line chart shows the annual youth unemployment rate (% of the labor force "
            "ages 15-24). The endpoint table reports the percentage-point change; null "
            "endpoints remain unavailable."
        ),
        "",
        f"![Annual modeled youth unemployment rates, {start_year}-{end_year}]"
        "(youth-unemployment-trends.png)",
        "",
        "| Country | Start rate (%) | End rate (%) | Change (percentage points) |",
        "|---|---:|---:|---:|",
    ]
    for item in results["youth_change"]:
        change = item["change_percentage_points"]
        change_text = "NA" if change is None else f"{change:+.1f}"
        lines.append(
            f"| {item['country_iso3']} | {_format_rate(item['start_value'])} | "
            f"{_format_rate(item['end_value'])} | {change_text} |"
        )

    lines.extend(
        [
            "",
            "## 2. Youth and Total Unemployment in the Latest Year",
            "",
            f"**Question**: How do the two modeled rates compare in {results['latest_year']}?",
            "",
            (
                "The grouped bars show distinct indicators: youth unemployment uses the labor "
                "force ages 15-24, while total unemployment uses the total labor force. Their "
                "difference is descriptive only and is not a causal estimate."
            ),
            "",
            f"![Youth and total modeled unemployment rates in {results['latest_year']}]"
            "(latest-youth-vs-total-unemployment.png)",
            "",
            "| Country | Youth rate (%) | Total rate (%) | Difference (percentage points) |",
            "|---|---:|---:|---:|",
        ]
    )
    for item in results["latest_comparison"]:
        difference = item["difference_percentage_points"]
        difference_text = "NA" if difference is None else f"{difference:+.1f}"
        lines.append(
            f"| {item['country_iso3']} | {_format_rate(item['youth_rate'])} | "
            f"{_format_rate(item['total_rate'])} | {difference_text} |"
        )

    lines.extend(
        [
            "",
            "## Caveats",
            "",
            (
                "Both series are modeled ILO estimates distributed by the World Bank and may be "
                "revised. The four countries are a selected comparison set, not a representative "
                "regional sample. The two rates have different labor-force denominators; do not "
                "interpret their difference as a causal effect or as the unemployment experience "
                "of the same population."
            ),
            "",
            "Reproduce with `make data-parse` followed by `make data-eda`. No values are imputed.",
            "",
        ]
    )
    return "\n".join(lines)


def _save_figure(figure: Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".part", dir=path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        canvas = FigureCanvasAgg(figure)
        canvas.print_png(
            temporary_path,
            metadata={"Title": path.stem.replace("-", " "), "Software": "PolicyLens"},
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
        figure.clear()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plot_youth_trends(results: dict[str, Any], output_path: Path) -> str:
    figure = Figure(figsize=(10, 5.5), constrained_layout=True)
    axis = figure.subplots()
    for series in results["youth_trends"]:
        values = series["values"]
        axis.plot(
            [item["year"] for item in values],
            [item["value"] for item in values],
            marker="o",
            linewidth=2,
            markersize=4,
            label=series["country_iso3"],
            color=COUNTRY_COLORS.get(series["country_iso3"], "#666666"),
        )
    start_year, end_year = results["year_range"]
    axis.set_title(f"Modeled youth unemployment, {start_year}-{end_year}")
    axis.set_xlabel("Year")
    axis.set_ylabel("Unemployment (% of labor force ages 15-24)")
    axis.set_xticks(range(start_year, end_year + 1, 2))
    axis.grid(axis="y", alpha=0.25)
    axis.legend(title="Country")
    return _save_figure(figure, output_path)


def _plot_latest_comparison(results: dict[str, Any], output_path: Path) -> str:
    comparison = results["latest_comparison"]
    countries = [item["country_iso3"] for item in comparison]
    positions = list(range(len(countries)))
    bar_width = 0.36
    youth_values = [item["youth_rate"] for item in comparison]
    total_values = [item["total_rate"] for item in comparison]
    figure = Figure(figsize=(9, 5.5), constrained_layout=True)
    axis = figure.subplots()
    axis.bar(
        [position - bar_width / 2 for position in positions],
        youth_values,
        bar_width,
        color="#0072B2",
        label="Youth (ages 15-24)",
    )
    axis.bar(
        [position + bar_width / 2 for position in positions],
        total_values,
        bar_width,
        color="#E69F00",
        label="Total labor force",
    )
    axis.set_title(f"Modeled unemployment rates, {results['latest_year']}")
    axis.set_xlabel("Country")
    axis.set_ylabel("Unemployment rate (%)")
    axis.set_xticks(positions, countries)
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    return _save_figure(figure, output_path)


def _load_structured_datasets(project_root: Path) -> tuple[StructuredDataset, StructuredDataset]:
    _, sources = load_source_registry(project_root / "data/manifests/sources.yaml")
    datasets: dict[str, StructuredDataset] = {}
    for source in sources:
        if not source.acquisition_enabled or source.source_kind != "structured":
            continue
        if not source.sha256:
            raise ValueError(f"Missing source checksum for {source.source_id}")
        canonical_path = (
            project_root
            / "data/canonical/structured"
            / source.source_id
            / STRUCTURED_PARSER_VERSION
            / f"{source.sha256}.json"
        )
        if not canonical_path.is_file():
            raise FileNotFoundError(
                "Canonical structured data is missing; run make data-parse first"
            )
        dataset = StructuredDataset.model_validate_json(canonical_path.read_bytes())
        if dataset.content_sha256 != source.sha256:
            raise ValueError(f"Canonical input hash does not match registry for {source.source_id}")
        datasets[source.indicator_id or ""] = dataset
    try:
        return datasets[YOUTH_INDICATOR_ID], datasets[TOTAL_INDICATOR_ID]
    except KeyError as error:
        raise ValueError("Both World Bank unemployment indicator datasets are required") from error


def _write_results(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")
    temporary_path = path.with_suffix(path.suffix + ".part")
    temporary_path.write_bytes(payload)
    os.replace(temporary_path, path)
    return hashlib.sha256(payload).hexdigest()


def run_eda(project_root: Path = PROJECT_ROOT) -> int:
    try:
        youth, total = _load_structured_datasets(project_root)
        results = build_eda_results(youth, total)
    except (DownloadError, OSError, ValueError) as error:
        print(f"ERROR EDA_INPUT_INVALID: {error}")
        return 2

    output_directory = project_root / OUTPUT_DIRECTORY
    youth_figure = output_directory / "youth-unemployment-trends.png"
    comparison_figure = output_directory / "latest-youth-vs-total-unemployment.png"
    results_path = output_directory / "results.md"
    figure_hashes = {
        youth_figure.name: _plot_youth_trends(results, youth_figure),
        comparison_figure.name: _plot_latest_comparison(results, comparison_figure),
    }
    results_hash = _write_results(results_path, _results_markdown(results))

    manifest_path = project_root / EDA_MANIFEST
    try:
        manifest = load_manifest(manifest_path)
        manifest["runs"].append(
            {
                "run_id": str(uuid.uuid4()),
                "started_at": _timestamp(),
                "finished_at": _timestamp(),
                "tool_versions": {
                    "python": platform.python_version(),
                    "matplotlib": matplotlib.__version__,
                },
                "parameters": {
                    "analysis_version": "1.0.0",
                    "latest_year": results["latest_year"],
                    "country_codes": results["country_codes"],
                },
                "inputs": results["source_hashes"],
                "outputs": {
                    results_path.name: results_hash,
                    **figure_hashes,
                },
                "status": "completed",
                "warnings": [
                    "Modeled ILO estimates may be revised.",
                    "Youth and total unemployment rates have different denominators.",
                ],
            }
        )
        write_manifest(manifest_path, manifest)
    except (DownloadError, OSError) as error:
        print(f"ERROR EDA_MANIFEST_WRITE_FAILED: {error}")
        return 1

    print(f"EDA outputs written to {OUTPUT_DIRECTORY.as_posix()}")
    return 0


def main() -> int:
    return run_eda()


if __name__ == "__main__":
    raise SystemExit(main())
