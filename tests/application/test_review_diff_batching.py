"""Unit tests for large-diff batching inside ReviewDiffUseCase, using in-memory fakes."""

import pytest

from pr_inspector.application.use_cases.review_diff import ReviewDiffUseCase
from pr_inspector.domain.chunking import estimate_tokens
from pr_inspector.domain.entities import (
    DiffHunk,
    DiffLine,
    FileDiff,
    PRReviewResult,
    ReviewIssue,
    RiskLevel,
    TelemetryRecord,
)
from pr_inspector.domain.exceptions import ReviewExecutionError


def make_file(path: str, hunks: int = 1) -> FileDiff:
    return FileDiff(
        file_path=path,
        hunks=[
            DiffHunk(
                header=f"@@ -{index * 50 + 1},3 +{index * 50 + 1},3 @@",
                old_start=index * 50 + 1,
                old_lines=3,
                new_start=index * 50 + 1,
                new_lines=3,
                lines=[
                    DiffLine(
                        line_type="add",
                        content="y" * 60,
                        new_line_number=index * 50 + 1 + offset,
                    )
                    for offset in range(3)
                ],
            )
            for index in range(hunks)
        ],
    )


def tokens_of(file_diff: FileDiff) -> int:
    return estimate_tokens(file_diff.annotated_diff_text)


class FakeDiffProvider:
    def __init__(self, diffs: list[FileDiff]) -> None:
        self.diffs = diffs

    def get_diff(self, target_ref: str | None = None, staged: bool = False) -> list[FileDiff]:
        return self.diffs


class RecordingReviewer:
    """Reports one issue per file it is shown and records every call."""

    def __init__(self, fail_on_call: int | None = None) -> None:
        self.calls: list[list[FileDiff]] = []
        self._fail_on_call = fail_on_call

    def review(self, diffs: list[FileDiff]) -> tuple[PRReviewResult, TelemetryRecord]:
        self.calls.append(diffs)
        if self._fail_on_call == len(self.calls):
            raise ReviewExecutionError("LLM response was truncated")
        issues = [
            ReviewIssue(
                file_path=diff.file_path,
                line_number=diff.hunks[0].new_start,
                severity=RiskLevel.MEDIUM,
                title="Finding",
                description="details",
            )
            for diff in diffs
            if diff.hunks
        ]
        result = PRReviewResult(
            summary=f"Reviewed call {len(self.calls)}.",
            risk_level=RiskLevel.MEDIUM if issues else RiskLevel.LOW,
            issues=issues,
        )
        telemetry = TelemetryRecord(
            model="fake-model",
            input_tokens=100,
            output_tokens=10,
            latency_ms=250.0,
            timestamp=f"t{len(self.calls)}",
        )
        return result, telemetry


class FakeTelemetrySink:
    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []

    def record(self, telemetry: TelemetryRecord) -> None:
        self.records.append(telemetry)


def make_use_case(
    diffs: list[FileDiff],
    reviewer: RecordingReviewer,
    sink: FakeTelemetrySink | None = None,
    max_input_tokens: int = 10_000,
) -> ReviewDiffUseCase:
    return ReviewDiffUseCase(
        diff_provider=FakeDiffProvider(diffs),
        reviewer=reviewer,
        telemetry_sink=sink,
        max_input_tokens=max_input_tokens,
    )


def test_diff_under_the_ceiling_costs_exactly_one_call():
    reviewer = RecordingReviewer()
    files = [make_file("a.py"), make_file("b.py")]

    result, telemetry = make_use_case(files, reviewer).execute()

    assert reviewer.calls == [files]
    assert [i.file_path for i in result.issues] == ["a.py", "b.py"]
    assert telemetry.input_tokens == 100


def test_diff_over_the_ceiling_is_reviewed_in_batches_and_merged():
    reviewer = RecordingReviewer()
    files = [make_file("a.py"), make_file("b.py"), make_file("c.py")]
    ceiling = tokens_of(files[0]) * 2  # two files per batch

    result, telemetry = make_use_case(files, reviewer, max_input_tokens=ceiling).execute()

    assert [[f.file_path for f in call] for call in reviewer.calls] == [["a.py", "b.py"], ["c.py"]]
    assert [i.file_path for i in result.issues] == ["a.py", "b.py", "c.py"]
    assert result.risk_level == RiskLevel.MEDIUM
    assert telemetry.input_tokens == 200
    assert telemetry.output_tokens == 20
    assert telemetry.latency_ms == 500.0
    assert telemetry.timestamp == "t2"


def test_batched_review_records_one_telemetry_record_per_run():
    sink = FakeTelemetrySink()
    files = [make_file("a.py"), make_file("b.py"), make_file("c.py")]
    ceiling = tokens_of(files[0])  # one file per batch

    _, telemetry = make_use_case(
        files, RecordingReviewer(), sink, max_input_tokens=ceiling
    ).execute()

    assert sink.records == [telemetry]
    assert telemetry.input_tokens == 300


def test_oversized_file_keeps_exact_line_numbers_across_batches():
    reviewer = RecordingReviewer()
    big = make_file("big.py", hunks=4)
    ceiling = tokens_of(make_file("big.py", hunks=1)) * 2

    result, _ = make_use_case([big], reviewer, max_input_tokens=ceiling).execute()

    assert len(reviewer.calls) > 1
    # One finding per batch, each anchored at the first line of a hunk that really exists.
    assert {i.line_number for i in result.issues} <= {h.new_start for h in big.hunks}


def test_a_failing_batch_fails_the_whole_review_and_records_nothing():
    reviewer = RecordingReviewer(fail_on_call=2)
    sink = FakeTelemetrySink()
    files = [make_file("a.py"), make_file("b.py"), make_file("c.py")]
    ceiling = tokens_of(files[0])  # one file per batch

    use_case = make_use_case(files, reviewer, sink, max_input_tokens=ceiling)
    with pytest.raises(ReviewExecutionError, match=r"batch 2 of 3.*truncated"):
        use_case.execute()

    # Fail closed: nothing after the failure is reviewed, and no partial result escapes.
    assert len(reviewer.calls) == 2
    assert sink.records == []


def test_single_call_failure_keeps_the_original_error_message():
    reviewer = RecordingReviewer(fail_on_call=1)

    with pytest.raises(ReviewExecutionError) as caught:
        make_use_case([make_file("a.py")], reviewer).execute()

    assert str(caught.value) == "LLM response was truncated"


def test_diff_without_hunks_is_delegated_untouched():
    reviewer = RecordingReviewer()
    renamed = [FileDiff(file_path="renamed.py", old_path="old.py")]

    make_use_case(renamed, reviewer).execute()

    assert reviewer.calls == [renamed]


@pytest.mark.parametrize("bad_ceiling", [0, -1])
def test_non_positive_ceiling_is_rejected(bad_ceiling: int):
    with pytest.raises(ValueError, match="at least 1"):
        make_use_case([make_file("a.py")], RecordingReviewer(), max_input_tokens=bad_ceiling)
