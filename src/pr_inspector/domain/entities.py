"""Domain entities and value objects for pr-inspector."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RiskLevel(StrEnum):
    """Overall review or issue risk severity."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Severity ordering, used to compare risk levels ordinally.
RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


class ReviewIssue(BaseModel):
    """An individual issue identified during PR review."""

    file_path: str = Field(description="Relative path of the reviewed file")
    line_number: int = Field(ge=1, description="Exact 1-based target line number in new file")
    severity: RiskLevel = Field(description="Severity of the issue")
    title: str = Field(description="Brief headline of the problem")
    description: str = Field(description="Detailed explanation of the defect or security flaw")
    suggested_fix: str | None = Field(default=None, description="Recommended remediation")


class PRReviewResult(BaseModel):
    """Strict structured review output returned by the LLM analyzer."""

    summary: str = Field(description="High-level assessment of the pull request changes")
    risk_level: RiskLevel = Field(description="Aggregated risk severity")
    issues: list[ReviewIssue] = Field(default_factory=list, description="List of identified issues")

    @model_validator(mode="after")
    def _align_risk_level_with_issues(self) -> "PRReviewResult":
        """Keep ``risk_level`` consistent with the issues it aggregates.

        ``risk_level`` drives the ``--fail-on`` exit-code contract, so it must
        never be lower than the severity of the issues that were reported: a
        critical finding under a LOW risk level would let a broken pull request
        pass CI. The model sets both fields independently, so the risk level is
        corrected upwards here rather than rejected — a live model that
        under-reports its own severity should not fail the whole review.
        """
        if not self.issues:
            return self

        highest = max(self.issues, key=lambda issue: RISK_ORDER[issue.severity]).severity
        if RISK_ORDER[self.risk_level] < RISK_ORDER[highest]:
            self.risk_level = highest
        return self


@dataclass(frozen=True)
class DiffLine:
    """A single annotated line within a git diff hunk."""

    line_type: Literal["add", "del", "context"]
    content: str
    old_line_number: int | None = None
    new_line_number: int | None = None


@dataclass
class DiffHunk:
    """A hunk within a file diff."""

    header: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    """Parsed and annotated diff for a single file."""

    file_path: str
    old_path: str | None = None
    is_new: bool = False
    is_deleted: bool = False
    hunks: list[DiffHunk] = field(default_factory=list)

    @property
    def annotated_diff_text(self) -> str:
        """Render diff lines annotated with exact target line numbers for LLMs."""
        output: list[str] = [f"--- a/{self.old_path or self.file_path}", f"+++ b/{self.file_path}"]
        for hunk in self.hunks:
            output.append(hunk.header)
            for line in hunk.lines:
                if line.line_type == "add":
                    prefix = f"{line.new_line_number:4d} + "
                elif line.line_type == "del":
                    prefix = "     - "
                else:
                    prefix = f"{line.new_line_number:4d} | "
                output.append(f"{prefix}{line.content}")
        return "\n".join(output)


@dataclass(frozen=True)
class TelemetryRecord:
    """Telemetry capturing cost and latency metrics for an LLM run."""

    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    timestamp: str
