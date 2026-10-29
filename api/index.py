"""Vercel entrypoint: serves the FastAPI backend under /api next to the static frontend."""

import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for source in (ROOT / "apps/backend/src", ROOT / "services/mcp-policy-data/src"):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

# The MCP SDK does not inherit PYTHONPATH, so the stdio server command carries it explicitly.
os.environ.setdefault(
    "MCP_SERVER_COMMAND",
    "env PYTHONPATH="
    + shlex.quote(os.pathsep.join(p for p in sys.path if p and p != "."))
    + f" {shlex.quote(sys.executable)} -m policylens_mcp",
)

# The deployment filesystem is read-only except /tmp, so the local embedding model downloads there.
os.environ.setdefault("MODEL_CACHE_DIRECTORY", "/tmp/fastembed")

from fastapi import FastAPI  # noqa: E402

from policylens.api.app import app as backend  # noqa: E402

app = FastAPI(title="PolicyLens", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", backend)
