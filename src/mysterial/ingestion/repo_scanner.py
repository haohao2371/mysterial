"""Repository scanner – clones / updates git repos and discovers source files."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Iterator

import git

from mysterial.config import settings
from mysterial.models.code import FileRecord, Language, Repository

logger = logging.getLogger(__name__)

# Map file extensions → Language
_EXT_LANGUAGE: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
}


class RepoScanner:
    """Clone (or update) a repository, then yield FileRecord objects for each source file."""

    def __init__(self, workspace_dir: str | None = None) -> None:
        self.workspace_dir = Path(workspace_dir or settings.workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────

    def register_and_scan(self, repo: Repository) -> Iterator[FileRecord]:
        """Clone (or pull) *repo* and yield a FileRecord for every supported source file."""
        local_path = self._ensure_local(repo)
        repo.local_path = str(local_path)
        yield from self._scan_directory(local_path, repo.name)

    def scan_local(self, repo_name: str, local_path: str | Path) -> Iterator[FileRecord]:
        """Scan a repository that is already present on disk."""
        yield from self._scan_directory(Path(local_path), repo_name)

    # ── Internal helpers ────────────────────────────────────────────────

    def _ensure_local(self, repo: Repository) -> Path:
        local_path = self.workspace_dir / repo.name
        if local_path.exists():
            logger.info("Pulling latest changes for %s", repo.name)
            try:
                git_repo = git.Repo(local_path)
                git_repo.remotes.origin.pull(repo.branch)
            except git.GitCommandError as exc:
                logger.warning("Pull failed for %s: %s – re-cloning", repo.name, exc)
                shutil.rmtree(local_path)
                self._clone(repo, local_path)
        else:
            self._clone(repo, local_path)
        return local_path

    def _clone(self, repo: Repository, local_path: Path) -> None:
        logger.info("Cloning %s → %s", repo.url, local_path)
        git.Repo.clone_from(repo.url, local_path, branch=repo.branch, depth=1)

    def _scan_directory(self, root: Path, repo_name: str) -> Iterator[FileRecord]:
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories and common non-source directories
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(".")
                and d
                not in {
                    "node_modules",
                    "__pycache__",
                    ".git",
                    "venv",
                    ".venv",
                    "dist",
                    "build",
                }
            ]
            for filename in filenames:
                full_path = Path(dirpath) / filename
                language = _EXT_LANGUAGE.get(full_path.suffix.lower())
                if language is None:
                    continue
                try:
                    size = full_path.stat().st_size
                    if size > settings.max_file_size_bytes:
                        logger.debug("Skipping large file %s (%d bytes)", full_path, size)
                        continue
                    content = full_path.read_bytes()
                    content_hash = hashlib.sha256(content).hexdigest()
                    relative_path = str(full_path.relative_to(root))
                    yield FileRecord(
                        repo=repo_name,
                        path=relative_path,
                        language=language,
                        size_bytes=size,
                        content_hash=content_hash,
                    )
                except OSError as exc:
                    logger.warning("Could not read %s: %s", full_path, exc)
