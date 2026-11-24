"""Git CLI adapter for extracting, filtering, and parsing unified diffs."""

import ast
import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from pr_inspector.domain.entities import DiffHunk, DiffLine, FileDiff
from pr_inspector.domain.exceptions import DiffExtractionError

# Matched against the file name and against the whole path.
DEFAULT_IGNORED_PATTERNS: tuple[str, ...] = (
    # Lockfiles
    "*.lock",
    "uv.lock",
    "package-lock.json",
    "poetry.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.sum",
    # Minified output and source maps
    "*.min.js",
    "*.min.css",
    "*.map",
    # Images, fonts and archives
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.webp",
    "*.avif",
    "*.bmp",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.otf",
    "*.eot",
    "*.pdf",
    "*.zip",
    "*.whl",
    "*.tar.gz",
    "*.gz",
    "*.jar",
    # Compiled artifacts
    "*.pyc",
    "*.class",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    # Generated code
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.pb.go",
    "*.generated.*",
    "*.snap",
)

# Matched against each directory segment of a path, so nested directories are covered too.
DEFAULT_IGNORED_DIRECTORIES: tuple[str, ...] = (
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    ".next",
    "__pycache__",
    "*.egg-info",
)

HUNK_HEADER_REGEX = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def _decode_git_quoted_path(token: str) -> str:
    """Decode a git-quoted path token into its real UTF-8 text.

    Git quotes a path when it contains non-ASCII bytes and escapes each byte
    in octal, e.g. ``"b/caf\\303\\251.py"`` for ``b/café.py``. The escapes are
    byte values, so the octal is decoded to Latin-1 first and then re-encoded
    as UTF-8.
    """
    try:
        decoded = ast.literal_eval(token)
    except (ValueError, SyntaxError):
        return token
    if not isinstance(decoded, str):
        return token
    try:
        return decoded.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return decoded


def _strip_path_prefix(path: str) -> str:
    """Remove the ``a/`` or ``b/`` prefix git puts on diff paths."""
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path


def _parse_path_line(line: str, marker: str) -> str | None:
    """Extract the path from a ``---``/``+++`` diff line.

    Two shapes must be handled:

    * unquoted paths that contain spaces are terminated by a tab, because the
      path itself would otherwise be ambiguous::

          --- a/my dir/app.py\\t

    * quoted paths are unambiguous on their own and carry no tab, and their
      non-ASCII bytes are octal-escaped::

          --- "a/caf\\303\\251.py"
    """
    if not line.startswith(marker):
        return None

    rest = line[len(marker) :].strip()
    if not rest:
        return None

    if rest.startswith('"'):
        closing = rest.find('"', 1)
        if closing == -1:
            return None
        token = rest[: closing + 1]
        return _strip_path_prefix(_decode_git_quoted_path(token))

    # Tab-terminated: everything before the tab is the path.
    path = rest.split("\t", 1)[0].strip()
    if not path:
        return None
    if path == "/dev/null":
        return None
    return _strip_path_prefix(path)


def _parse_header_pair_with_spaces(payload: str) -> tuple[str | None, str | None]:
    """Split an unquoted ``diff --git`` payload into two paths.

    The header has no delimiter when a path contains spaces, so this is
    inherently ambiguous. Git disambiguates by construction: both paths are
    identical except for the ``a/``/``b/`` prefix (or differ only at a rename).
    Splitting on the last `` b/`` occurrence covers the common case.
    """
    idx = payload.rfind(" b/")
    if idx == -1:
        return None, None
    old_part = payload[:idx].strip()
    new_part = payload[idx + 1 :].strip()
    return _strip_path_prefix(old_part), _strip_path_prefix(new_part)


