from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from policylens.retrieval.chunking import structure_aware_chunker_config
from policylens.retrieval.config import RetrievalSettings
from policylens.retrieval.embeddings import create_embedding_provider
from policylens.retrieval.indexing import (
    IndexBuildError,
    build_index,
    rollback_active_index,
    verify_active_index,
)
from policylens.retrieval.models import ActiveIndexPointer
from policylens.settings import PROJECT_ROOT


def _pointer_summary(pointer: ActiveIndexPointer) -> dict[str, object]:
    return pointer.model_dump(mode="json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and manage the local PolicyLens retrieval index"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="Build, validate, and activate a new index")
    subparsers.add_parser("verify", help="Verify the active index and its persistent stores")
    subparsers.add_parser("rollback", help="Atomically restore the previous validated index")
    arguments = parser.parse_args(argv)
    settings = RetrievalSettings()

    try:
        if arguments.command == "build":
            embedder = create_embedding_provider(settings)
            pointer = build_index(
                PROJECT_ROOT,
                settings,
                embedder,
                structure_aware_chunker_config(),
            )
        elif arguments.command == "verify":
            pointer = verify_active_index(PROJECT_ROOT, settings)
        else:
            pointer = rollback_active_index(PROJECT_ROOT, settings)
    except IndexBuildError as error:
        print(json.dumps({"status": "failed", "error_code": error.code, "message": str(error)}))
        return 1

    print(json.dumps({"status": "ready", "pointer": _pointer_summary(pointer)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
