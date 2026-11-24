"""Unit tests for context injection and grounded prompting in OpenAICompatibleLLMReviewer."""

from unittest.mock import MagicMock, patch

from pr_inspector.domain.entities import (
    DiffHunk,
    DiffLine,
    FileDiff,
    PRReviewResult,
    ReviewIssue,
    RiskLevel,
)
from pr_inspector.infrastructure.llm.openai_client import (
    REVIEW_SYSTEM_PROMPT,
    OpenAICompatibleLLMReviewer,
)


def _make_diff() -> FileDiff:
    return FileDiff(
        file_path="src/calc.py",
        hunks=[
            DiffHunk(
                old_start=1,
                old_lines=1,
                new_start=1,
                new_lines=2,
                header="@@ -1,1 +1,2 @@",
                lines=[
                    DiffLine(
                        line_type="context",
                        content="def add(a, b):",
                        old_line_number=1,
                        new_line_number=1,
                    ),
                    DiffLine(line_type="add", content="    return a + b", new_line_number=2),
                ],
            )
        ],
    )


def test_reviewer_injects_context_into_prompt():
    mock_result = PRReviewResult(
        summary="Context-aware review",
        risk_level=RiskLevel.LOW,
        issues=[],
    )
    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_result
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 100
    mock_completion.usage.completion_tokens = 20

    reviewer = OpenAICompatibleLLMReviewer()
    with patch.object(
        reviewer.client.beta.chat.completions,
        "parse",
        return_value=mock_completion,
    ) as mock_parse:
        context_block = "### src/utils.py\n```python\ndef helper():\n    return 42\n```"
        result, _ = reviewer.review([_make_diff()], context=context_block)

        assert result == mock_result
        assert mock_parse.called
        messages = mock_parse.call_args[1]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "cited_files" in messages[0]["content"]

        user_content = messages[1]["content"]
        assert "## Relevant Codebase Context" in user_content
        assert context_block in user_content


def test_reviewer_omits_context_when_none_or_blank():
    mock_result = PRReviewResult(summary="OK", risk_level=RiskLevel.LOW, issues=[])
    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_result
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 50
    mock_completion.usage.completion_tokens = 10

    reviewer = OpenAICompatibleLLMReviewer()
    with patch.object(
        reviewer.client.beta.chat.completions,
        "parse",
        return_value=mock_completion,
    ) as mock_parse:
        # Test None
        reviewer.review([_make_diff()], context=None)
        messages_none = mock_parse.call_args[1]["messages"]
        assert "## Relevant Codebase Context" not in messages_none[1]["content"]

        # Test blank string
        reviewer.review([_make_diff()], context="   \n  ")
        messages_blank = mock_parse.call_args[1]["messages"]
        assert "## Relevant Codebase Context" not in messages_blank[1]["content"]


def test_reviewer_parses_cited_files_from_completion():
    mock_result = PRReviewResult(
        summary="Found contract violation based on context",
        risk_level=RiskLevel.HIGH,
        issues=[
            ReviewIssue(
                file_path="src/calc.py",
                line_number=2,
                severity=RiskLevel.HIGH,
                title="Contract violation",
                description="Caller expects float, but int returned",
                suggested_fix="Cast result to float",
                cited_files=["src/caller.py"],
            )
        ],
        cited_files=["src/caller.py", "src/types.py"],
    )
    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_result
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 150
    mock_completion.usage.completion_tokens = 60

    reviewer = OpenAICompatibleLLMReviewer()
    with patch.object(
        reviewer.client.beta.chat.completions,
        "parse",
        return_value=mock_completion,
    ):
        result, _ = reviewer.review([_make_diff()], context="### src/caller.py\n...")

        assert result.cited_files == ["src/caller.py", "src/types.py"]
        assert result.issues[0].cited_files == ["src/caller.py"]


def test_system_prompt_contains_grounded_prompting_instructions():
    assert "## Relevant Codebase Context" in REVIEW_SYSTEM_PROMPT
    assert "cited_files" in REVIEW_SYSTEM_PROMPT
