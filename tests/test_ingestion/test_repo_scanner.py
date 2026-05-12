"""Tests for the RepoScanner."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from mysterial.ingestion.repo_scanner import RepoScanner
from mysterial.models.code import Language


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a minimal fake repo directory with the given files."""
    for relative, content in files.items():
        full = tmp_path / relative
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return tmp_path


class TestRepoScanner:
    def test_scan_local_python(self, tmp_path: Path) -> None:
        repo_dir = _make_repo(
            tmp_path,
            {
                "src/main.py": "def hello(): pass",
                "src/utils.py": "x = 1",
            },
        )
        scanner = RepoScanner(workspace_dir=str(tmp_path / "ws"))
        records = list(scanner.scan_local("myrepo", repo_dir))

        assert len(records) == 2
        paths = {r.path for r in records}
        assert "src/main.py" in paths
        assert "src/utils.py" in paths
        for r in records:
            assert r.repo == "myrepo"
            assert r.language == Language.PYTHON

    def test_scan_local_javascript(self, tmp_path: Path) -> None:
        repo_dir = _make_repo(
            tmp_path,
            {"index.js": "function hello() {}"},
        )
        scanner = RepoScanner(workspace_dir=str(tmp_path / "ws"))
        records = list(scanner.scan_local("jsrepo", repo_dir))

        assert len(records) == 1
        assert records[0].language == Language.JAVASCRIPT

    def test_scan_local_typescript(self, tmp_path: Path) -> None:
        repo_dir = _make_repo(
            tmp_path,
            {"app.ts": "const x: number = 1;"},
        )
        scanner = RepoScanner(workspace_dir=str(tmp_path / "ws"))
        records = list(scanner.scan_local("tsrepo", repo_dir))

        assert len(records) == 1
        assert records[0].language == Language.TYPESCRIPT

    def test_skips_non_source_files(self, tmp_path: Path) -> None:
        repo_dir = _make_repo(
            tmp_path,
            {
                "README.md": "# readme",
                "Makefile": "all: build",
                "src/main.py": "pass",
            },
        )
        scanner = RepoScanner(workspace_dir=str(tmp_path / "ws"))
        records = list(scanner.scan_local("repo", repo_dir))

        assert len(records) == 1
        assert records[0].path == "src/main.py"

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        repo_dir = _make_repo(
            tmp_path,
            {
                "src/app.js": "function main() {}",
                "node_modules/lib/index.js": "module.exports = {}",
            },
        )
        scanner = RepoScanner(workspace_dir=str(tmp_path / "ws"))
        records = list(scanner.scan_local("repo", repo_dir))

        assert len(records) == 1
        assert "node_modules" not in records[0].path

    def test_skips_files_over_size_limit(self, tmp_path: Path) -> None:
        large_content = "x = 1\n" * 200_000  # > 1 MB
        repo_dir = _make_repo(
            tmp_path,
            {
                "tiny.py": "pass",
                "huge.py": large_content,
            },
        )
        scanner = RepoScanner(workspace_dir=str(tmp_path / "ws"))
        records = list(scanner.scan_local("repo", repo_dir))

        assert len(records) == 1
        assert records[0].path == "tiny.py"

    def test_content_hash_is_stable(self, tmp_path: Path) -> None:
        repo_dir = _make_repo(tmp_path, {"a.py": "pass"})
        scanner = RepoScanner(workspace_dir=str(tmp_path / "ws"))
        records1 = list(scanner.scan_local("repo", repo_dir))
        records2 = list(scanner.scan_local("repo", repo_dir))
        assert records1[0].content_hash == records2[0].content_hash
