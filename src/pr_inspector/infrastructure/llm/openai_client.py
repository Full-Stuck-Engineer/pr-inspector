"""OpenAI-compatible LLM adapter for structured code reviews."""

import os
import time
from datetime import UTC, datetime

import openai
from openai import OpenAI

from pr_inspector.domain.entities import FileDiff, PRReviewResult, TelemetryRecord
from pr_inspector.domain.exceptions import ReviewExecutionError

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

        start_time = time.perf_counter()

        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Review the following code diff:\n\n{diff_text}",
                    },
                ],
                response_format=PRReviewResult,
                temperature=0.0,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            parsed_result = completion.choices[0].message.parsed
            if parsed_result is None:
                raise ReviewExecutionError("LLM response failed to parse into PRReviewResult")

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

        except openai.OpenAIError as exc:
            raise ReviewExecutionError(f"LLM API request failed: {exc}") from exc
        except Exception as exc:
            if isinstance(exc, ReviewExecutionError):
                raise
            raise ReviewExecutionError(f"Unexpected error during code review: {exc}") from exc
