"""Domain entities and value objects for pr-inspector."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    cited_files: list[str] = Field(
        default_factory=list,
        description="External codebase files cited as evidence or reference for this issue",
    )


class PRReviewResult(BaseModel):
    """Strict structured review output returned by the LLM analyzer."""

    summary: str = Field(description="High-level assessment of the pull request changes")
    risk_level: RiskLevel = Field(description="Aggregated risk severity")
    issues: list[ReviewIssue] = Field(default_factory=list, description="List of identified issues")
    cited_files: list[str] = Field(
        default_factory=list,
        description="Source files from codebase context cited in the review report",
    )

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
    retrieved_chunks: int = 0
    rerank_latency_ms: float = 0.0
    context_tokens: int = 0


class ChunkType(StrEnum):
    """Categorization of a code or document chunk."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE_PREAMBLE = "module_preamble"
    MARKDOWN_SECTION = "markdown_section"
    TEXT_BLOCK = "text_block"


class SymbolKind(StrEnum):
    """Kind of a code symbol definition."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    VARIABLE = "variable"
    INTERFACE = "interface"


class SymbolDefinition(BaseModel):
    """A symbol definition extracted from source code."""

    name: str = Field(description="Name of the defined symbol")
    kind: SymbolKind = Field(description="Kind of symbol")
    file_path: str = Field(description="Relative path of defining file")
    line_number: int = Field(ge=1, description="1-based line number of definition")
    signature: str | None = Field(default=None, description="Function/method call signature")
    docstring: str | None = Field(default=None, description="Extracted docstring summary")


class CodeChunk(BaseModel):
    """A structure-aware chunk of code or documentation."""

    id: str = Field(description="Globally unique chunk identifier")
    file_path: str = Field(description="Relative file path")
    content: str = Field(description="Extracted chunk text content")
    start_line: int = Field(ge=1, description="1-based starting line number")
    end_line: int = Field(ge=1, description="1-based ending line number")
    chunk_type: ChunkType = Field(description="Classification of this chunk")
    symbol_name: str | None = Field(
        default=None, description="Primary symbol defined by this chunk"
    )
    parent_symbol: str | None = Field(default=None, description="Enclosing class or symbol name")
    language: str = Field(default="text", description="Programming or markup language")


class FileChangeSet(BaseModel):
    """Detected file differences between working tree and manifest."""

    added: list[str] = Field(default_factory=list, description="New files not in manifest")
    modified: list[str] = Field(
        default_factory=list, description="Files with changed content hashes"
    )
    deleted: list[str] = Field(
        default_factory=list, description="Files in manifest but removed from disk"
    )
    unchanged: list[str] = Field(
        default_factory=list, description="Files with matching content hashes"
    )

    @property
    def has_changes(self) -> bool:
        """Return True if any added, modified, or deleted files are detected."""
        return bool(self.added or self.modified or self.deleted)


class IndexManifest(BaseModel):
    """Persistent state recording indexed files and their SHA256 hashes."""

    version: int = Field(default=1, description="Manifest schema version")
    file_hashes: dict[str, str] = Field(
        default_factory=dict, description="Mapping of relative file path to SHA256 digest"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp of last index update",
    )
