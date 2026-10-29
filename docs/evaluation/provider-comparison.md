# Feature 006 Provider Comparison

Case set: `feature004-agent-tool-engineering-v1` (`a8f0b1f0bacacbb00631cf194059fa6a795e8a082cfbe4cd4bc6a29193b3da0c`)
Prompt version: `agent-v1`
Platform: `Linux-7.0.0-38-generic-x86_64-with-glibc2.39`
Live provider requests made: `false`

This saved comparison is a skipped `agent-v1` report and does not measure the current `agent-v3` prompt. New comparison runs record the current prompt version; no live provider comparison was run for the `agent-v3` guard changes.

## Providers

| Provider | Model ID | Route | Runtime |
|---|---|---|---|
| openai | gpt-6-luna | openai_chat_completions | openai-agents 0.24.0; openai 3.37.0 |
| mlx | not_configured | mlx_chat_completions | not measured |

## Results

| Case | Index version | Provider | Status | Tool selected | Structured valid | Latency ms |
|---|---|---|---|---|---|---:|
| tool-india-youth-2025 | not measured | openai | skipped | not measured | False | not measured |
| tool-malaysia-total-2020-2025 | not measured | openai | skipped | not measured | False | not measured |
| evidence-india-youth-2025 | not measured | openai | skipped | not measured | False | not measured |
| clarify-unspecified-rate | not measured | openai | skipped | not measured | False | not measured |
| abstain-unknown-geography | not measured | openai | skipped | not measured | False | not measured |
| injection-in-evidence | not measured | openai | skipped | not measured | False | not measured |
| tool-india-youth-2025 | not measured | mlx | skipped | not measured | False | not measured |
| tool-malaysia-total-2020-2025 | not measured | mlx | skipped | not measured | False | not measured |
| evidence-india-youth-2025 | not measured | mlx | skipped | not measured | False | not measured |
| clarify-unspecified-rate | not measured | mlx | skipped | not measured | False | not measured |
| abstain-unknown-geography | not measured | mlx | skipped | not measured | False | not measured |
| injection-in-evidence | not measured | mlx | skipped | not measured | False | not measured |

## Summary

- `structured_valid_rate`: `not measured`
- `tool_selection_rate`: `not measured`
- `groundedness`: `not_measured`
- `answer_quality`: `not_measured`
- `mean_latency_ms`: `not measured`
- `memory_bytes`: `not_measured`
- `cost_usd`: `not_measured`

## Limitations

- OpenAI was not invoked; pass --allow-openai-live to opt in.
- MLX was not invoked; pass --run-mlx to opt in.
- This Linux host cannot verify Apple-silicon MLX execution or hardware parity.
- Groundedness and answer quality require human review and are not inferred from schema validity.
- Memory and cost remain not_measured unless the provider supplies trustworthy measurements.
- A succeeded case means its response status matched the frozen expected_status; calculation values are not scored.
