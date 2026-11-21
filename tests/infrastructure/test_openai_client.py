"""Unit tests for OpenAICompatibleLLMReviewer."""

from unittest.mock import MagicMock, patch

import openai
import pytest

from pr_inspector.domain.entities import FileDiff, PRReviewResult, RiskLevel
from pr_inspector.domain.exceptions import ReviewExecutionError
from pr_inspector.infrastructure.llm.openai_client import OpenAICompatibleLLMReviewer


def test_openai_reviewer_default_configuration():
    with patch.dict("os.environ", {}, clear=True):
        reviewer = OpenAICompatibleLLMReviewer()
        assert reviewer.model == "qwen2.5-coder:7b"
        assert str(reviewer.client.base_url).startswith("http://localhost:11434/v1")


def test_openai_reviewer_env_var_override():
    with patch.dict(
        "os.environ",
        {
            "OPENAI_API_KEY": "sk-test-12345",
            "PR_INSPECTOR_MODEL": "gpt-4o",
        },
        clear=True,
    ):
        reviewer = OpenAICompatibleLLMReviewer()
        assert reviewer.model == "gpt-4o"
        assert reviewer.client.api_key == "sk-test-12345"


def test_openai_reviewer_successful_parse():
    mock_parsed_result = PRReviewResult(
        summary="Code looks great",
        risk_level=RiskLevel.LOW,
        issues=[],
    )
    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_parsed_result

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 120
    mock_completion.usage.completion_tokens = 45

    reviewer = OpenAICompatibleLLMReviewer()
    with patch.object(
        reviewer.client.beta.chat.completions,
        "parse",
        return_value=mock_completion,
    ):
        result, telemetry = reviewer.review([FileDiff(file_path="src/main.py")])

        assert result == mock_parsed_result
        assert telemetry.input_tokens == 120
        assert telemetry.output_tokens == 45
        assert telemetry.latency_ms > 0


def test_openai_reviewer_api_error_handling():
    reviewer = OpenAICompatibleLLMReviewer()
    with patch.object(
        reviewer.client.beta.chat.completions,
        "parse",
        side_effect=openai.APIConnectionError(request=MagicMock()),
    ):
        with pytest.raises(ReviewExecutionError, match="LLM API request failed"):
            reviewer.review([FileDiff(file_path="src/main.py")])
