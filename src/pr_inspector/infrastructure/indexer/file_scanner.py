"""Incremental repository file scanner using SHA256 content hashing."""

import fnmatch
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pr_inspector.domain.entities import FileChangeSet, IndexManifest

DEFAULT_IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pr-inspector",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".eggs",
}

DEFAULT_IGNORED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".dylib",
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".svg",
}

INDEXABLE_EXTENSIONS = {
    ".py",
    ".md",
    ".markdown",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".ini",
    ".cfg",
    ".sh",
}


class IncrementalFileScanner:
    """Scans repository files and detects added, modified, and deleted files via SHA256."""

    def __init__(
        self,
        repo_root: Path | str,
        manifest_path: Path | str | None = None,
        ignored_dirs: set[str] | None = None,
        indexable_extensions: set[str] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.manifest_path = (
            Path(manifest_path).resolve()
            if manifest_path
            else self.repo_root / ".pr-inspector" / "index_manifest.json"
        )
        self.ignored_dirs = ignored_dirs or DEFAULT_IGNORED_DIRS
        self.indexable_extensions = indexable_extensions or INDEXABLE_EXTENSIONS
        self._gitignore_patterns = self._load_gitignore_patterns()

    def _load_gitignore_patterns(self) -> list[str]:
        """Read patterns from .gitignore in repository root if present."""
        gitignore_file = self.repo_root / ".gitignore"
        patterns: list[str] = []
        if gitignore_file.is_file():
            for line in gitignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    patterns.append(stripped.rstrip("/"))
        return patterns

    def is_ignored(self, relative_path: Path) -> bool:
        """Check if relative path matches default exclusions or .gitignore."""
        # 1. Check directory components against ignored dirs
        parts = relative_path.parts
        for part in parts[:-1]:
            if part in self.ignored_dirs or part.startswith("."):
                return True

        filename = relative_path.name
        # 2. Check filename / extension
        if filename.startswith(".") and filename != ".gitignore":
            return True
        if relative_path.suffix.lower() in DEFAULT_IGNORED_EXTENSIONS:
            return True
        if relative_path.suffix.lower() not in self.indexable_extensions:
            return True

        # 3. Check gitignore patterns
        path_str = str(relative_path)
        for pattern in self._gitignore_patterns:
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(filename, pattern):
                return True
            if any(fnmatch.fnmatch(p, pattern) for p in parts):
                return True

        return False

    def compute_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hexadecimal digest of file content."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def scan_files(self) -> dict[str, str]:
        """Scan repository and return mapping of relative path to SHA256 digest."""
        current_hashes: dict[str, str] = {}

        for path in self.repo_root.rglob("*"):
            if not path.is_file():
                continue

            try:
                rel_path = path.relative_to(self.repo_root)
            except ValueError:
                continue

            if self.is_ignored(rel_path):
                continue

            try:
                current_hashes[str(rel_path)] = self.compute_sha256(path)
            except (OSError, PermissionError):
                continue

        return current_hashes

    def scan(
        self, previous_manifest: IndexManifest | None = None
    ) -> tuple[FileChangeSet, IndexManifest]:
        """Compare current repo state with previous manifest to identify change sets."""
        if previous_manifest is None:
            previous_manifest = self.load_manifest()

        prev_hashes = previous_manifest.file_hashes if previous_manifest else {}
        current_hashes = self.scan_files()

        added: list[str] = []
        modified: list[str] = []
        unchanged: list[str] = []
        deleted: list[str] = []

        for file_path, current_hash in current_hashes.items():
            if file_path not in prev_hashes:
                added.append(file_path)
            elif prev_hashes[file_path] != current_hash:
                modified.append(file_path)
            else:
                unchanged.append(file_path)

        for file_path in prev_hashes:
            if file_path not in current_hashes:
                deleted.append(file_path)

        changeset = FileChangeSet(
            added=sorted(added),
            modified=sorted(modified),
            deleted=sorted(deleted),
            unchanged=sorted(unchanged),
        )

        new_manifest = IndexManifest(
            version=1,
            file_hashes=current_hashes,
            updated_at=datetime.now(UTC).isoformat(),
        )

        return changeset, new_manifest

    def load_manifest(self) -> IndexManifest | None:
        """Load manifest from disk if present."""
        if not self.manifest_path.is_file():
            return None
        try:
            return IndexManifest.model_validate_json(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_manifest(self, manifest: IndexManifest) -> None:
        """Save manifest to disk, creating parent directories if needed."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
