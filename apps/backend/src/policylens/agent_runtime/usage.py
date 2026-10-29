from __future__ import annotations

from collections.abc import Sequence

from openai.types.responses import ResponseReasoningItem

from policylens.agent_runtime.models import AgentModelUsage


def _token_count(value: object | None, *fields: str) -> int | None:
    for field in fields:
        count = getattr(value, field, None)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            return count
    return None


def model_usage_from_provider(
    usage: object | None,
    *,
    default_requests: int | None = None,
) -> AgentModelUsage:
    prompt_tokens = _token_count(usage, "input_tokens", "prompt_tokens")
    completion_tokens = _token_count(usage, "output_tokens", "completion_tokens")
    total_tokens = _token_count(usage, "total_tokens")
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    input_details = getattr(usage, "input_tokens_details", None) or getattr(
        usage, "prompt_tokens_details", None
    )
    output_details = getattr(usage, "output_tokens_details", None) or getattr(
        usage, "completion_tokens_details", None
    )
    requests = _token_count(usage, "requests")
    if requests is None:
        requests = default_requests
    return AgentModelUsage(
        requests=requests,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=_token_count(input_details, "cached_tokens"),
        reasoning_tokens=_token_count(output_details, "reasoning_tokens"),
    )


def aggregate_model_usage(usages: Sequence[AgentModelUsage]) -> AgentModelUsage:
    if not usages:
        return AgentModelUsage()

    def total(field: str) -> int | None:
        values = [getattr(usage, field) for usage in usages]
        if any(value is None for value in values):
            return None
        return sum(value for value in values if isinstance(value, int))

    return AgentModelUsage(
        requests=total("requests"),
        prompt_tokens=total("prompt_tokens"),
        completion_tokens=total("completion_tokens"),
        total_tokens=total("total_tokens"),
        cached_input_tokens=total("cached_input_tokens"),
        reasoning_tokens=total("reasoning_tokens"),
    )


def reasoning_summary_from_responses(responses: object) -> str | None:
    if not isinstance(responses, Sequence) or isinstance(responses, (str, bytes)):
        return None

    summaries: list[str] = []
    for response in responses:
        output = getattr(response, "output", ())
        if not isinstance(output, Sequence) or isinstance(output, (str, bytes)):
            continue
        for item in output:
            if not isinstance(item, ResponseReasoningItem):
                continue
            summaries.extend(
                summary.text.strip()
                for summary in item.summary
                if summary.type == "summary_text" and summary.text.strip()
            )

    unique_summaries = list(dict.fromkeys(summaries))
    combined = "\n\n".join(unique_summaries)
    return combined[:4000] or None
