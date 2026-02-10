"""Tests for create_config functionality."""

import json
import subprocess
from pathlib import Path

import pytest

from claude_setup.categories import CategoryRegistry
from claude_setup.create_config import (
    ConfigPlan,
    ScannedFile,
    apply_reverse_templates,
    filter_settings_for_team,
    generate_config_repo,
    generate_manifest,
    preview_config_plan,
    scan_claude_dir,
    scan_plugins,
    scan_settings,
)


# Scanner Tests


def test_scan_claude_dir_populated(populated_claude_dir):
    """Test scanning a populated ~/.claude directory."""
    result = scan_claude_dir(populated_claude_dir)

    # Count files by category
    core_files = [f for f in result.files if f.category == "core"]
    agent_files = [f for f in result.files if f.category == "agents"]
    rule_files = [f for f in result.files if f.category == "rules"]
    command_files = [f for f in result.files if f.category == "commands"]

    # Core files: CLAUDE.md, settings.json, statusline.sh
    assert len(core_files) == 3
    assert any(f.relative_path == "CLAUDE.md" for f in core_files)
    assert any(f.relative_path == "settings.json" for f in core_files)
    assert any(f.relative_path == "statusline.sh" for f in core_files)

    # Agent files: 2 agent definitions
    assert len(agent_files) == 2
    assert any("test-agent.md" in f.relative_path for f in agent_files)
    assert any("another-agent.md" in f.relative_path for f in agent_files)

    # Rule files: 1 rule
    assert len(rule_files) == 1
    assert any("team-rule.md" in f.relative_path for f in rule_files)

    # Command files: 2 commands (1 top-level, 1 nested)
    assert len(command_files) == 2
    assert any("simple-command.sh" in f.relative_path for f in command_files)
    assert any("nested/deep-command.py" in f.relative_path for f in command_files)

    # Check executable detection
    statusline = next(f for f in core_files if f.relative_path == "statusline.sh")
    assert statusline.is_executable

    simple_cmd = next(f for f in command_files if "simple-command.sh" in f.relative_path)
    assert simple_cmd.is_executable

    # Settings should be scanned
    assert result.settings is not None

    # Plugins should be scanned
    assert len(result.plugins) == 2

    # Verify skipped directories are not included
    # No files from backups/, sources/, plans/ should be present
    for file in result.files:
        assert "backups" not in file.relative_path
        assert "sources" not in file.relative_path
        assert "plans" not in file.relative_path
        assert ".claude-setup-version.json" not in file.relative_path
        assert "sources.json" not in file.relative_path


def test_scan_claude_dir_empty(temp_dir):
    """Test scanning an empty ~/.claude directory."""
    empty_dir = temp_dir / ".claude"
    empty_dir.mkdir()

    result = scan_claude_dir(empty_dir)

    assert len(result.files) == 0
    assert result.settings is None
    assert len(result.plugins) == 0
    assert result.claude_dir == empty_dir


def test_scan_claude_dir_missing(temp_dir):
    """Test scanning a non-existent directory."""
    missing_dir = temp_dir / "nonexistent"

    result = scan_claude_dir(missing_dir)

    # Should return empty result without crashing
    assert len(result.files) == 0
    assert result.settings is None
    assert len(result.plugins) == 0


def test_scan_settings_classification(populated_claude_dir):
    """Test settings field classification into team vs personal."""
    settings = scan_settings(populated_claude_dir)

    assert settings is not None

    # Team fields should include
    assert "$schema" in settings.team_fields
    assert "model" in settings.team_fields
    assert "statusLine" in settings.team_fields
    assert "alwaysThinkingEnabled" in settings.team_fields
    assert "permissions" in settings.team_fields
    assert "allow" in settings.team_fields["permissions"]
    assert "enabledPlugins" in settings.team_fields

    # Personal fields should include
    assert "permissions" in settings.personal_fields
    assert "deny" in settings.personal_fields["permissions"]
    assert "ask" in settings.personal_fields["permissions"]
    assert "feedbackSurveyState" in settings.personal_fields

    # Unknown custom fields should be personal
    assert "customTeamField" in settings.personal_fields
    assert "userCustomField" in settings.personal_fields

    # Home dir should be captured
    assert settings.home_dir == str(Path.home())


