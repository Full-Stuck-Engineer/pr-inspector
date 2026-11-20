"""Unit tests for GitCliDiffProvider."""

from unittest.mock import MagicMock, patch

import pytest

from pr_inspector.domain.exceptions import DiffExtractionError
from pr_inspector.infrastructure.git.diff_extractor import GitCliDiffProvider

SAMPLE_UNIFIED_DIFF = """diff --git a/src/math_ops.py b/src/math_ops.py
index e69de29..d95f3ad 100644
--- a/src/math_ops.py
+++ b/src/math_ops.py
@@ -1,3 +1,4 @@
 def add(a: int, b: int) -> int:
-    return a - b
+    # fixed bug
+    return a + b
diff --git a/uv.lock b/uv.lock
index aaaaaaa..bbbbbbb 100644
--- a/uv.lock
+++ b/uv.lock
@@ -1,1 +1,1 @@
-version = 1
+version = 2
"""


def test_parse_unified_diff():
    provider = GitCliDiffProvider()
    diffs = provider.parse_unified_diff(SAMPLE_UNIFIED_DIFF)

    # uv.lock should be filtered out
    assert len(diffs) == 1
    file_diff = diffs[0]
    assert file_diff.file_path == "src/math_ops.py"
    assert len(file_diff.hunks) == 1

    hunk = file_diff.hunks[0]
    assert hunk.new_start == 1
    assert len(hunk.lines) == 4

    # Line 1: context line
    assert hunk.lines[0].line_type == "context"
    assert hunk.lines[0].new_line_number == 1

    # Line 2: deleted line
    assert hunk.lines[1].line_type == "del"
    assert hunk.lines[1].old_line_number == 2

    # Line 3: added comment line
    assert hunk.lines[2].line_type == "add"
    assert hunk.lines[2].new_line_number == 2

    # Line 4: added return line
    assert hunk.lines[3].line_type == "add"
    assert hunk.lines[3].new_line_number == 3


def test_noise_filtering():
    provider = GitCliDiffProvider()
    assert provider.should_ignore_file("uv.lock") is True
    assert provider.should_ignore_file("package-lock.json") is True
    assert provider.should_ignore_file("dist/app.min.js") is True
    assert provider.should_ignore_file("assets/logo.svg") is True
    assert provider.should_ignore_file("src/pr_inspector/main.py") is False


def test_empty_diff_returns_empty_list():
    provider = GitCliDiffProvider()
    assert provider.parse_unified_diff("") == []
    assert provider.parse_unified_diff("   \n\n  ") == []


def test_git_diff_execution_failure():
    provider = GitCliDiffProvider()
    mock_res = MagicMock(returncode=128, stderr="fatal: not a git repository")
    with patch("subprocess.run", return_value=mock_res):
        with pytest.raises(DiffExtractionError, match="git diff failed"):
            provider.get_diff("main")
