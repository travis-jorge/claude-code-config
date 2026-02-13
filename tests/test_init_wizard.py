"""Tests for init wizard and validation functions."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from claude_setup.init import validate_config_source
from claude_setup.cli import _parse_github_url, _detect_github_remote


class TestValidateConfigSource:
    """Test config source validation."""

    def test_validate_nonexistent_path(self, tmp_path):
        """Test validation of non-existent path."""
        nonexistent = tmp_path / "does_not_exist"
        is_valid, message, resolved = validate_config_source(nonexistent)

        assert not is_valid
        assert "does not exist" in message
        assert resolved is None

    def test_validate_file_not_directory(self, tmp_path):
        """Test validation fails for files."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")

        is_valid, message, resolved = validate_config_source(file_path)

        assert not is_valid
        assert "not a directory" in message
        assert resolved is None

    def test_validate_missing_manifest(self, tmp_path):
        """Test validation fails without manifest.json."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        is_valid, message, resolved = validate_config_source(config_dir)

        assert not is_valid
        assert "manifest.json not found" in message
        assert resolved is None

    def test_validate_valid_manifest_at_root(self, tmp_path):
        """Test validation succeeds with manifest at root."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        manifest = {
            "version": "1.0.0",
            "categories": [
                {"name": "core", "description": "Core files"}
            ]
        }
        (config_dir / "manifest.json").write_text(json.dumps(manifest))

        is_valid, message, resolved = validate_config_source(config_dir)

        assert is_valid
        assert "Valid config source" in message
        assert resolved is None

    def test_validate_manifest_one_level_deep(self, tmp_path):
        """Test validation finds manifest one level deep (zip extraction)."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Create a subdirectory with manifest (common with zip extractions)
        subdir = config_dir / "actual-config"
        subdir.mkdir()

        manifest = {
            "version": "1.0.0",
            "categories": [
                {"name": "core", "description": "Core files"}
            ]
        }
        (subdir / "manifest.json").write_text(json.dumps(manifest))

        is_valid, message, resolved = validate_config_source(config_dir)

        assert is_valid
        assert "subdirectory" in message
        assert resolved == subdir

    def test_validate_invalid_json(self, tmp_path):
        """Test validation fails with invalid JSON."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        (config_dir / "manifest.json").write_text("{ invalid json }")

        is_valid, message, resolved = validate_config_source(config_dir)

        assert not is_valid
        assert "not valid JSON" in message
        assert resolved is None

    def test_validate_missing_categories_field(self, tmp_path):
        """Test validation fails without categories field."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        manifest = {"version": "1.0.0"}
        (config_dir / "manifest.json").write_text(json.dumps(manifest))

        is_valid, message, resolved = validate_config_source(config_dir)

        assert not is_valid
        assert "missing 'categories'" in message
        assert resolved is None

    def test_validate_empty_categories(self, tmp_path):
        """Test validation fails with empty categories."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        manifest = {"version": "1.0.0", "categories": []}
        (config_dir / "manifest.json").write_text(json.dumps(manifest))

        is_valid, message, resolved = validate_config_source(config_dir)

        assert not is_valid
        assert "non-empty list" in message
        assert resolved is None

    def test_validate_categories_not_list(self, tmp_path):
        """Test validation fails when categories is not a list."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        manifest = {"version": "1.0.0", "categories": "not-a-list"}
        (config_dir / "manifest.json").write_text(json.dumps(manifest))

        is_valid, message, resolved = validate_config_source(config_dir)

        assert not is_valid
        assert "non-empty list" in message
        assert resolved is None


class TestParseGitHubUrl:
    """Test GitHub URL parsing."""

    def test_parse_https_url(self):
        """Test parsing HTTPS GitHub URL."""
        url = "https://github.com/owner/repo"
        result = _parse_github_url(url)

        assert result == ("owner", "repo")

    def test_parse_https_url_with_git_suffix(self):
        """Test parsing HTTPS URL with .git suffix."""
        url = "https://github.com/owner/repo.git"
        result = _parse_github_url(url)

        assert result == ("owner", "repo")

    def test_parse_https_url_with_trailing_slash(self):
        """Test parsing HTTPS URL with trailing slash."""
        url = "https://github.com/owner/repo/"
        result = _parse_github_url(url)

        assert result == ("owner", "repo")

    def test_parse_ssh_url(self):
        """Test parsing SSH GitHub URL."""
        url = "git@github.com:owner/repo"
        result = _parse_github_url(url)

        assert result == ("owner", "repo")

    def test_parse_ssh_url_with_git_suffix(self):
        """Test parsing SSH URL with .git suffix."""
        url = "git@github.com:owner/repo.git"
        result = _parse_github_url(url)

        assert result == ("owner", "repo")

    def test_parse_bare_url(self):
        """Test parsing bare github.com URL."""
        url = "github.com/owner/repo"
        result = _parse_github_url(url)

        assert result == ("owner", "repo")

    def test_parse_http_url(self):
        """Test parsing HTTP (not HTTPS) GitHub URL."""
        url = "http://github.com/owner/repo"
        result = _parse_github_url(url)

        assert result == ("owner", "repo")

    def test_parse_non_github_url(self):
        """Test parsing non-GitHub URL returns None."""
        urls = [
            "https://gitlab.com/owner/repo",
            "https://bitbucket.org/owner/repo",
            "https://example.com/repo",
            "not-a-url",
        ]

        for url in urls:
            result = _parse_github_url(url)
            assert result is None, f"Expected None for {url}"

    def test_parse_malformed_urls(self):
        """Test parsing malformed URLs returns None."""
        urls = [
            "github.com/owner",  # Missing repo
            "github.com",  # Just domain
            "",  # Empty string
        ]

        for url in urls:
            result = _parse_github_url(url)
            assert result is None, f"Expected None for {url}"


class TestDetectGitHubRemote:
    """Test GitHub remote detection."""

    def test_detect_github_remote_https(self, tmp_path):
        """Test detecting GitHub remote with HTTPS URL."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="https://github.com/owner/repo.git\n",
                returncode=0
            )

            result = _detect_github_remote(repo_path)

            assert result == "owner/repo"
            mock_run.assert_called_once_with(
                ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True,
            )

    def test_detect_github_remote_ssh(self, tmp_path):
        """Test detecting GitHub remote with SSH URL."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="git@github.com:owner/repo.git\n",
                returncode=0
            )

            result = _detect_github_remote(repo_path)

            assert result == "owner/repo"

    def test_detect_non_github_remote(self, tmp_path):
        """Test detecting non-GitHub remote returns None."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="https://gitlab.com/owner/repo.git\n",
                returncode=0
            )

            result = _detect_github_remote(repo_path)

            assert result is None

    def test_detect_no_remote(self, tmp_path):
        """Test no remote returns None."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git", stderr="fatal: No remote configured"
            )

            result = _detect_github_remote(repo_path)

            assert result is None

    def test_detect_git_not_installed(self, tmp_path):
        """Test git not installed returns None."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")

            result = _detect_github_remote(repo_path)

            assert result is None

    def test_detect_not_a_git_repo(self, tmp_path):
        """Test non-git directory returns None."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                128, "git", stderr="fatal: not a git repository"
            )

            result = _detect_github_remote(repo_path)

            assert result is None