def test_scan_plugins(populated_claude_dir):
    """Test plugin scanning and conversion."""
    plugins = scan_plugins(populated_claude_dir)

    assert len(plugins) == 2
    assert all(isinstance(p, dict) for p in plugins)
    assert all("name" in p and "description" in p for p in plugins)

    plugin_names = [p["name"] for p in plugins]
    assert "test-plugin@author" in plugin_names
    assert "another-plugin@org" in plugin_names


def test_scan_plugins_missing(temp_dir):
    """Test plugin scanning when installed_plugins.json is missing."""
    empty_dir = temp_dir / ".claude"
    empty_dir.mkdir()

    plugins = scan_plugins(empty_dir)

    assert len(plugins) == 0


def test_scan_nested_commands(populated_claude_dir):
    """Test that nested commands are found with correct relative paths."""
    result = scan_claude_dir(populated_claude_dir)

    command_files = [f for f in result.files if f.category == "commands"]

    # Check nested command path is preserved
    nested_cmd = next(f for f in command_files if "deep-command.py" in f.relative_path)
    assert nested_cmd.relative_path == "commands/nested/deep-command.py"


# Filter Tests


def test_filter_settings_default(populated_claude_dir):
    """Test filtering settings with default behavior (no overrides)."""
    scanned_settings = scan_settings(populated_claude_dir)
    filtered = filter_settings_for_team(scanned_settings)

    # Only team fields should be present
    assert "$schema" in filtered
    assert "model" in filtered
    assert "statusLine" in filtered
    assert "alwaysThinkingEnabled" in filtered
    assert "permissions" in filtered
    assert "allow" in filtered["permissions"]
    assert "enabledPlugins" in filtered

    # Personal fields should not be present
    assert "deny" not in filtered.get("permissions", {})
    assert "ask" not in filtered.get("permissions", {})
    assert "feedbackSurveyState" not in filtered
    assert "customTeamField" not in filtered
    assert "userCustomField" not in filtered

    # Template substitution should have occurred
    # statusLine command should have {{HOME}} instead of actual home path
    if "statusLine" in filtered and "command" in filtered["statusLine"]:
        assert "{{HOME}}" in filtered["statusLine"]["command"]
        assert str(Path.home()) not in filtered["statusLine"]["command"]


def test_filter_settings_custom_allow(populated_claude_dir):
    """Test filtering with custom permissions.allow override."""
    scanned_settings = scan_settings(populated_claude_dir)
    custom_allow = ["Read", "Write", "CustomTool"]

    filtered = filter_settings_for_team(scanned_settings, custom_allow=custom_allow)

    assert "permissions" in filtered
    assert filtered["permissions"]["allow"] == custom_allow


def test_filter_settings_custom_plugins(populated_claude_dir):
    """Test filtering with custom enabledPlugins override."""
    scanned_settings = scan_settings(populated_claude_dir)
    custom_plugins = {
        "custom-plugin@author": True,
        "another-custom@org": {"enabled": True},
    }

    filtered = filter_settings_for_team(scanned_settings, custom_plugins=custom_plugins)

    assert "enabledPlugins" in filtered
    assert filtered["enabledPlugins"] == custom_plugins


