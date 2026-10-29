FROM node:24-slim AS frontend
WORKDIR /app/apps/frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/backend apps/backend
COPY services/mcp-policy-data services/mcp-policy-data
RUN uv sync --locked --all-packages --no-dev
COPY prompts prompts
COPY data data
COPY --from=frontend /app/apps/frontend/dist apps/frontend/dist
ENV PATH="/app/.venv/bin:$PATH" MCP_SERVER_COMMAND="python -m policylens_mcp"
EXPOSE 8009
# Secrets (for example OPENAI_API_KEY) are supplied at run time, never baked into the image.
CMD ["uvicorn", "policylens.api.app:app", "--host", "0.0.0.0", "--port", "8009"]
