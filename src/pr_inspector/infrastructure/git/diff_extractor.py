"""Git CLI adapter for extracting, filtering, and parsing unified diffs."""

import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

from pr_inspector.domain.entities import DiffHunk, DiffLine, FileDiff
from pr_inspector.domain.exceptions import DiffExtractionError

DEFAULT_IGNORED_PATTERNS: tuple[str, ...] = (
    "*.lock",
    "uv.lock",
    "package-lock.json",
    "poetry.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    "*.pyc",
    "__pycache__/*",
    "*.whl",
    "*.tar.gz",
)

HUNK_HEADER_REGEX = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


class GitCliDiffProvider:
    """Extracts, filters, and parses git diffs into domain FileDiff objects."""

    def __init__(
        self,
        repo_path: Path | None = None,
        ignored_patterns: tuple[str, ...] = DEFAULT_IGNORED_PATTERNS,
    ) -> None:
        self.repo_path = repo_path or Path.cwd()
        self.ignored_patterns = ignored_patterns

    def get_diff(self, target_ref: str | None = None, staged: bool = False) -> list[FileDiff]:
        """Fetch and parse git diff according to ref or staged mode."""
        raw_diff = self._run_git_diff(target_ref=target_ref, staged=staged)
        if not raw_diff.strip() and target_ref is None and not staged:
            # If working tree is clean, fallback to reviewing last commit HEAD~1..HEAD
            raw_diff = self._run_git_diff(target_ref="HEAD~1")
        return self.parse_unified_diff(raw_diff)

    def _run_git_diff(self, target_ref: str | None = None, staged: bool = False) -> str:
        cmd = ["git", "diff"]
        if target_ref:
            cmd.append(target_ref)
        elif staged:
            cmd.append("--staged")
        else:
            cmd.append("HEAD")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=30.0,
            )
            if result.returncode != 0:
                raise DiffExtractionError(
                    f"git diff failed with exit code {result.returncode}: {result.stderr.strip()}"
                )
            return result.stdout
        except (subprocess.SubprocessError, OSError) as exc:
            raise DiffExtractionError(f"Failed to execute git diff: {exc}") from exc

    def should_ignore_file(self, file_path: str) -> bool:
        """Check if file matches any noise filtering pattern."""
        file_name = Path(file_path).name
        return any(
            fnmatch(file_name, pattern) or fnmatch(file_path, pattern)
            for pattern in self.ignored_patterns
        )

    def parse_unified_diff(self, raw_diff: str) -> list[FileDiff]:
        """Parse raw unified diff output into annotated FileDiff objects."""
        if not raw_diff.strip():
            return []

        file_diffs: list[FileDiff] = []
        raw_files = raw_diff.split("diff --git ")

        for raw_file in raw_files:
            if not raw_file.strip():
                continue

            lines = raw_file.splitlines()
            header_line = lines[0]
            # Format: a/path/to/file b/path/to/file
            paths = header_line.split(" ")
            if len(paths) < 2:
                continue

            old_path = paths[0].removeprefix("a/")
            new_path = paths[1].removeprefix("b/")

            # Ignore binary files or noise files
            if self.should_ignore_file(new_path) or any(
                "Binary files differ" in line for line in lines[:10]
            ):
                continue

            is_new = any(line.startswith("new file mode") for line in lines[:10])
            is_deleted = any(line.startswith("deleted file mode") for line in lines[:10])

            hunks = self._parse_hunks(lines)
            file_diffs.append(
                FileDiff(
                    file_path=new_path if not is_deleted else old_path,
                    old_path=old_path if not is_new else None,
                    is_new=is_new,
                    is_deleted=is_deleted,
                    hunks=hunks,
                )
            )

        return file_diffs

    def _parse_hunks(self, lines: list[str]) -> list[DiffHunk]:
        hunks: list[DiffHunk] = []
        current_hunk: DiffHunk | None = None
        current_old_line = 0
        current_new_line = 0

        for line in lines:
            match = HUNK_HEADER_REGEX.match(line)
            if match:
                old_start = int(match.group(1))
                old_lines = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_lines = int(match.group(4)) if match.group(4) else 1

                current_hunk = DiffHunk(
                    header=line,
                    old_start=old_start,
                    old_lines=old_lines,
                    new_start=new_start,
                    new_lines=new_lines,
                    lines=[],
                )
                hunks.append(current_hunk)
                current_old_line = old_start
                current_new_line = new_start
                continue

            if current_hunk is None or line.startswith("\\ No newline"):
                continue

            if line.startswith("+"):
                current_hunk.lines.append(
                    DiffLine(
                        line_type="add",
                        content=line[1:],
                        new_line_number=current_new_line,
                    )
                )
                current_new_line += 1
            elif line.startswith("-"):
                current_hunk.lines.append(
                    DiffLine(
                        line_type="del",
                        content=line[1:],
                        old_line_number=current_old_line,
                    )
                )
                current_old_line += 1
            elif line.startswith(" "):
                current_hunk.lines.append(
                    DiffLine(
                        line_type="context",
                        content=line[1:],
                        old_line_number=current_old_line,
                        new_line_number=current_new_line,
                    )
                )
                current_old_line += 1
                current_new_line += 1

        return hunks
