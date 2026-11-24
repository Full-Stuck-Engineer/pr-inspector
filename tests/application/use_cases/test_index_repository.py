"""Unit tests for IndexRepositoryUseCase."""

from pathlib import Path

from pr_inspector.application.use_cases.index_repository import IndexRepositoryUseCase
from pr_inspector.infrastructure.indexer.chunk_store import JsonFileChunkStore


def _setup_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    src = repo / "src"
    src.mkdir()
    (src / "math_utils.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (src / "service.py").write_text(
        "class WorkerService:\n    def run(self):\n        return True\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text(
        "# Project Overview\nThis is a sample project.\n",
        encoding="utf-8",
    )
    return repo


def test_fresh_repo_indexing(tmp_path):
    repo = _setup_test_repo(tmp_path)
    use_case = IndexRepositoryUseCase(repo)

    result = use_case.execute()

    assert result.total_files_scanned == 3
    assert result.added_files == 3
    assert result.modified_files == 0
    assert result.deleted_files == 0
    assert result.total_chunks >= 3
    assert result.duration_ms >= 0

    assert (repo / ".pr-inspector" / "index_manifest.json").is_file()
    assert (repo / ".pr-inspector" / "chunks.json").is_file()

    chunk_store = JsonFileChunkStore(repo / ".pr-inspector" / "chunks.json")
    chunks = chunk_store.load_chunks()
    assert len(chunks) == result.total_chunks


def test_incremental_indexing_no_changes(tmp_path):
    repo = _setup_test_repo(tmp_path)
    use_case = IndexRepositoryUseCase(repo)

    first_result = use_case.execute()
    second_result = use_case.execute()

    assert second_result.total_files_scanned == 3
    assert second_result.added_files == 0
    assert second_result.modified_files == 0
    assert second_result.deleted_files == 0
    assert second_result.unchanged_files == 3
    assert second_result.total_chunks == first_result.total_chunks


def test_incremental_indexing_with_modifications_and_deletions(tmp_path):
    repo = _setup_test_repo(tmp_path)
    use_case = IndexRepositoryUseCase(repo)
    use_case.execute()

    # Modify a file
    (repo / "src" / "math_utils.py").write_text(
        "def add(a, b):\n    return a + b + 0\n",
        encoding="utf-8",
    )
    # Delete a file
    (repo / "src" / "service.py").unlink()
    # Add a new file
    (repo / "src" / "helper.py").write_text(
        "def help_me():\n    return 'ok'\n",
        encoding="utf-8",
    )

    result = use_case.execute()

    assert result.total_files_scanned == 3
    assert result.added_files == 1
    assert result.modified_files == 1
    assert result.deleted_files == 1
    assert result.unchanged_files == 1

    chunks = JsonFileChunkStore(repo / ".pr-inspector" / "chunks.json").load_chunks()
    file_paths = {c.file_path for c in chunks}
    assert "src/math_utils.py" in file_paths
    assert "src/helper.py" in file_paths
    assert "src/service.py" not in file_paths


def test_force_reindexing(tmp_path):
    repo = _setup_test_repo(tmp_path)
    use_case = IndexRepositoryUseCase(repo)
    use_case.execute()

    # Force reindexing treats all files as added/re-indexed
    result = use_case.execute(force=True)
    assert result.total_files_scanned == 3
    assert result.added_files == 3
    assert result.modified_files == 0
    assert result.deleted_files == 0


def test_clean_indexing(tmp_path):
    repo = _setup_test_repo(tmp_path)
    use_case = IndexRepositoryUseCase(repo)
    use_case.execute()

    assert (repo / ".pr-inspector").is_dir()

    # Clean clears directory and indexes cleanly
    result = use_case.execute(clean=True)
    assert result.total_files_scanned == 3
    assert result.added_files == 3
    assert (repo / ".pr-inspector" / "chunks.json").is_file()
