"""Tests for plugin management."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_setup.plugins import PluginManager


class TestPluginManager:
    """Test PluginManager functionality."""

    def test_check_installed_plugins_no_file(self, tmp_path):
        """Test checking installed plugins when no plugins file exists."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        required = [{"name": "plugin1", "description": "Test plugin"}]
        manager = PluginManager(claude_dir, required)

        status = manager.check_installed()

        assert status == {"plugin1": False}

    def test_check_installed_plugins_with_file(self, tmp_path):
        """Test checking installed plugins with existing plugins file."""
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)

        # Create installed_plugins.json with correct structure
        installed = {
            "plugins": {
                "plugin1": {"version": "1.0.0"},
                "plugin2": {"version": "2.0.0"},
            }
        }
        plugins_file = plugins_dir / "installed_plugins.json"
        plugins_file.write_text(json.dumps(installed))

        required = [
            {"name": "plugin1", "description": "Plugin 1"},
            {"name": "plugin2", "description": "Plugin 2"},
            {"name": "plugin3", "description": "Plugin 3"},
        ]
        manager = PluginManager(claude_dir, required)

        status = manager.check_installed()

        assert status == {
            "plugin1": True,
            "plugin2": True,
            "plugin3": False,
        }

    def test_check_installed_invalid_json(self, tmp_path):
        """Test checking installed plugins with invalid JSON."""
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)

        # Create invalid JSON
        plugins_file = plugins_dir / "installed_plugins.json"
        plugins_file.write_text("{ invalid json }")

        required = [{"name": "plugin1", "description": "Test plugin"}]
        manager = PluginManager(claude_dir, required)

        status = manager.check_installed()

        assert status == {"plugin1": False}

    def test_get_missing_plugins(self, tmp_path):
        """Test getting list of missing plugins."""
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)

        # Create installed_plugins.json with some plugins
        installed = {
            "plugins": {
                "plugin1": {"version": "1.0.0"},
            }
        }
        plugins_file = plugins_dir / "installed_plugins.json"
        plugins_file.write_text(json.dumps(installed))

        required = [
            {"name": "plugin1", "description": "Plugin 1"},
            {"name": "plugin2", "description": "Plugin 2"},
            {"name": "plugin3", "description": "Plugin 3"},
        ]
        manager = PluginManager(claude_dir, required)

        missing = manager.get_missing_plugins()

        assert len(missing) == 2
        assert missing[0]["name"] in ["plugin2", "plugin3"]
        assert missing[1]["name"] in ["plugin2", "plugin3"]

    def test_get_missing_plugins_all_installed(self, tmp_path):
        """Test getting missing plugins when all are installed."""
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)

        # All plugins installed
        installed = {
            "plugins": {
                "plugin1": {"version": "1.0.0"},
                "plugin2": {"version": "2.0.0"},
            }
        }
        plugins_file = plugins_dir / "installed_plugins.json"
        plugins_file.write_text(json.dumps(installed))

        required = [
            {"name": "plugin1", "description": "Plugin 1"},
            {"name": "plugin2", "description": "Plugin 2"},
        ]
        manager = PluginManager(claude_dir, required)

        missing = manager.get_missing_plugins()

        assert len(missing) == 0

    def test_install_plugin_success(self, tmp_path):
        """Test successful plugin installation."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        required = [{"name": "test-plugin", "description": "Test"}]
        manager = PluginManager(claude_dir, required)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Plugin installed successfully",
                stderr=""
            )

            success, message = manager.install_plugin("test-plugin")

            assert success
            assert "successfully" in message.lower()
            mock_run.assert_called_once()
            assert "claude" in mock_run.call_args[0][0]
            assert "plugin" in mock_run.call_args[0][0]
            assert "install" in mock_run.call_args[0][0]

    def test_install_plugin_failure(self, tmp_path):
        """Test failed plugin installation."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        required = [{"name": "test-plugin", "description": "Test"}]
        manager = PluginManager(claude_dir, required)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: Plugin not found"
            )

            success, message = manager.install_plugin("test-plugin")

            assert not success
            assert "failed" in message.lower() or "error" in message.lower()

    def test_install_plugin_command_not_found(self, tmp_path):
        """Test plugin installation when claude command not found."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        required = [{"name": "test-plugin", "description": "Test"}]
        manager = PluginManager(claude_dir, required)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("claude command not found")

            success, message = manager.install_plugin("test-plugin")

            assert not success
            assert "not found" in message.lower() or "error" in message.lower()

    def test_install_all_missing_plugins(self, tmp_path):
        """Test installing all missing plugins."""
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)

        # One plugin installed, two missing
        installed = {
            "plugins": {
                "plugin1": {"version": "1.0.0"},
            }
        }
        plugins_file = plugins_dir / "installed_plugins.json"
        plugins_file.write_text(json.dumps(installed))

        required = [
            {"name": "plugin1", "description": "Plugin 1"},
            {"name": "plugin2", "description": "Plugin 2"},
            {"name": "plugin3", "description": "Plugin 3"},
        ]
        manager = PluginManager(claude_dir, required)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Plugin installed successfully",
                stderr=""
            )

            results = manager.install_all_missing()

            # Should have tried to install 2 missing plugins
            assert len(results) == 2
            assert "plugin2" in results
            assert "plugin3" in results
            assert all(result[0] for result in results.values())

    def test_install_all_missing_no_plugins_needed(self, tmp_path):
        """Test installing missing plugins when none are missing."""
        claude_dir = tmp_path / ".claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)

        # All plugins installed
        installed = {
            "plugins": {
                "plugin1": {"version": "1.0.0"},
            }
        }
        plugins_file = plugins_dir / "installed_plugins.json"
        plugins_file.write_text(json.dumps(installed))

        required = [
            {"name": "plugin1", "description": "Plugin 1"},
        ]
        manager = PluginManager(claude_dir, required)

        results = manager.install_all_missing()

        # Should not try to install anything
        assert len(results) == 0

    def test_no_required_plugins(self, tmp_path):
        """Test plugin manager with no required plugins."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        required = []
        manager = PluginManager(claude_dir, required)

        status = manager.check_installed()
        missing = manager.get_missing_plugins()
        results = manager.install_all_missing()

        assert status == {}
        assert missing == []
        assert results == {}