def test_apply_reverse_templates():
    """Test reverse template substitution (home path -> {{HOME}})."""
    home_dir = str(Path.home())
    data = {
        "statusLine": {
            "type": "command",
            "command": f"bash {home_dir}/.claude/statusline.sh",
        },
        "customPath": f"{home_dir}/some/path",
        "nestedPaths": {
            "path1": f"{home_dir}/nested/path",
            "path2": f"{home_dir}/another",
        },
    }

    result = apply_reverse_templates(data, home_dir)

    # All home directory references should be replaced
    assert "{{HOME}}" in result["statusLine"]["command"]
    assert home_dir not in result["statusLine"]["command"]
    assert result["customPath"] == "{{HOME}}/some/path"
    assert result["nestedPaths"]["path1"] == "{{HOME}}/nested/path"
    assert result["nestedPaths"]["path2"] == "{{HOME}}/another"


# Generator Tests


def test_generate_manifest(populated_claude_dir):
    """Test manifest generation with correct structure."""
    result = scan_claude_dir(populated_claude_dir)

    manifest = generate_manifest(
        output_dir=populated_claude_dir / "output",
        selected_files=result.files,
        has_settings=True,
        has_plugins=True,
    )

    # Check version
    assert manifest["version"] == "1.0.0"

    # Check all categories are present
    categories = {cat["name"]: cat for cat in manifest["categories"]}
    assert set(categories.keys()) == {"core", "agents", "rules", "commands", "plugins"}

    # Core category checks
    core = categories["core"]
    assert core["install_type"] == "merge"
    assert core["target_dir"] == ".claude"
    assert len(core["files"]) > 0

    # Check settings.json has correct flags
    settings_file = next(f for f in core["files"] if f["dest"] == "settings.json")
    assert settings_file["merge"] is True
    assert settings_file["template"] is True

    # Check statusline.sh has correct flags
    statusline_file = next(f for f in core["files"] if f["dest"] == "statusline.sh")
    assert statusline_file["executable"] is True
    assert statusline_file["template"] is True

    # Check CLAUDE.md has correct flags
    claude_md_file = next(f for f in core["files"] if f["dest"] == "CLAUDE.md")
    assert claude_md_file["template"] is True

    # Agents category
    agents = categories["agents"]
    assert agents["install_type"] == "overwrite"
    assert agents["target_dir"] == ".claude/agents"
    assert len(agents["files"]) == 2

    # Rules category
    rules = categories["rules"]
    assert rules["install_type"] == "overwrite"
    assert rules["target_dir"] == ".claude/rules"
    assert len(rules["files"]) == 1

    # Commands category (discover mode)
    commands = categories["commands"]
    assert commands["install_type"] == "discover"
    assert commands["target_dir"] == ".claude/commands"
    assert len(commands["files"]) == 0  # Empty for discover mode

    # Plugins category (check mode)
    plugins = categories["plugins"]
    assert plugins["install_type"] == "check"
    assert plugins["target_dir"] == ".claude/plugins"
    assert len(plugins["files"]) == 0  # Empty for check mode


