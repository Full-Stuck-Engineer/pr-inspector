"""Persistent JSON file-backed chunk store for codebase indexing."""

import json
from pathlib import Path

from pr_inspector.domain.entities import CodeChunk
from pr_inspector.domain.protocols import ChunkStore


class JsonFileChunkStore(ChunkStore):
    """Stores and loads CodeChunk collections to and from a local JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).resolve()

    def load_chunks(self) -> list[CodeChunk]:
        """Load code chunks from disk. Returns empty list if missing or corrupt."""
        if not self.path.is_file():
            return []

        try:
            raw_text = self.path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            if not isinstance(data, list):
                return []
            return [CodeChunk.model_validate(item) for item in data]
        except Exception:
            return []

    def save_chunks(self, chunks: list[CodeChunk]) -> None:
        """Persist code chunks to disk, ensuring directory exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [chunk.model_dump() for chunk in chunks]
        self.path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
