# Feature 001 Coverage Report

**Measured**: 2026-10-24  
**Scope**: Feature 001 foundation code only  
**Commands**: `make coverage`  
**Status**: Measured local baseline; no coverage threshold is set yet.

## Results

| Area | Result | Details |
|---|---:|---|
| Python workspace | 90% combined statement/branch coverage | 365 statements, 28 missed statements, 76 branch opportunities, 13 partial branches. |
| Backend MCP probe | 87% | Success, empty command, identity mismatch, timeout, and generic startup failure are tested. Remaining misses are defensive paths. |
| Backend settings | 94% | Provider selection, missing credentials/models, aliases, invalid bounds, `.env.example` contract, and redaction are tested. |
| Traceability checker | 80% | Helpers, negative mappings, real repository validation, and CLI success are tested. Input-read/parse failure and malformed-document branches remain uncovered. |
| MCP service | 100% for in-process measured modules | Server identity/configuration, logging, and `main()` dispatch are tested. `__main__.py` is 0% in the in-process report because the protocol integration test launches it as a separate process. |
| Frontend | 100% statements, branches, functions, and lines | Both included source modules (`src/App.tsx` and `src/api/health.ts`) are exercised. Vite entrypoint, type-only declarations, and test setup are excluded from the source denominator. |

## Tests Included

- Backend: 19 tests across health, settings, logging, and MCP probe outcomes.
- MCP: 4 tests across settings, logging, stdio identity, and server entrypoint.
- Traceability: 5 tests, including the live repository inventory/spec/task matrix.
- Frontend: 4 Vitest/React Testing Library tests, including API URL defaults and health success/failure.

## Interpretation and Limits

- The Python `coverage.py` report combines statements and branch opportunities; it is not a quality score and does not replace reviewing uncovered paths.
- The MCP subprocess is exercised by a real stdio handshake, but coverage instrumentation is not propagated to the child process. Its `__main__.py` line coverage therefore remains zero in this report.
- The frontend report is limited to the two current product modules. It is not evidence for the final research workspace, evidence drawer, streaming, or later user journeys.
- Tests use synthetic settings and a non-secret fake key only. No live OpenAI call, MLX inference, corpus, or production MCP tool is involved.
- The report is a baseline. A minimum threshold should be considered only after later features add their own tests and after excluded subprocess/runtime behavior is accounted for.