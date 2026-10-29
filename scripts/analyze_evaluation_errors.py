from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from scripts.evaluation_errors import (
    DEFAULT_ERROR_MANIFEST,
    DEFAULT_ERROR_REPORT,
    EvaluationErrorStoreError,
    load_error_records,
    render_error_report,
    summarize_errors,
)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize reviewed Feature 007 error records.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ERROR_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_ERROR_REPORT)
    arguments = parser.parse_args(argv)

    try:
        records = load_error_records(arguments.manifest)
    except EvaluationErrorStoreError:
        print(json.dumps({"status": "invalid", "manifest": str(arguments.manifest)}))
        return 2

    _atomic_write(arguments.output, render_error_report(records))
    print(
        json.dumps(
            {
                "status": "completed",
                **summarize_errors(records),
                "report": str(arguments.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
