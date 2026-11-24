"""Application use case for indexing repository files into structure-aware chunks."""

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from pr_inspector.domain.entities import CodeChunk, IndexManifest
from pr_inspector.domain.protocols import ChunkStore
from pr_inspector.infrastructure.indexer.chunk_store import JsonFileChunkStore
from pr_inspector.infrastructure.indexer.composite_chunker import CompositeChunker
from pr_inspector.infrastructure.indexer.file_scanner import IncrementalFileScanner


@dataclass(frozen=True)
class IndexingResult:
    """Outcome and metrics of a repository indexing run."""

    total_files_scanned: int
    added_files: int
    modified_files: int
    deleted_files: int
    unchanged_files: int
    total_chunks: int
    duration_ms: float


class IndexRepositoryUseCase:
    """Coordinates file scanning, chunking, and persistent storage of repository index."""

    def __init__(
        self,
        repo_root: Path | str,
        scanner: IncrementalFileScanner | None = None,
        chunker: CompositeChunker | None = None,
        chunk_store: ChunkStore | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.scanner = scanner or IncrementalFileScanner(self.repo_root)
        self.chunker = chunker or CompositeChunker()
        self.chunk_store = chunk_store or JsonFileChunkStore(
            self.repo_root / ".pr-inspector" / "chunks.json"
        )

    def execute(self, force: bool = False, clean: bool = False) -> IndexingResult:
        """Execute indexing over the target repository."""
        start_time = time.perf_counter()

        if clean:
            dot_dir = self.repo_root / ".pr-inspector"
            if dot_dir.is_dir():
                shutil.rmtree(dot_dir)

        previous_manifest = (
            IndexManifest(version=1, file_hashes={})
            if force
            else (None if clean else self.scanner.load_manifest())
        )
        changeset, new_manifest = self.scanner.scan(previous_manifest=previous_manifest)

        if force or clean or previous_manifest is None:
            chunks: list[CodeChunk] = []
        else:
            loaded_chunks = self.chunk_store.load_chunks()
            evicted_files = set(changeset.modified) | set(changeset.deleted)
            chunks = [c for c in loaded_chunks if c.file_path not in evicted_files]

        for rel_path in changeset.added + changeset.modified:
            full_path = self.repo_root / rel_path
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                new_chunks = self.chunker.chunk_file(rel_path, content)
                chunks.extend(new_chunks)
            except (OSError, PermissionError):
                continue

        self.chunk_store.save_chunks(chunks)
        self.scanner.save_manifest(new_manifest)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return IndexingResult(
            total_files_scanned=len(new_manifest.file_hashes),
            added_files=len(changeset.added),
            modified_files=len(changeset.modified),
            deleted_files=len(changeset.deleted),
            unchanged_files=len(changeset.unchanged),
            total_chunks=len(chunks),
            duration_ms=duration_ms,
        )