class GitCliDiffProvider:
    """Extracts, filters, and parses git diffs into domain FileDiff objects."""

    def __init__(
        self,
        repo_path: Path | None = None,
        ignored_patterns: tuple[str, ...] = DEFAULT_IGNORED_PATTERNS,
        ignored_directories: tuple[str, ...] = DEFAULT_IGNORED_DIRECTORIES,
    ) -> None:
        self.repo_path = repo_path or Path.cwd()
        self.ignored_patterns = ignored_patterns
        self.ignored_directories = ignored_directories

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
        """Check if a file sits in an ignored directory or matches a noise pattern.

        Directories are matched segment by segment at any depth, so ``packages/web/dist/x.js``
        is skipped while ``src/dist_utils.py`` is not. Git paths always use forward slashes.
        """
        path = PurePosixPath(file_path)
        if any(
            fnmatch(segment, pattern)
            for segment in path.parts[:-1]
            for pattern in self.ignored_directories
        ):
            return True
        return any(
            fnmatch(path.name, pattern) or fnmatch(file_path, pattern)
            for pattern in self.ignored_patterns
        )

    @staticmethod
    def _is_binary_diff(lines: list[str]) -> bool:
        """Whether a file section is a binary diff.

        Git prints ``Binary files a/x and b/x differ``. Only the header lines are inspected,
        and diff content lines always start with ``+``, ``-`` or a space, so added text that
        merely looks like the notice cannot hide a real file.
        """
        return any(
            line.startswith("Binary files ") and line.endswith(" differ") for line in lines[:10]
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
            old_path, new_path = self._resolve_paths(header_line, lines)
            if old_path is None and new_path is None:
                continue

            # Ignore binary files or noise files
            target_path = new_path or old_path
            if (
                target_path is None
                or self.should_ignore_file(target_path)
                or self._is_binary_diff(lines)
            ):
                continue

            is_new = any(line.startswith("new file mode") for line in lines[:10])
            is_deleted = any(line.startswith("deleted file mode") for line in lines[:10])

            hunks = self._parse_hunks(lines)
            file_diffs.append(
                FileDiff(
                    file_path=new_path or target_path,
                    old_path=old_path if not is_new else None,
                    is_new=is_new,
                    is_deleted=is_deleted,
                    hunks=hunks,
                )
            )

        return file_diffs

    @staticmethod
    def _resolve_paths(header_line: str, lines: list[str]) -> tuple[str | None, str | None]:
        """Determine a file's old and new path from its diff section.

        The ``---``/``+++`` lines are the authoritative source: git terminates
        an unquoted path containing spaces with a tab, and octal-escapes a
        non-ASCII one inside quotes. Only when those lines are absent (binary
        diffs, renames with no hunks) does the ``diff --git`` header serve as
        the fallback.
        """
        old_path: str | None = None
        new_path: str | None = None

        for line in lines[:10]:
            if old_path is None and line.startswith("--- "):
                old_path = _parse_path_line(line, "--- ")
                continue
            if new_path is None and line.startswith("+++ "):
                new_path = _parse_path_line(line, "+++ ")
                break

        if old_path is None and new_path is None:
            return GitCliDiffProvider._parse_header_paths(header_line)

        # A new file shows /dev/null on the old side; a deleted file the reverse.
        return old_path, new_path or old_path

    @staticmethod
    def _parse_header_paths(header_line: str) -> tuple[str | None, str | None]:
        """Fallback parser for the ``diff --git`` header line.

        The header has no unambiguous delimiter when a path contains spaces —
        git relies on the ``---``/``+++`` lines for that. This parser is used
        only for sections that have no such lines, so it handles the common
        single-token case and git's quoted form for non-ASCII paths.
        """
        payload = header_line.removeprefix("diff --git ")

        tokens = payload.split("\t")
        if len(tokens) == 2:
            return _strip_path_prefix(tokens[0]), _strip_path_prefix(tokens[1])

        if payload.startswith('"'):
            closing = payload.find('"', 1)
            if closing == -1:
                return None, None
            first = payload[: closing + 1]
            remainder = payload[closing + 1 :].strip()
            if not remainder.startswith('"'):
                return None, None
            return (
                _strip_path_prefix(_decode_git_quoted_path(first)),
                _strip_path_prefix(_decode_git_quoted_path(remainder)),
            )

        return _parse_header_pair_with_spaces(payload)

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
