"""Tests for LLM retry/backoff and truncation handling (issue #11).

The review call previously ran exactly once: a single 429 failed the run, and
a token-ceiling truncation surfaced as a confusing parse error. These tests
lock in retry-with-backoff for transient failures, immediate failure for
caller errors, and an explicit truncation message.
"""

from unittest.mock import MagicMock, patch

import openai
import pytest

from pr_inspector.domain.entities import FileDiff, PRReviewResult, RiskLevel
from pr_inspector.domain.exceptions import ReviewExecutionError
from pr_inspector.infrastructure.llm import openai_client
from pr_inspector.infrastructure.llm.openai_client import OpenAICompatibleLLMReviewer


def _parsed_result() -> PRReviewResult:
    return PRReviewResult(summary="clean", risk_level=RiskLevel.LOW, issues=[])


def _completion(
    finish_reason: str = "stop", parsed: object | None = None, *, omit_parsed: bool = False
) -> MagicMock:
    choice = MagicMock()
    choice.finish_reason = finish_reason
    if omit_parsed:
        choice.message.parsed = None
    else:
        choice.message.parsed = parsed if parsed is not None else _parsed_result()
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage.prompt_tokens = 100
    completion.usage.completion_tokens = 20
    return completion


@pytest.fixture(autouse=True)
def _no_sleep():
    """Keep backoff out of the test runtime."""
    with patch.object(openai_client.time, "sleep"):
        yield


def _reviewer() -> OpenAICompatibleLLMReviewer:
    return OpenAICompatibleLLMReviewer(api_key="test-key", model="test-model")


class TestRetries:
    def test_rate_limit_is_retried_then_succeeds(self):
        reviewer = _reviewer()
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=[
                openai.RateLimitError(message="429", response=MagicMock(), body=None),
                _completion(),
            ],
        ) as mock_parse:
            result, _telemetry = reviewer.review([FileDiff(file_path="a.py")])

        assert result.risk_level is RiskLevel.LOW
        assert mock_parse.call_count == 2

    def test_connection_error_is_retried_then_succeeds(self):
        reviewer = _reviewer()
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=[openai.APIConnectionError(request=MagicMock()), _completion()],
        ) as mock_parse:
            reviewer.review([FileDiff(file_path="a.py")])

        assert mock_parse.call_count == 2

    def test_server_error_is_retried(self):
        reviewer = _reviewer()
        response = MagicMock()
        response.status_code = 503
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=[openai.APIStatusError("503", response=response, body=None), _completion()],
        ) as mock_parse:
            reviewer.review([FileDiff(file_path="a.py")])

        assert mock_parse.call_count == 2

    def test_persistent_rate_limit_raises_after_max_attempts(self):
        reviewer = _reviewer()
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=openai.RateLimitError(message="429", response=MagicMock(), body=None),
        ) as mock_parse:
            with pytest.raises(ReviewExecutionError, match="after 3 attempts"):
                reviewer.review([FileDiff(file_path="a.py")])

        assert mock_parse.call_count == 3

    def test_client_error_fails_immediately_without_retry(self):
        """A 4xx other than 429 is a caller mistake; retrying cannot help."""
        reviewer = _reviewer()
        response = MagicMock()
        response.status_code = 401
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=openai.APIStatusError("401", response=response, body=None),
        ) as mock_parse:
            with pytest.raises(ReviewExecutionError, match="LLM API request failed"):
                reviewer.review([FileDiff(file_path="a.py")])

        assert mock_parse.call_count == 1

    def test_backoff_grows_between_attempts(self):
        sleeps = []
        reviewer = _reviewer()
        with (
            patch.object(openai_client.time, "sleep", side_effect=lambda s: sleeps.append(s)),
            patch.object(
                reviewer.client.beta.chat.completions,
                "parse",
                side_effect=[
                    openai.APIConnectionError(request=MagicMock()),
                    openai.APIConnectionError(request=MagicMock()),
                    _completion(),
                ],
            ),
        ):
            reviewer.review([FileDiff(file_path="a.py")])

        assert len(sleeps) == 2
        assert sleeps[1] > sleeps[0]


class TestTruncation:
    def test_truncated_response_raises_explicit_error(self):
        reviewer = _reviewer()
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            return_value=_completion(finish_reason="length", omit_parsed=True),
        ):
            with pytest.raises(ReviewExecutionError, match="truncated"):
                reviewer.review([FileDiff(file_path="a.py")])

    def test_truncation_error_is_actionable(self):
        reviewer = _reviewer()
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            return_value=_completion(finish_reason="length", omit_parsed=True),
        ):
            with pytest.raises(ReviewExecutionError, match="smaller diff"):
                reviewer.review([FileDiff(file_path="a.py")])

    def test_unparseable_non_truncated_response_still_raises_parse_error(self):
        reviewer = _reviewer()
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            return_value=_completion(finish_reason="stop", omit_parsed=True),
        ):
            with pytest.raises(ReviewExecutionError, match="failed to parse"):
                reviewer.review([FileDiff(file_path="a.py")])


class TestSdkTruncationError:
    """The SDK raises LengthFinishReasonError instead of returning a
    completion when the token ceiling is hit — the finish_reason check in
    review() never sees it. These tests exercise the real exception path
    that the mocked-return-value tests above cannot reach."""

    def test_sdk_truncation_error_is_wrapped(self):
        reviewer = _reviewer()
        exc = openai.LengthFinishReasonError(
            completion=_completion(finish_reason="length", omit_parsed=True)
        )
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=exc,
        ):
            with pytest.raises(ReviewExecutionError, match="truncated"):
                reviewer.review([FileDiff(file_path="a.py")])

    def test_sdk_truncation_error_is_not_retried(self):
        """Truncation is deterministic: retrying the same diff cannot help."""
        reviewer = _reviewer()
        exc = openai.LengthFinishReasonError(
            completion=_completion(finish_reason="length", omit_parsed=True)
        )
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=exc,
        ) as mock_parse:
            with pytest.raises(ReviewExecutionError, match="truncated"):
                reviewer.review([FileDiff(file_path="a.py")])

        assert mock_parse.call_count == 1


class TestUnexpectedSdkErrors:
    """Every remaining OpenAIError must surface as ReviewExecutionError,
    never as a raw traceback."""

    def test_content_filter_refusal_is_wrapped(self):
        reviewer = _reviewer()
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=openai.ContentFilterFinishReasonError(),
        ):
            with pytest.raises(ReviewExecutionError, match="LLM API request failed"):
                reviewer.review([FileDiff(file_path="a.py")])

    def test_response_validation_error_is_wrapped(self):
        reviewer = _reviewer()
        response = MagicMock()
        response.status_code = 200
        with patch.object(
            reviewer.client.beta.chat.completions,
            "parse",
            side_effect=openai.APIResponseValidationError(
                message="did not match schema", response=response, body=None
            ),
        ):
            with pytest.raises(ReviewExecutionError, match="LLM API request failed"):
                reviewer.review([FileDiff(file_path="a.py")])
