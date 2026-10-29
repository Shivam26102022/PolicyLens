# Feature 008 Privacy and Retention

## Allowed Data

Feature 008 security fixtures contain synthetic text only. Runtime and evaluation data must be public, synthetic, or properly anonymized and separately approved for the intended use. A source whose rights or permission status is unknown is excluded. Security test results store fixture IDs, test references, environment metadata, and safe summaries, not raw prompts, private model reasoning, or unredacted tool output.

## Logs and Traces

Default telemetry is limited to allow-listed lifecycle events, durations, stable error codes, and hashes needed for local diagnosis. It excludes provider credentials, request prompts, model output, raw MCP arguments/results, and unnecessary personal identifiers. The offline scanner returns file locations only and never prints matched values.

Synthetic canaries exist only in deterministic tests. The scanner excludes the specific approved fake-secret test files and the existing MLX no-auth placeholder; these exceptions are documented in `scripts/security_audit.py`. An exception is not permission to add real secrets.

## Retention and Deletion

Evaluation and security manifests are local append-only JSON artifacts and are retained until a maintainer manually removes them. They are not sent to a hosted service by Feature 008. Source-specific retention follows the source manifest and applicable permission terms. Local filesystem backups and deletion are operator responsibilities; no centralized retention or deletion service is in scope.

## Reviewer Identity and Consent

Human evaluation reviews use a pseudonymous reviewer ID and rubric version only. Do not store a reviewer name, email, profile, or other identifying details in review records. External provider use requires explicit opt-in at the existing execution boundary; the security audit, fixtures, and `security-verify` target make no provider calls. Local MLX requests remain loopback-only.

## Human Oversight and Escalation

PolicyLens provides evidence-grounded research support and is not the final authority for eligibility, benefits, funding, enforcement, safety, or legal decisions. Requests requiring a consequential determination must be escalated to a qualified human decision-maker. Feature 008 does not implement an appeal workflow or certify an institution's review process; the deploying organization must define those procedures before consequential use.