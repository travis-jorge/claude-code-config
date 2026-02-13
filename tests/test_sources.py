"""Tests for source management."""

import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_setup.sources import (
    LocalSource,
    GitHubSource,
    ZipSource,
    SourceManager,
    SourceError,
)


class TestLocalSource:
    """Test LocalSource implementation."""

    def test_local_source_fetch_existing_directory(self, tmp_path):
        """Test fetching from existing local directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("content")

        cache_dir = tmp_path / "cache"
        config = {"path": str(source_dir)}

        source = LocalSource("test-source", config)
        result = source.fetch(cache_dir)

        assert result.exists()
        assert (result / "test.txt").read_text() == "content"

    def test_local_source_fetch_nonexistent_directory(self, tmp_path):
        """Test fetching from non-existent directory raises error."""
        cache_dir = tmp_path / "cache"
        config = {"path": str(tmp_path / "nonexistent")}

        source = LocalSource("test-source", config)

        with pytest.raises(SourceError, match="Local path not found"):
            source.fetch(cache_dir)

    def test_local_source_copies_to_cache(self, tmp_path):
        """Test local source copies files to cache."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")

        cache_dir = tmp_path / "cache"
        config = {"path": str(source_dir)}

        source = LocalSource("test-source", config)
        result = source.fetch(cache_dir)

        # Verify files copied to cache
        assert (result / "file1.txt").read_text() == "content1"
        assert (result / "file2.txt").read_text() == "content2"

    def test_local_source_preserves_directory_structure(self, tmp_path):
        """Test local source preserves subdirectories."""
        source_dir = tmp_path / "source"
        subdir = source_dir / "subdir"
        subdir.mkdir(parents=True)
        (subdir / "nested.txt").write_text("nested content")

        cache_dir = tmp_path / "cache"
        config = {"path": str(source_dir)}

        source = LocalSource("test-source", config)
        result = source.fetch(cache_dir)

        assert (result / "subdir" / "nested.txt").read_text() == "nested content"


class TestZipSource:
    """Test ZipSource implementation."""

    def test_zip_source_fetch(self, tmp_path):
        """Test fetching and extracting zip file."""
        # Create a zip file
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("zip content")

        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(source_dir / "file.txt", "file.txt")

        cache_dir = tmp_path / "cache"
        config = {"url": "https://example.com/test.zip"}

        source = ZipSource("test-source", config)

        with patch("claude_setup.sources.urlretrieve") as mock_urlretrieve:
            # Mock urlretrieve to copy our test zip file
            def fake_urlretrieve(url, dest):
                shutil.copy(zip_path, dest)
                return str(dest), None

            mock_urlretrieve.side_effect = fake_urlretrieve

            result = source.fetch(cache_dir)

            assert result.exists()
            assert (result / "file.txt").read_text() == "zip content"

    def test_zip_source_flattens_single_directory(self, tmp_path):
        """Test zip with single top-level directory gets flattened."""
        # Create zip with single top-level directory
        source_dir = tmp_path / "source"
        wrapper_dir = source_dir / "wrapper"
        wrapper_dir.mkdir(parents=True)
        (wrapper_dir / "file.txt").write_text("content")

        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(wrapper_dir / "file.txt", "wrapper/file.txt")

        cache_dir = tmp_path / "cache"
        config = {"url": "https://example.com/test.zip"}

        source = ZipSource("test-source", config)

        with patch("claude_setup.sources.urlretrieve") as mock_urlretrieve:
            # Mock urlretrieve to copy our test zip file
            def fake_urlretrieve(url, dest):
                shutil.copy(zip_path, dest)
                return str(dest), None

            mock_urlretrieve.side_effect = fake_urlretrieve

            result = source.fetch(cache_dir)

            # File should be at root level, not in wrapper directory
            assert (result / "file.txt").exists()
            assert (result / "file.txt").read_text() == "content"

    def test_zip_source_preserves_multiple_directories(self, tmp_path):
        """Test zip with multiple top-level items is not flattened."""
        # Create zip with multiple top-level items
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content1")

        subdir = source_dir / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").write_text("content2")

        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(source_dir / "file1.txt", "file1.txt")
            zf.write(subdir / "file2.txt", "subdir/file2.txt")

        cache_dir = tmp_path / "cache"
        config = {"url": "https://example.com/test.zip"}

        source = ZipSource("test-source", config)

        with patch("claude_setup.sources.urlretrieve") as mock_urlretrieve:
            # Mock urlretrieve to copy our test zip file
            def fake_urlretrieve(url, dest):
                shutil.copy(zip_path, dest)
                return str(dest), None

            mock_urlretrieve.side_effect = fake_urlretrieve

            result = source.fetch(cache_dir)

            # Both should exist at expected locations
            assert (result / "file1.txt").read_text() == "content1"
            assert (result / "subdir" / "file2.txt").read_text() == "content2"

    def test_zip_source_fetch_error(self, tmp_path):
        """Test zip fetch error is handled."""
        cache_dir = tmp_path / "cache"
        config = {"url": "https://example.com/nonexistent.zip"}

        source = ZipSource("test-source", config)

        with patch("claude_setup.sources.urlretrieve") as mock_urlretrieve:
            mock_urlretrieve.side_effect = Exception("Network error")

            with pytest.raises(SourceError, match="Zip download/extract failed"):
                source.fetch(cache_dir)


