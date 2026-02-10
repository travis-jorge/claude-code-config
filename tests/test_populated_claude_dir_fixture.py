"""Test the populated_claude_dir fixture to ensure it creates the expected structure."""

import json
from pathlib import Path


def test_populated_claude_dir_core_files(populated_claude_dir):
    """Test that core files are created."""
    assert (populated_claude_dir / "CLAUDE.md").exists()
    assert (populated_claude_dir / "settings.json").exists()
    assert (populated_claude_dir / "statusline.sh").exists()


def test_populated_claude_dir_agent_files(populated_claude_dir):
    """Test that agent files are created."""
    assert (populated_claude_dir / "agents").exists()
    assert (populated_claude_dir / "agents" / "test-agent.md").exists()
    assert (populated_claude_dir / "agents" / "another-agent.md").exists()


def test_populated_claude_dir_rules_files(populated_claude_dir):
    """Test that rules files are created."""
    assert (populated_claude_dir / "rules").exists()
    assert (populated_claude_dir / "rules" / "team-rule.md").exists()


def test_populated_claude_dir_commands(populated_claude_dir):
    """Test that commands are created with nested structure."""
    assert (populated_claude_dir / "commands").exists()
    assert (populated_claude_dir / "commands" / "simple-command.sh").exists()
    assert (populated_claude_dir / "commands" / "nested").exists()
    assert (populated_claude_dir / "commands" / "nested" / "deep-command.py").exists()


def test_populated_claude_dir_plugins(populated_claude_dir):
    """Test that plugins directory and files are created."""
    assert (populated_claude_dir / "plugins").exists()
    assert (populated_claude_dir / "plugins" / "installed_plugins.json").exists()


def test_populated_claude_dir_skip_files(populated_claude_dir):
    """Test that files which should be skipped are present (to test skip logic)."""
    assert (populated_claude_dir / "backups" / "backup-2024-01-01" / "CLAUDE.md").exists()
    assert (populated_claude_dir / "sources" / "cached-source" / "manifest.json").exists()
    assert (populated_claude_dir / ".claude-setup-version.json").exists()
    assert (populated_claude_dir / "sources.json").exists()
    assert (populated_claude_dir / "plans" / "some-plan.md").exists()


def test_populated_claude_dir_executable_bits(populated_claude_dir):
    """Test that shell scripts have executable permissions."""
    statusline = populated_claude_dir / "statusline.sh"
    simple_cmd = populated_claude_dir / "commands" / "simple-command.sh"
    deep_cmd = populated_claude_dir / "commands" / "nested" / "deep-command.py"

    # Check that files are executable (any execute bit set)
    assert statusline.stat().st_mode & 0o111 != 0, "statusline.sh should be executable"
    assert simple_cmd.stat().st_mode & 0o111 != 0, "simple-command.sh should be executable"
    assert deep_cmd.stat().st_mode & 0o111 != 0, "deep-command.py should be executable"


def test_populated_claude_dir_settings_structure(populated_claude_dir):
    """Test that settings.json has all required fields."""
    settings_path = populated_claude_dir / "settings.json"
    settings = json.loads(settings_path.read_text())

    # Core fields
    assert "$schema" in settings
    assert settings["model"] == "opusplan"
    assert "statusLine" in settings
    assert settings["alwaysThinkingEnabled"] is True

    # Permissions with all three subfields
    assert "permissions" in settings
    assert "allow" in settings["permissions"]
    assert "deny" in settings["permissions"]
    assert "ask" in settings["permissions"]

    # Check that lists are not empty
    assert len(settings["permissions"]["allow"]) > 0
    assert len(settings["permissions"]["deny"]) > 0
    assert len(settings["permissions"]["ask"]) > 0

    # Plugins
    assert "enabledPlugins" in settings
    assert len(settings["enabledPlugins"]) > 0

    # Personal field
    assert "feedbackSurveyState" in settings

    # Custom fields (to test preservation)
    assert "customTeamField" in settings
    assert "userCustomField" in settings


def test_populated_claude_dir_settings_statusline_template(populated_claude_dir):
    """Test that statusLine contains {{HOME}} template variable."""
    settings_path = populated_claude_dir / "settings.json"
    settings = json.loads(settings_path.read_text())

    assert "statusLine" in settings
    assert "command" in settings["statusLine"]
    assert "{{HOME}}" in settings["statusLine"]["command"]


def test_populated_claude_dir_plugins_structure(populated_claude_dir):
    """Test that installed_plugins.json has correct structure."""
    plugins_path = populated_claude_dir / "plugins" / "installed_plugins.json"
    plugins = json.loads(plugins_path.read_text())

    # Should have at least 2 plugins
    assert len(plugins) >= 2

    # Check structure of a plugin entry
    assert "test-plugin@author" in plugins
    assert "description" in plugins["test-plugin@author"]
    assert "version" in plugins["test-plugin@author"]


def test_populated_claude_dir_content_samples(populated_claude_dir):
    """Test that files have non-empty, realistic content."""
    # Check CLAUDE.md has markdown headers
    claude_md = (populated_claude_dir / "CLAUDE.md").read_text()
    assert "# Claude Code Instructions" in claude_md
    assert "## Project Overview" in claude_md

    # Check agent files have content
    test_agent = (populated_claude_dir / "agents" / "test-agent.md").read_text()
    assert "# Test Agent" in test_agent
    assert "## Capabilities" in test_agent

    # Check rules have content
    team_rule = (populated_claude_dir / "rules" / "team-rule.md").read_text()
    assert "# Team Rule" in team_rule
    assert "## Guidelines" in team_rule

    # Check commands have shebang lines
    simple_cmd = (populated_claude_dir / "commands" / "simple-command.sh").read_text()
    assert simple_cmd.startswith("#!/bin/bash")

    deep_cmd = (populated_claude_dir / "commands" / "nested" / "deep-command.py").read_text()
    assert deep_cmd.startswith("#!/usr/bin/env python3")
