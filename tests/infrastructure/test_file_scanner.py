"""Unit tests for IncrementalFileScanner (Issue #17)."""

from pathlib import Path

from pr_inspector.domain.entities import IndexManifest
from pr_inspector.infrastructure.indexer.file_scanner import IncrementalFileScanner


def test_scanner_fresh_directory(tmp_path: Path):
    file1 = tmp_path / "app.py"
    file1.write_text("print('hello')", encoding="utf-8")

    file2 = tmp_path / "README.md"
    file2.write_text("# Doc", encoding="utf-8")

    scanner = IncrementalFileScanner(repo_root=tmp_path)
    changeset, manifest = scanner.scan()

    assert sorted(changeset.added) == ["README.md", "app.py"]
    assert changeset.modified == []
    assert changeset.deleted == []
    assert changeset.unchanged == []
    assert changeset.has_changes

    assert "app.py" in manifest.file_hashes
    assert "README.md" in manifest.file_hashes


def test_scanner_incremental_changes(tmp_path: Path):
    file1 = tmp_path / "app.py"
    file1.write_text("x = 1\n", encoding="utf-8")
    file2 = tmp_path / "util.py"
    file2.write_text("y = 2\n", encoding="utf-8")

    scanner = IncrementalFileScanner(repo_root=tmp_path)
    _, manifest_v1 = scanner.scan()

    # Case 1: Unchanged run
    changeset_v2, manifest_v2 = scanner.scan(previous_manifest=manifest_v1)
    assert not changeset_v2.has_changes
    assert sorted(changeset_v2.unchanged) == ["app.py", "util.py"]

    # Case 2: Modify app.py, add new.py, delete util.py
    file1.write_text("x = 999\n", encoding="utf-8")
    file3 = tmp_path / "new.py"
    file3.write_text("z = 3\n", encoding="utf-8")
    file2.unlink()

    changeset_v3, manifest_v3 = scanner.scan(previous_manifest=manifest_v2)
    assert changeset_v3.has_changes
    assert changeset_v3.modified == ["app.py"]
    assert changeset_v3.added == ["new.py"]
    assert changeset_v3.deleted == ["util.py"]
    assert changeset_v3.unchanged == []

    assert "new.py" in manifest_v3.file_hashes
    assert "util.py" not in manifest_v3.file_hashes


def test_scanner_ignored_directories_and_extensions(tmp_path: Path):
    # Valid file
    (tmp_path / "valid.py").write_text("a = 1", encoding="utf-8")

    # Ignored directory (.venv)
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "lib.py").write_text("b = 2", encoding="utf-8")

    # Ignored directory (.git)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config", encoding="utf-8")

    # Ignored extension (.pyc)
    (tmp_path / "compiled.pyc").write_bytes(b"\x00\x01\x02")

    scanner = IncrementalFileScanner(repo_root=tmp_path)
    files = scanner.scan_files()

    assert "valid.py" in files
    assert ".venv/lib.py" not in files
    assert ".git/config" not in files
    assert "compiled.pyc" not in files


def test_scanner_gitignore_support(tmp_path: Path):
    (tmp_path / "keep.py").write_text("k = 1", encoding="utf-8")
    (tmp_path / "secret.env").write_text("secret", encoding="utf-8")
    (tmp_path / "temp_cache.json").write_text("{}", encoding="utf-8")

    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("secret.*\ntemp_*\n", encoding="utf-8")

    scanner = IncrementalFileScanner(repo_root=tmp_path)
    files = scanner.scan_files()

    assert "keep.py" in files
    assert "secret.env" not in files
    assert "temp_cache.json" not in files


def test_manifest_load_and_save(tmp_path: Path):
    manifest_path = tmp_path / ".pr-inspector" / "index_manifest.json"
    scanner = IncrementalFileScanner(repo_root=tmp_path, manifest_path=manifest_path)

    assert scanner.load_manifest() is None

    manifest = IndexManifest(version=1, file_hashes={"a.py": "hash_a"})
    scanner.save_manifest(manifest)

    loaded = scanner.load_manifest()
    assert loaded is not None
    assert loaded.version == 1
    assert loaded.file_hashes == {"a.py": "hash_a"}
