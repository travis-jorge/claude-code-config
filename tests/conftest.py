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


@pytest.fixture
def populated_claude_dir(temp_dir):
    """Create a realistic populated ~/.claude directory for testing create-config feature.

    Creates a complete directory structure with:
    - Core files (CLAUDE.md, settings.json, statusline.sh)
    - Agent files
    - Rules files
    - Commands (with nested structure)
    - Plugins
    - Files that should be skipped (backups, sources, etc.)
    """
    claude_dir = temp_dir / ".claude"
    claude_dir.mkdir()

    # Core files
    (claude_dir / "CLAUDE.md").write_text(
        "# Claude Code Instructions\n\n"
        "This is a sample CLAUDE.md file with instructions for Claude.\n\n"
        "## Project Overview\n\n"
        "This is a test project.\n"
    )

    # settings.json with all field types
    settings = {
        "$schema": "https://schemas.anthropic.com/claude-code/settings.json",
        "model": "opusplan",
        "statusLine": {
            "type": "command",
            "command": "bash {{HOME}}/.claude/statusline.sh",
        },
        "alwaysThinkingEnabled": True,
        "permissions": {
            "allow": ["Bash", "Read", "Write", "Edit"],
            "deny": ["WebFetch", "WebSearch"],
            "ask": ["Glob", "Grep"],
        },
        "enabledPlugins": {
            "test-plugin@author": True,
            "another-plugin@org": {"enabled": True, "config": {"key": "value"}},
        },
        "feedbackSurveyState": {
            "lastShownTime": 1234567890,
            "dismissed": False,
        },
        "customTeamField": "team-value",
        "userCustomField": "user-value",
    }
    (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2))

    # statusline.sh (executable)
    statusline_path = claude_dir / "statusline.sh"
    statusline_path.write_text(
        "#!/bin/bash\n"
        "# Sample statusline script\n"
        'echo "Project: $(basename $PWD)"\n'
    )
    statusline_path.chmod(0o755)

    # Agent files
    agents_dir = claude_dir / "agents"
    agents_dir.mkdir()

    (agents_dir / "test-agent.md").write_text(
        "# Test Agent\n\n"
        "This is a sample agent definition.\n\n"
        "## Capabilities\n\n"
        "- Task 1\n"
        "- Task 2\n"
    )

    (agents_dir / "another-agent.md").write_text(
        "# Another Agent\n\n"
        "This agent handles different tasks.\n\n"
        "## Usage\n\n"
        "Use this agent for specific workflows.\n"
    )

    # Rules files
    rules_dir = claude_dir / "rules"
    rules_dir.mkdir()

    (rules_dir / "team-rule.md").write_text(
        "# Team Rule\n\n"
        "This is a team-wide rule that all members should follow.\n\n"
        "## Guidelines\n\n"
        "1. Follow convention A\n"
        "2. Follow convention B\n"
    )

    # Commands structure (with nested directories)
    commands_dir = claude_dir / "commands"
    commands_dir.mkdir()

    simple_cmd = commands_dir / "simple-command.sh"
    simple_cmd.write_text(
        "#!/bin/bash\n"
        "# Simple command\n"
        'echo "Running simple command"\n'
    )
    simple_cmd.chmod(0o755)

    nested_dir = commands_dir / "nested"
    nested_dir.mkdir()

    deep_cmd = nested_dir / "deep-command.py"
    deep_cmd.write_text(
        "#!/usr/bin/env python3\n"
        "# Nested command\n"
        'print("Running nested command")\n'
    )
    deep_cmd.chmod(0o755)

    # Plugins
    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir()

    installed_plugins = {
        "test-plugin@author": {
            "description": "A test plugin",
            "version": "1.0.0",
        },
        "another-plugin@org": {
            "description": "Another plugin",
            "version": "2.1.0",
            "config": {"enabled": True},
        },
    }
    (plugins_dir / "installed_plugins.json").write_text(json.dumps(installed_plugins, indent=2))

    # Files that should be skipped
    # Backups directory
    backups_dir = claude_dir / "backups" / "backup-2024-01-01"
    backups_dir.mkdir(parents=True)
    (backups_dir / "CLAUDE.md").write_text("# Old backup")

    # Sources directory
    sources_dir = claude_dir / "sources" / "cached-source"
    sources_dir.mkdir(parents=True)
    (sources_dir / "manifest.json").write_text("{}")

    # Version file (should be skipped)
    (claude_dir / ".claude-setup-version.json").write_text(
        json.dumps({"version": "1.0.0", "timestamp": "2024-01-01T00:00:00"})
    )

    # sources.json (should be skipped)
    (claude_dir / "sources.json").write_text(
        json.dumps({"sources": [{"type": "local", "path": "/some/path"}]})
    )

    # Plans directory (should be skipped)
    plans_dir = claude_dir / "plans"
    plans_dir.mkdir()
    (plans_dir / "some-plan.md").write_text("# Some plan")

    return claude_dir
