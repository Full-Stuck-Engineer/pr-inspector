"""Unit tests for git-quoted and whitespace path parsing (issue #9).

Git emits paths that contain spaces or non-ASCII bytes in forms a naive
whitespace split cannot handle:

* unquoted space-paths are terminated by a tab on the ``---``/``+++`` lines
* non-ASCII paths are quoted with octal-escaped bytes

These tests lock in the parser's behaviour against real git output shapes.
"""

from pr_inspector.infrastructure.git.diff_extractor import GitCliDiffProvider

QUOTED_NON_ASCII_DIFF = (
    'diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"\n'
    "index 47643d4..258e955 100644\n"
    '--- "a/caf\\303\\251.py"\n'
    '+++ "b/caf\\303\\251.py"\n'
    "@@ -1 +1,2 @@\n"
    " y = 2\n"
    "+w = 4\n"
)

TAB_TERMINATED_SPACE_PATH_DIFF = (
    "diff --git a/my dir/app.py b/my dir/app.py\n"
    "index 7d4290a..a3ef230 100644\n"
    "--- a/my dir/app.py\t\n"
    "+++ b/my dir/app.py\t\n"
    "@@ -1 +1,2 @@\n"
    " x = 1\n"
    "+z = 3\n"
)

NEW_FILE_SPACE_PATH_DIFF = (
    "diff --git a/docs/API v2/spec.md b/docs/API v2/spec.md\n"
    "new file mode 100644\n"
    "index 0000000..1234567\n"
    "--- /dev/null\n"
    "+++ b/docs/API v2/spec.md\t\n"
    "@@ -0,0 +1,2 @@\n"
    "+spec = True\n"
)

DELETED_NON_ASCII_DIFF = (
    'diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"\n'
    "deleted file mode 100644\n"
    "index 47643d4..0000000\n"
    '--- "a/caf\\303\\251.py"\n'
    "+++ /dev/null\n"
    "@@ -1 +0,0 @@\n"
    "-y = 2\n"
)


def test_parse_quoted_non_ascii_path():
    """A non-ASCII path arrives octal-escaped inside quotes; decode to UTF-8."""
    result = GitCliDiffProvider().parse_unified_diff(QUOTED_NON_ASCII_DIFF)

    assert len(result) == 1
    assert result[0].file_path == "café.py"
    assert result[0].hunks[0].lines[0].content == "y = 2"


def test_parse_tab_terminated_path_with_space():
    """An unquoted space-path is terminated by a tab, not a quote."""
    result = GitCliDiffProvider().parse_unified_diff(TAB_TERMINATED_SPACE_PATH_DIFF)

    assert len(result) == 1
    assert result[0].file_path == "my dir/app.py"
    assert result[0].old_path == "my dir/app.py"


def test_parse_new_file_with_space_path():
    """A new file's old side is /dev/null; the new path keeps its spaces."""
    result = GitCliDiffProvider().parse_unified_diff(NEW_FILE_SPACE_PATH_DIFF)

    assert len(result) == 1
    fd = result[0]
    assert fd.file_path == "docs/API v2/spec.md"
    assert fd.is_new is True
    assert fd.old_path is None


def test_parse_deleted_non_ascii_path():
    """A deleted file reports the old path, decoded from octal escapes."""
    result = GitCliDiffProvider().parse_unified_diff(DELETED_NON_ASCII_DIFF)

    assert len(result) == 1
    fd = result[0]
    assert fd.file_path == "café.py"
    assert fd.is_deleted is True


def test_header_fallback_for_space_path_without_path_lines():
    """Without ---/+++ lines the header is the only path source.

    A rename-only diff (100% similarity) emits no path lines. The header
    fallback splits on the last `` b/`` occurrence.
    """
    raw = (
        "diff --git a/my dir/app.py b/my dir/renamed.py\n"
        "similarity index 100%\n"
        "rename from my dir/app.py\n"
        "rename to my dir/renamed.py\n"
    )
    result = GitCliDiffProvider().parse_unified_diff(raw)

    assert len(result) == 1
    assert result[0].old_path == "my dir/app.py"
    assert result[0].file_path == "my dir/renamed.py"


def test_plain_paths_still_parse():
    """The pre-existing simple case must keep working unchanged."""
    raw = (
        "diff --git a/src/math_ops.py b/src/math_ops.py\n"
        "index e69de29..d95f3ad 100644\n"
        "--- a/src/math_ops.py\n"
        "+++ b/src/math_ops.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def add(a: int, b: int) -> int:\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    result = GitCliDiffProvider().parse_unified_diff(raw)

    assert len(result) == 1
    assert result[0].file_path == "src/math_ops.py"
