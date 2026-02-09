"""Pytest configuration and fixtures."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    tmp = Path(tempfile.mkdtemp())
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def mock_config_dir(temp_dir):
    """Create a mock config directory structure."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    # Create core files
    core_dir = config_dir / "core"
    core_dir.mkdir()
    (core_dir / "CLAUDE.md").write_text("# Test CLAUDE.md")
    (core_dir / "statusline.sh").write_text("#!/bin/bash\necho test")
    (core_dir / "settings.json").write_text(
        json.dumps(
            {
                "model": "opusplan",
                "statusLine": {"type": "command", "command": "bash {{HOME}}/.claude/statusline.sh"},
                "enabledPlugins": {"test-plugin": True},
                "permissions": {"allow": ["Bash", "Read"]},
            }
        )
    )

    # Create manifest
    manifest = {
        "version": "1.0.0",
        "categories": [
            {
                "name": "core",
                "description": "Core files",
                "target_dir": ".claude",
                "install_type": "merge",
                "files": [
                    {"src": "core/CLAUDE.md", "dest": "CLAUDE.md", "merge": False, "executable": False, "template": False},
                    {
                        "src": "core/settings.json",
                        "dest": "settings.json",
                        "merge": True,
                        "executable": False,
                        "template": True,
                    },
                    {
                        "src": "core/statusline.sh",
                        "dest": "statusline.sh",
                        "merge": False,
                        "executable": True,
                        "template": False,
                    },
                ],
            },
        ],
    }
    (config_dir / "manifest.json").write_text(json.dumps(manifest))

    # Create plugins directory
    plugins_dir = config_dir / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "required.json").write_text(
        json.dumps([{"name": "test-plugin", "description": "Test plugin"}])
    )

    return config_dir


@pytest.fixture
def mock_claude_dir(temp_dir):
    """Create a mock ~/.claude directory."""
    claude_dir = temp_dir / ".claude"
    claude_dir.mkdir()
    return claude_dir


@pytest.fixture
def existing_settings():
    """Return a sample existing settings.json."""
    return {
        "model": "sonnet",
        "permissions": {
            "allow": ["Read", "Write"],
            "deny": ["Bash"],
        },
        "enabledPlugins": {
            "user-plugin": True,
        },
        "feedbackSurveyState": {
            "lastShownTime": 1234567890,
        },
    }
