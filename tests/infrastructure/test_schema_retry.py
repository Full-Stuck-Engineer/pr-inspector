"""One retry when a reply does not match the review schema (issue #42).

The endpoint sometimes returns a reply that finishes normally but drops a required field.
The review asks once more, naming the validation error, and a second violation fails it.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from pr_inspector.domain.entities import FileDiff, PRReviewResult, RiskLevel
from pr_inspector.domain.exceptions import ReviewExecutionError
from pr_inspector.infrastructure.llm.openai_client import (
    SCHEMA_FAILURE_MESSAGE,
    OpenAICompatibleLLMReviewer,
    _schema_feedback,
)

MISSING_SEVERITY = {
    "summary": "One problem.",
    "risk_level": "HIGH",
    "issues": [{"file_path": "a.py", "line_number": 3, "title": "t", "description": "d"}],
}
WRONG_TYPE = {
    "summary": "One problem.",
    "risk_level": "HIGH",
    "issues": [
        {
            "file_path": "a.py",
            "line_number": "SECRET-LINE",
            "severity": "HIGH",
            "title": "t",
            "description": "d",
        }
    ],
}


def validation_error(reply: dict) -> ValidationError:
    try:
        PRReviewResult.model_validate(reply)
    except ValidationError as exc:
        return exc
    raise AssertionError("the sample reply should not validate")


def completion(parsed=None, content=None, tokens=(50, 20)) -> MagicMock:
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.parsed = parsed
    choice.message.content = content
    result = MagicMock()
    result.choices = [choice]
    result.usage.prompt_tokens, result.usage.completion_tokens = tokens
    return result


def clean_result() -> PRReviewResult:
    return PRReviewResult(summary="fixed", risk_level=RiskLevel.LOW, issues=[])


def review_with(reviewer, replies):
    """Run a review with the endpoint answering ``replies`` in order."""
    with patch.object(reviewer.client.beta.chat.completions, "parse", side_effect=replies) as parse:
        result = reviewer.review([FileDiff(file_path="a.py")])
    return result, parse


def test_a_valid_reply_takes_one_request():
    reviewer = OpenAICompatibleLLMReviewer()

    (result, _), parse = review_with(reviewer, [completion(parsed=clean_result())])

    assert parse.call_count == 1
    assert result.summary == "fixed"


def test_a_schema_violation_is_retried_once_and_the_error_is_named():
    reviewer = OpenAICompatibleLLMReviewer()
    replies = [validation_error(MISSING_SEVERITY), completion(parsed=clean_result())]

    (result, _), parse = review_with(reviewer, replies)

    assert result.summary == "fixed"
    assert parse.call_count == 2
    retry_turn = parse.call_args.kwargs["messages"][-1]
    assert retry_turn["role"] == "user"
    assert "issues.0.severity" in retry_turn["content"]


def test_a_second_schema_violation_fails_the_review():
    reviewer = OpenAICompatibleLLMReviewer()
    replies = [validation_error(MISSING_SEVERITY), validation_error(MISSING_SEVERITY)]

    with pytest.raises(ReviewExecutionError) as caught:
        review_with(reviewer, replies)

    assert str(caught.value) == SCHEMA_FAILURE_MESSAGE


def test_a_fenced_reply_that_breaks_the_schema_is_retried_too():
    reviewer = OpenAICompatibleLLMReviewer()
    fenced_without_risk = completion(parsed=None, content='```json\n{"summary": "x"}\n```')
    replies = [fenced_without_risk, completion(parsed=clean_result())]

    (result, _), parse = review_with(reviewer, replies)

    assert result.summary == "fixed"
    assert parse.call_count == 2
    assert "risk_level" in parse.call_args.kwargs["messages"][-1]["content"]


def test_the_feedback_names_the_field_and_rule_and_never_repeats_the_reply_value():
    feedback = _schema_feedback(validation_error(WRONG_TYPE))

    assert "issues.0.line_number" in feedback
    assert "SECRET-LINE" not in feedback


def test_the_telemetry_reports_the_reply_that_was_kept():
    # The failed attempt's usage is not returned with the SDK's validation error, so only the
    # kept reply's tokens are counted. The latency covers both attempts.
    reviewer = OpenAICompatibleLLMReviewer()
    replies = [
        validation_error(MISSING_SEVERITY),
        completion(parsed=clean_result(), tokens=(70, 30)),
    ]

    (_, telemetry), _ = review_with(reviewer, replies)

    assert telemetry.input_tokens == 70
    assert telemetry.output_tokens == 30