def test_generate_config_repo_new_dir(populated_claude_dir, temp_dir):
    """Test generating config repo to a new directory."""
    result = scan_claude_dir(populated_claude_dir)
    scanned_settings = scan_settings(populated_claude_dir)
    filtered_settings = filter_settings_for_team(scanned_settings)

    output_dir = temp_dir / "new-config"
    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=result.files,
        settings=filtered_settings,
        plugins=result.plugins,
        init_git=False,
        config_name="test-config",
    )

    generated_dir = generate_config_repo(plan, force=False)

    # Check directory structure was created
    assert generated_dir.exists()
    assert (generated_dir / "core").exists()
    assert (generated_dir / "agents").exists()
    assert (generated_dir / "rules").exists()
    assert (generated_dir / "commands").exists()
    assert (generated_dir / "plugins").exists()

    # Check files were copied
    assert (generated_dir / "core" / "CLAUDE.md").exists()
    assert (generated_dir / "core" / "statusline.sh").exists()
    assert (generated_dir / "agents" / "test-agent.md").exists()
    assert (generated_dir / "agents" / "another-agent.md").exists()
    assert (generated_dir / "rules" / "team-rule.md").exists()

    # Check nested commands are preserved
    assert (generated_dir / "commands" / "simple-command.sh").exists()
    assert (generated_dir / "commands" / "nested" / "deep-command.py").exists()

    # Check settings.json was written (filtered version)
    settings_path = generated_dir / "core" / "settings.json"
    assert settings_path.exists()
    with open(settings_path) as f:
        settings = json.load(f)
    # Should only have team fields
    assert "model" in settings
    assert "feedbackSurveyState" not in settings

    # Check plugins/required.json was written
    plugins_path = generated_dir / "plugins" / "required.json"
    assert plugins_path.exists()
    with open(plugins_path) as f:
        plugins_data = json.load(f)
    assert "plugins" in plugins_data
    assert len(plugins_data["plugins"]) == 2

    # Check manifest.json was written
    manifest_path = generated_dir / "manifest.json"
    assert manifest_path.exists()
    with open(manifest_path) as f:
        manifest = json.load(f)
    assert "version" in manifest
    assert "categories" in manifest

    # Check executable bits are preserved
    statusline = generated_dir / "core" / "statusline.sh"
    assert statusline.stat().st_mode & 0o111

    simple_cmd = generated_dir / "commands" / "simple-command.sh"
    assert simple_cmd.stat().st_mode & 0o111

    # Check git init was NOT run (init_git=False)
    assert not (generated_dir / ".git").exists()


def test_generate_config_repo_existing_empty(populated_claude_dir, temp_dir):
    """Test generating to existing empty directory."""
    result = scan_claude_dir(populated_claude_dir)
    scanned_settings = scan_settings(populated_claude_dir)
    filtered_settings = filter_settings_for_team(scanned_settings)

    output_dir = temp_dir / "existing-empty"
    output_dir.mkdir()

    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=result.files,
        settings=filtered_settings,
        plugins=result.plugins,
        init_git=False,
        config_name="test-config",
    )

    # Should succeed without force flag for empty dir
    generated_dir = generate_config_repo(plan, force=False)
    assert generated_dir.exists()
    assert (generated_dir / "manifest.json").exists()


def test_generate_config_repo_existing_non_empty_no_force(populated_claude_dir, temp_dir):
    """Test generating to non-empty directory without force flag."""
    result = scan_claude_dir(populated_claude_dir)
    scanned_settings = scan_settings(populated_claude_dir)
    filtered_settings = filter_settings_for_team(scanned_settings)

    output_dir = temp_dir / "existing-non-empty"
    output_dir.mkdir()
    (output_dir / "existing-file.txt").write_text("existing content")

    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=result.files,
        settings=filtered_settings,
        plugins=result.plugins,
        init_git=False,
        config_name="test-config",
    )

    # Should raise FileExistsError
    with pytest.raises(FileExistsError, match="already exists and is not empty"):
        generate_config_repo(plan, force=False)


def test_generate_config_repo_existing_non_empty_with_force(populated_claude_dir, temp_dir):
    """Test generating to non-empty directory with force=True."""
    result = scan_claude_dir(populated_claude_dir)
    scanned_settings = scan_settings(populated_claude_dir)
    filtered_settings = filter_settings_for_team(scanned_settings)

    output_dir = temp_dir / "existing-force"
    output_dir.mkdir()
    existing_file = output_dir / "existing-file.txt"
    existing_file.write_text("existing content")

    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=result.files,
        settings=filtered_settings,
        plugins=result.plugins,
        init_git=False,
        config_name="test-config",
    )

    # Should succeed with force=True
    generated_dir = generate_config_repo(plan, force=True)

    assert generated_dir.exists()
    assert (generated_dir / "manifest.json").exists()

    # Existing file should be removed
    assert not existing_file.exists()