class TestGitHubSource:
    """Test GitHubSource implementation."""

    def test_github_source_clone_new_repo(self, tmp_path):
        """Test cloning a new GitHub repository."""
        cache_dir = tmp_path / "cache"
        config = {
            "repo": "owner/repo",
            "ref": "main",
        }

        source = GitHubSource("test-source", config)

        with patch("subprocess.run") as mock_run:
            # Mock needs to create the directory structure
            def fake_run(*args, **kwargs):
                cmd = args[0]
                if "clone" in cmd:
                    # Extract destination path (last arg in git clone command)
                    dest = Path(cmd[-1])
                    dest.mkdir(parents=True, exist_ok=True)
                return MagicMock(returncode=0)

            mock_run.side_effect = fake_run

            result = source.fetch(cache_dir)

            # Verify git clone was called
            assert mock_run.call_count >= 1
            clone_call = mock_run.call_args_list[0]
            assert "git" in clone_call[0][0]
            assert "clone" in clone_call[0][0]
            assert "https://github.com/owner/repo.git" in clone_call[0][0]

    def test_github_source_with_token(self, tmp_path):
        """Test cloning with authentication token."""
        cache_dir = tmp_path / "cache"
        config = {
            "repo": "owner/repo",
            "ref": "main",
            "token": "test-token",
        }

        source = GitHubSource("test-source", config)

        with patch("subprocess.run") as mock_run:
            # Mock needs to create the directory structure
            def fake_run(*args, **kwargs):
                cmd = args[0]
                if "clone" in cmd:
                    # Extract destination path (last arg in git clone command)
                    dest = Path(cmd[-1])
                    dest.mkdir(parents=True, exist_ok=True)
                return MagicMock(returncode=0)

            mock_run.side_effect = fake_run

            result = source.fetch(cache_dir)

            # Verify token was used in URL
            clone_call = mock_run.call_args_list[0]
            url_with_token = "https://test-token@github.com/owner/repo.git"
            assert url_with_token in clone_call[0][0]

    def test_github_source_pull_existing_repo(self, tmp_path):
        """Test pulling updates to existing repository."""
        cache_dir = tmp_path / "cache"
        repo_dir = cache_dir / "test-source"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()  # Simulate existing repo

        config = {
            "repo": "owner/repo",
            "ref": "main",
        }

        source = GitHubSource("test-source", config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = source.fetch(cache_dir)

            # Verify git pull was called instead of clone
            calls = [call[0][0] for call in mock_run.call_args_list]
            assert any("pull" in str(call) for call in calls)

    def test_github_source_clone_failure(self, tmp_path):
        """Test git clone failure raises error."""
        cache_dir = tmp_path / "cache"
        config = {
            "repo": "owner/repo",
            "ref": "main",
        }

        source = GitHubSource("test-source", config)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git", stderr="fatal: repository not found"
            )

            with pytest.raises(SourceError, match="Git operation failed"):
                source.fetch(cache_dir)


class TestSourceManager:
    """Test SourceManager."""

    def test_source_manager_load_sources_from_file(self, tmp_path):
        """Test loading sources from configuration file."""
        sources_file = tmp_path / "sources.json"
        sources_config = {
            "version": "1.0",
            "sources": [
                {
                    "name": "local-source",
                    "type": "local",
                    "path": str(tmp_path / "config"),
                }
            ],
        }
        sources_file.write_text(json.dumps(sources_config))

        # Create the config directory
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        cache_dir = tmp_path / "cache"
        manager = SourceManager(cache_dir)
        manager.load_sources(sources_file)

        assert len(manager.sources) == 1
        assert manager.sources[0].name == "local-source"

    def test_source_manager_get_primary_source(self, tmp_path):
        """Test getting primary source."""
        source_dir = tmp_path / "config"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("content")

        sources_file = tmp_path / "sources.json"
        sources_config = {
            "version": "1.0",
            "sources": [
                {
                    "name": "primary",
                    "type": "local",
                    "path": str(source_dir),
                }
            ],
        }
        sources_file.write_text(json.dumps(sources_config))

        cache_dir = tmp_path / "cache"
        manager = SourceManager(cache_dir)
        manager.load_sources(sources_file)

        result = manager.get_primary_source()

        assert result is not None
        assert (result / "test.txt").read_text() == "content"

    def test_source_manager_no_sources(self, tmp_path):
        """Test get_primary_source with no sources returns None."""
        cache_dir = tmp_path / "cache"
        manager = SourceManager(cache_dir)

        result = manager.get_primary_source()

        assert result is None

    def test_source_manager_invalid_source_type(self, tmp_path):
        """Test invalid source type raises error."""
        sources_file = tmp_path / "sources.json"
        sources_config = {
            "version": "1.0",
            "sources": [
                {
                    "name": "invalid",
                    "type": "invalid-type",
                }
            ],
        }
        sources_file.write_text(json.dumps(sources_config))

        cache_dir = tmp_path / "cache"
        manager = SourceManager(cache_dir)

        with pytest.raises(SourceError, match="Unknown source type"):
            manager.load_sources(sources_file)
