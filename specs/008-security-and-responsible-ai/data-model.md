# Feature 008 Data Model

## TrustBoundary

Each boundary records stable ID, source/destination principal, assets, data classification, identity/authentication assumptions, authorization and validation controls, logging/redaction behavior, failure behavior, abuse scenarios, existing/new test references, and residual risk. The required boundaries are frontend/browser, frontend/API, API/OpenAI, API/MLX, MCP host/server, MCP/server-data, ingestion/source, evaluation/judge, and logs/traces.

## AttackFixture

Versioned fixture with ID, boundary ID, attack category, synthetic input description/payload, expected invariant, test path, and status (`planned`, `tested`, `unavailable`). Fixture content must not include real credentials, restricted source text, or production personal data. Fixture data must be kept separate from runtime prompts.

## SecurityTestResult

Records fixture ID, run/test reference, result (`pass`, `fail`, `blocked`, `not_tested`), observed invariant, artifact reference, environment and lock identity, and a safe summary. Do not store raw secrets, full prompts, private model reasoning, or unredacted tool output.

## ResidualRisk

Each residual risk records ID, affected boundary, condition, likelihood/impact rationale, existing mitigation, untested assumption, owner/next trigger, and whether local-only scope prevents verification. Risks are not marked mitigated without test evidence.

## Privacy and Oversight

Human review metadata uses pseudonymous reviewer IDs and rubric version; no personal reviewer profile is stored. Logs/traces keep only the existing allow-listed lifecycle and hash metadata. Retention policy defaults to local evaluation artifacts retained until manually removed; no user-content retention or public deployment is introduced by this feature.