def test_generate_config_repo_with_git_init(populated_claude_dir, temp_dir):
    """Test generating config repo with git initialization."""
    result = scan_claude_dir(populated_claude_dir)
    scanned_settings = scan_settings(populated_claude_dir)
    filtered_settings = filter_settings_for_team(scanned_settings)

    output_dir = temp_dir / "config-with-git"
    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=result.files,
        settings=filtered_settings,
        plugins=result.plugins,
        init_git=True,
        config_name="test-config",
    )

    generated_dir = generate_config_repo(plan, force=False)

    # Check git was initialized
    assert (generated_dir / ".git").exists()
    assert (generated_dir / ".git").is_dir()


def test_preview_config_plan(populated_claude_dir):
    """Test preview generation shows correct summary."""
    result = scan_claude_dir(populated_claude_dir)
    scanned_settings = scan_settings(populated_claude_dir)
    filtered_settings = filter_settings_for_team(scanned_settings)

    output_dir = Path("/tmp/preview-test")
    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=result.files,
        settings=filtered_settings,
        plugins=result.plugins,
        init_git=True,
        config_name="preview-config",
    )

    preview = preview_config_plan(plan)

    # Check structure
    assert "category_counts" in preview
    assert "file_lists" in preview
    assert "output_path" in preview
    assert "has_settings" in preview
    assert "has_plugins" in preview
    assert "will_init_git" in preview

    # Check counts
    counts = preview["category_counts"]
    assert counts["core"] >= 3  # CLAUDE.md, settings.json, statusline.sh
    assert counts["agents"] == 2
    assert counts["rules"] == 1
    assert counts["commands"] == 2

    # Check file lists
    file_lists = preview["file_lists"]
    assert "CLAUDE.md" in file_lists["core"]
    assert "settings.json" in file_lists["core"]
    assert "statusline.sh" in file_lists["core"]

    # Check boolean flags
    assert preview["has_settings"] is True
    assert preview["has_plugins"] is True
    assert preview["will_init_git"] is True
    assert preview["output_path"] == str(output_dir)


# Integration Test


def test_full_roundtrip(populated_claude_dir, temp_dir):
    """Test complete workflow from scan to generation to validation."""
    # Step 1: Scan populated directory
    scan_result = scan_claude_dir(populated_claude_dir)
    assert len(scan_result.files) > 0

    # Step 2: Filter settings
    scanned_settings = scan_settings(populated_claude_dir)
    filtered_settings = filter_settings_for_team(scanned_settings)
    assert "model" in filtered_settings
    assert "feedbackSurveyState" not in filtered_settings

    # Step 3: Generate config repo
    output_dir = temp_dir / "roundtrip-config"
    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=scan_result.files,
        settings=filtered_settings,
        plugins=scan_result.plugins,
        init_git=False,
        config_name="roundtrip-test",
    )

    generated_dir = generate_config_repo(plan, force=False)
    assert generated_dir.exists()

    # Step 4: Load the generated manifest with CategoryRegistry
    manifest_path = generated_dir / "manifest.json"
    assert manifest_path.exists()

    registry = CategoryRegistry(generated_dir)
    categories = registry.categories

    # Verify manifest is valid and loadable
    assert len(categories) == 5
    category_names = set(categories.keys())
    assert category_names == {"core", "agents", "rules", "commands", "plugins"}

    # Step 5: Verify settings.json is valid
    settings_path = generated_dir / "core" / "settings.json"
    with open(settings_path) as f:
        settings = json.load(f)

    # Should have valid JSON structure
    assert isinstance(settings, dict)
    assert "model" in settings
    assert "statusLine" in settings

    # Should have template variables
    if "statusLine" in settings and "command" in settings["statusLine"]:
        assert "{{HOME}}" in settings["statusLine"]["command"]

    # Step 6: Verify plugins/required.json has correct structure
    plugins_path = generated_dir / "plugins" / "required.json"
    with open(plugins_path) as f:
        plugins_data = json.load(f)

    assert "plugins" in plugins_data
    assert isinstance(plugins_data["plugins"], list)
    assert all("name" in p for p in plugins_data["plugins"])
