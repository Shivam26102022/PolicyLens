.PHONY: setup dev-frontend dev-api dev-mcp mcp-health data-fetch data-verify data-parse data-eda retrieval-index retrieval-verify retrieval-rollback retrieval-eval agent-eval evaluation-verify evaluation-errors security-verify test test-python test-frontend coverage coverage-python lint lint-python typecheck typecheck-python format format-check-python format-check traceability check

setup:
	uv sync --locked --all-packages --all-groups
	npm ci --prefix apps/frontend

dev-frontend:
	npm --prefix apps/frontend run dev

dev-api:
	uv run --locked --package policylens uvicorn policylens.api.app:app --host 127.0.0.1 --port 8009 --reload

dev-mcp:
	uv run --locked --package policylens-mcp policylens-mcp

mcp-health:
	uv run --locked --package policylens python -m policylens.api.mcp_probe

data-fetch:
	uv run --locked --package policylens python scripts/download_data.py fetch

data-verify:
	uv run --locked --package policylens python scripts/download_data.py verify

data-parse:
	uv run --locked --package policylens python -m scripts.parse_data

data-eda: data-parse
	uv run --locked --package policylens python -m scripts.eda.youth_employment

retrieval-index:
	uv run --locked --package policylens python -m scripts.build_retrieval_index build

retrieval-verify:
	uv run --locked --package policylens python -m scripts.build_retrieval_index verify

retrieval-rollback:
	uv run --locked --package policylens python -m scripts.build_retrieval_index rollback

retrieval-eval: retrieval-verify
	uv run --locked --package policylens python -m scripts.evaluate_retrieval

agent-eval:
	uv run --locked --package policylens python -m scripts.evaluate_agent

evaluation-verify:
	uv run --locked --package policylens python -m scripts.evaluation_case_set --validate-only

evaluation-errors:
	uv run --locked --package policylens python -m scripts.analyze_evaluation_errors

security-verify:
	uv run --locked --package policylens pytest scripts/tests/test_security_audit.py scripts/tests/test_evaluation_suite.py apps/backend/tests/security apps/backend/tests/unit/test_agent_runtime.py apps/backend/tests/unit/test_agent_state.py apps/backend/tests/unit/test_agent_tools.py apps/backend/tests/unit/test_generation_baseline.py apps/backend/tests/unit/test_mcp_client.py apps/backend/tests/unit/test_retrieval.py apps/backend/tests/unit/test_retrieval_models.py apps/backend/tests/unit/test_settings.py apps/backend/tests/unit/test_logging.py
	uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests/test_security_boundaries.py services/mcp-policy-data/tests/test_logging.py services/mcp-policy-data/tests/test_passages.py
	npm --prefix apps/frontend run build
	npm --prefix apps/frontend test
	uv run --locked --package policylens python -m scripts.security_audit --verify --scan-secrets

test-python:
	uv run --locked --package policylens pytest apps/backend/tests
	uv run --locked --package policylens-mcp pytest services/mcp-policy-data/tests
	uv run --locked --package policylens pytest scripts/tests

test-frontend:
	npm --prefix apps/frontend test

test: test-python test-frontend traceability

coverage-python:
	uv run --locked --all-packages --all-groups coverage erase
	uv run --locked --all-packages --all-groups coverage run --parallel-mode --branch --source=apps/backend/src/policylens,scripts -m pytest apps/backend/tests scripts/tests
	uv run --locked --all-packages --all-groups coverage run --parallel-mode --branch --source=services/mcp-policy-data/src/policylens_mcp -m pytest services/mcp-policy-data/tests
	uv run --locked --all-packages --all-groups coverage combine
	uv run --locked --all-packages --all-groups coverage report --show-missing

coverage: coverage-python
	npm --prefix apps/frontend run coverage

lint-python:
	uv run --locked --package policylens ruff check apps/backend/src apps/backend/tests scripts
	uv run --locked --package policylens-mcp ruff check services/mcp-policy-data/src services/mcp-policy-data/tests

lint:
	$(MAKE) lint-python
	npm --prefix apps/frontend run lint

typecheck-python:
	uv run --locked --package policylens mypy apps/backend/src apps/backend/tests scripts
	uv run --locked --package policylens-mcp mypy services/mcp-policy-data/src services/mcp-policy-data/tests

typecheck:
	$(MAKE) typecheck-python
	npm --prefix apps/frontend run typecheck

format:
	uv run --locked --package policylens ruff format apps/backend/src apps/backend/tests scripts
	uv run --locked --package policylens-mcp ruff format services/mcp-policy-data/src services/mcp-policy-data/tests
	npm --prefix apps/frontend run format

format-check-python:
	uv run --locked --package policylens ruff format --check apps/backend/src apps/backend/tests scripts
	uv run --locked --package policylens-mcp ruff format --check services/mcp-policy-data/src services/mcp-policy-data/tests

format-check:
	$(MAKE) format-check-python
	npm --prefix apps/frontend run format:check

traceability:
	python3 scripts/check_traceability.py

check: format-check lint typecheck test