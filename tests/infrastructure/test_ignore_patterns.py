"""Tests for noise filtering: generated files, build output and binary diffs."""

import pytest

from pr_inspector.infrastructure.git.diff_extractor import GitCliDiffProvider

provider = GitCliDiffProvider()


@pytest.mark.parametrize(
    "path",
    [
        # lockfiles
        "go.sum",
        "services/api/go.sum",
        # build and dependency output, at the root and nested
        "dist/app.js",
        "packages/web/dist/app.js",
        "node_modules/left-pad/index.js",
        "web/node_modules/x/y.js",
        "vendor/github.com/pkg/errors/errors.go",
        "build/lib/module.py",
        ".next/server/page.js",
        "coverage/lcov.info",
        "src/pkg.egg-info/PKG-INFO",
        "src/pkg/__pycache__/notes.txt",
        # generated code
        "api/user_pb2.py",
        "api/user_pb2_grpc.py",
        "api/user.pb.go",
        "ui/app.generated.ts",
        "ui/__snapshots__/app.test.js.snap",
        # assets and compiled artifacts
        "web/fonts/inter.woff2",
        "web/img/hero.webp",
        "release/app.zip",
        "lib/native.so",
    ],
)
def test_generated_and_build_files_are_ignored(path: str):
    assert provider.should_ignore_file(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "README.md",
        "cmd/main.go",
        "api/user.proto",  # the source that generated code comes from
        "src/dist_utils.py",  # a file name that merely starts like a directory name
        "src/distribution/api.py",
        "src/builds/runner.py",
        "docs/vendor_notes.md",
        "src/coverage_report.py",
        "docs/generated_docs.md",
    ],
)
def test_source_files_with_similar_names_are_kept(path: str):
    assert provider.should_ignore_file(path) is False


def test_directory_rules_can_be_overridden():
    keep_everything = GitCliDiffProvider(ignored_patterns=(), ignored_directories=())

    assert keep_everything.should_ignore_file("dist/app.js") is False
    assert keep_everything.should_ignore_file("go.sum") is False


RAW_DIFF = """\
diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
 def f():
-    return 1
+    return 2
diff --git a/packages/web/dist/bundle.js b/packages/web/dist/bundle.js
index 1111111..2222222 100644
--- a/packages/web/dist/bundle.js
+++ b/packages/web/dist/bundle.js
@@ -1 +1 @@
-var a = 1;
+var a = 2;
diff --git a/api/user_pb2.py b/api/user_pb2.py
index 1111111..2222222 100644
--- a/api/user_pb2.py
+++ b/api/user_pb2.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
diff --git a/assets/data.bin b/assets/data.bin
index 1111111..2222222 100644
Binary files a/assets/data.bin and b/assets/data.bin differ
"""


def test_raw_diff_keeps_only_reviewable_source():
    files = provider.parse_unified_diff(RAW_DIFF)

    assert [f.file_path for f in files] == ["src/app.py"]


def test_binary_diff_is_dropped_whatever_its_extension():
    raw = """\
diff --git a/assets/data.bin b/assets/data.bin
index 1111111..2222222 100644
Binary files a/assets/data.bin and b/assets/data.bin differ
"""

    assert provider.parse_unified_diff(raw) == []


def test_added_line_that_looks_like_a_binary_notice_does_not_hide_the_file():
    raw = """\
diff --git a/notes.md b/notes.md
index 1111111..2222222 100644
--- a/notes.md
+++ b/notes.md
@@ -1 +1,2 @@
 # Notes
+Binary files a/x and b/x differ
"""

    files = provider.parse_unified_diff(raw)

    assert [f.file_path for f in files] == ["notes.md"]
    assert len(files[0].hunks) == 1
