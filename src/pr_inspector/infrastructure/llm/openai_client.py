"""OpenAI-compatible LLM adapter for structured code reviews."""

import os
import random
import re
import time
from datetime import UTC, datetime

import openai
from openai import OpenAI
from openai.lib._parsing import type_to_response_format_param
from openai.types.chat import ChatCompletion
from pydantic import ValidationError

from pr_inspector.domain.entities import FileDiff, PRReviewResult, TelemetryRecord
from pr_inspector.domain.exceptions import ReviewExecutionError

# Matches a single Markdown code fence that wraps the whole reply, e.g.
# ```json\n{...}\n``` or ```\n{...}\n```. Only the innermost JSON text is kept.
_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n([\s\S]*?)\n\s*```\s*$")

# The structured-output request for a review, built by the SDK helper that its own ``parse``
# uses, so the request is unchanged. A test pins it against ``parse``.
REVIEW_RESPONSE_FORMAT = type_to_response_format_param(PRReviewResult)

# Transient failures worth retrying: rate limits, timeouts, dropped connections.
RETRYABLE_ERRORS = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
MAX_ATTEMPTS = 3

REVIEW_SYSTEM_PROMPT = """\
You are a Principal Software Engineer and Security Auditor performing an automated code review.

Your responsibilities:
1. ONLY identify genuine functional defects, security vulnerabilities (OWASP top 10, injection, \
exposed secrets, auth bypass), logic regressions, resource leaks (unclosed sockets/files), \
and race conditions.
2. STRICTLY IGNORE formatting, style, PEP 8 rules, whitespace, docstring nits, \
and minor naming preferences.
3. Every reported issue MUST cite the exact line number from the annotated diff (+ lines only).
4. If the diff contains no serious bugs or security issues, return an empty issues list and set \
risk_level to 'LOW'. Do NOT invent or hallucinate issues.
"""


# The message for a reply that does not match the review schema. Stable, so callers can match it.
SCHEMA_FAILURE_MESSAGE = (
    "LLM response failed to parse into PRReviewResult "
    "(reply was not valid structured output or JSON)"
)


class _SchemaViolation(ReviewExecutionError):
    """The reply came back, but it does not match the review schema.

    ``review`` retries once with the validation error. A second violation fails the review.
    """

    def __init__(self, validation_error: ValidationError) -> None:
        super().__init__(SCHEMA_FAILURE_MESSAGE)
        self.validation_error = validation_error


def _schema_feedback(error: ValidationError) -> str:
    """What to tell the model: each problem by field and rule, never the model's own values."""
    problems = [
        f"{'.'.join(str(part) for part in item['loc']) or 'reply'}: {item['msg']}"
        for item in error.errors()[:5]
    ]
    return (
        "Your previous reply did not match the required JSON schema: "
        + "; ".join(problems)
        + ". Reply again with one complete JSON object that has every required field."
    )


class OpenAICompatibleLLMReviewer:
    """LLM reviewer adapter compatible with Ollama, OpenAI, and Gemini APIs."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        resolved_key = api_key or os.getenv("PR_INSPECTOR_API_KEY") or os.getenv("OPENAI_API_KEY")
        resolved_base_url = (
            base_url or os.getenv("PR_INSPECTOR_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        )

        if model:
            self.model = model
        elif os.getenv("PR_INSPECTOR_MODEL"):
            self.model = os.getenv("PR_INSPECTOR_MODEL", "qwen2.5-coder:7b")
        elif resolved_key and not resolved_base_url:
            self.model = "gpt-4o-mini"
        else:
            self.model = "qwen2.5-coder:7b"

        # Default to local Ollama if no cloud API key provided
        if not resolved_base_url and not resolved_key:
            resolved_base_url = "http://localhost:11434/v1"
            resolved_key = "ollama"

        self.client = OpenAI(
            base_url=resolved_base_url,
            api_key=resolved_key or "ollama",
            timeout=timeout,
        )

    def review(self, diffs: list[FileDiff]) -> tuple[PRReviewResult, TelemetryRecord]:
        """Analyze diffs and produce structured review result with telemetry."""
        diff_text = "\n\n".join(d.annotated_diff_text for d in diffs if d.hunks)
        if not diff_text.strip():
            diff_text = "No code hunk changes found in diff."

        messages = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": f"Review the following code diff:\n\n{diff_text}"},
        ]

        start_time = time.perf_counter()
        try:
            completion, parsed_result = self._request_result(messages)
        except _SchemaViolation as exc:
            # One retry, naming what was wrong with the reply. A second violation fails the review.
            messages.append({"role": "user", "content": _schema_feedback(exc.validation_error)})
            completion, parsed_result = self._request_result(messages)
        latency_ms = (time.perf_counter() - start_time) * 1000

        prompt_tokens = completion.usage.prompt_tokens if completion.usage else 0
        completion_tokens = completion.usage.completion_tokens if completion.usage else 0

        telemetry = TelemetryRecord(
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            latency_ms=round(latency_ms, 2),
            timestamp=datetime.now(UTC).isoformat(),
        )

        return parsed_result, telemetry

    def _request_result(self, messages: list[dict]) -> tuple[ChatCompletion, PRReviewResult]:
        """One request, read as a review: the completion, and its parsed result.

        A reply that does not match the schema raises ``_SchemaViolation``, so ``review`` can
        retry it. That includes an empty or missing reply. A truncated reply is never retried:
        the same diff would be truncated again.
        """
        completion = self._call_with_retries(messages)

        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise ReviewExecutionError(
                "LLM response was truncated (finish_reason='length'). "
                "Retry with a smaller diff or fewer files."
            )

        # Some models wrap their JSON in a Markdown code fence despite the schema, so a single
        # fence is stripped before the reply is validated.
        raw_content = choice.message.content if isinstance(choice.message.content, str) else ""
        fence_match = _CODE_FENCE_RE.match(raw_content)
        json_text = fence_match.group(1) if fence_match else raw_content
        try:
            parsed_result = PRReviewResult.model_validate_json(json_text)
        except ValidationError as exc:
            raise _SchemaViolation(exc) from exc
        return completion, parsed_result

    def _call_with_retries(self, messages: list[dict]) -> ChatCompletion:
        """Call the completions endpoint, retrying transient failures.

        Rate limits, timeouts and connection errors are retried with
        exponential backoff and jitter — a single 429 from a shared endpoint
        should not fail the whole review. Other 4xx errors are the caller's
        mistake (bad key, unsupported parameter) and fail immediately.

        The request asks for the review schema exactly as the SDK's ``parse`` does, but the
        reply is validated in ``_request_result``, not by the SDK: the SDK's own validation
        rejects a fenced reply before it can be read (#50). ``LengthFinishReasonError`` and
        ``ValidationError`` are still wrapped, in case an SDK raises them. The remaining
        ``OpenAIError`` fallback catches the rest of the SDK's error surface (content-filter
        refusals, response validation) so nothing escapes as a raw traceback.
        """
        last_exc: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=REVIEW_RESPONSE_FORMAT,
                    stream=False,
                    temperature=0.0,
                )
            except openai.LengthFinishReasonError as exc:
                raise ReviewExecutionError(
                    "LLM response was truncated (finish_reason='length'). "
                    "Retry with a smaller diff or fewer files."
                ) from exc
            except RETRYABLE_ERRORS as exc:
                last_exc = exc
            except openai.APIStatusError as exc:
                if exc.status_code < 500:
                    raise ReviewExecutionError(f"LLM API request failed: {exc}") from exc
                last_exc = exc
            except ValidationError as exc:
                raise _SchemaViolation(exc) from exc
            except openai.OpenAIError as exc:
                raise ReviewExecutionError(f"LLM API request failed: {exc}") from exc

            if attempt < MAX_ATTEMPTS - 1:
                backoff = (2**attempt) * (1 + random.random() * 0.1)
                time.sleep(backoff)

        raise ReviewExecutionError(
            f"LLM API request failed after {MAX_ATTEMPTS} attempts: {last_exc}"
        ) from last_exc
