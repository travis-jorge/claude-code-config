"""Tests for installer functionality."""

import json
from pathlib import Path

import pytest

from claude_setup.backup import BackupManager
from claude_setup.categories import CategoryRegistry
from claude_setup.installer import Installer, InstallationError
from claude_setup.version import VersionManager


@pytest.fixture
def installer(mock_config_dir, mock_claude_dir):
    """Create installer with mocked dependencies."""
    registry = CategoryRegistry(mock_config_dir)
    backup_mgr = BackupManager(mock_claude_dir)
    version_mgr = VersionManager(mock_claude_dir, mock_config_dir)

    return Installer(mock_config_dir, mock_claude_dir, registry, backup_mgr, version_mgr)


def test_preflight_check_creates_directory(installer, temp_dir):
    """Test that preflight check creates target directory."""
    nonexistent_dir = temp_dir / "new" / "nested" / "dir"
    installer.target_dir = nonexistent_dir

    installer.preflight_check()

    assert nonexistent_dir.exists()
    assert nonexistent_dir.is_dir()


def test_compute_plan_new_install(installer):
    """Test computing plan for new installation."""
    plan = installer.compute_plan(["core"])

    # All files should be new
    assert len(plan["New"]) > 0
    assert len(plan["Updated"]) == 0
    assert len(plan["Unchanged"]) == 0
    assert len(plan["Merge"]) == 1  # settings.json


def test_compute_plan_with_existing_files(installer, mock_claude_dir):
    """Test computing plan with existing files."""
    # Create existing file with same content
    claude_md = mock_claude_dir / "CLAUDE.md"
    claude_md.write_text("# Test CLAUDE.md")

    plan = installer.compute_plan(["core"])

    # CLAUDE.md should be unchanged
    assert any(str(p[0]).endswith("CLAUDE.md") for p in plan["Unchanged"])


def test_compute_plan_with_modified_files(installer, mock_claude_dir):
    """Test computing plan with modified files."""
    # Create existing file with different content
    claude_md = mock_claude_dir / "CLAUDE.md"
    claude_md.write_text("# Different content")

    plan = installer.compute_plan(["core"])

    # CLAUDE.md should be updated
    assert any(str(p[0]).endswith("CLAUDE.md") for p in plan["Updated"])


def test_dry_run_makes_no_changes(installer, mock_claude_dir):
    """Test that dry run doesn't modify files."""
    result = installer.install(["core"], dry_run=True)

    assert result["dry_run"] is True
    assert "plan" in result

    # Check that no files were created
    assert not (mock_claude_dir / "CLAUDE.md").exists()
    assert not (mock_claude_dir / "statusline.sh").exists()


def test_install_creates_files(installer, mock_claude_dir):
    """Test that install creates files."""
    result = installer.install(["core"], dry_run=False)

    assert result["stats"]["installed"] > 0

    # Check that files were created
    assert (mock_claude_dir / "CLAUDE.md").exists()
    assert (mock_claude_dir / "statusline.sh").exists()
    assert (mock_claude_dir / "settings.json").exists()


def test_install_sets_executable_flag(installer, mock_claude_dir):
    """Test that executable files get correct permissions."""
    installer.install(["core"], dry_run=False)

    statusline = mock_claude_dir / "statusline.sh"
    assert statusline.exists()

    # Check that file is executable
    import stat

    st = statusline.stat()
    assert st.st_mode & stat.S_IXUSR


def test_install_creates_backup(installer, mock_claude_dir):
    """Test that install creates backup of existing files."""
    # Create existing file
    settings_file = mock_claude_dir / "settings.json"
    settings_file.write_text(json.dumps({"model": "sonnet"}))

    result = installer.install(["core"], dry_run=False)

    assert result["backup_path"] is not None

    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    assert backup_path.name.startswith("claude-setup-")


def test_install_writes_version_stamp(installer, mock_claude_dir):
    """Test that install writes version stamp."""
    installer.install(["core"], dry_run=False)

    stamp_path = mock_claude_dir / ".claude-setup-version.json"
    assert stamp_path.exists()

    with open(stamp_path) as f:
        stamp = json.load(f)

    assert "tool_version" in stamp
    assert "config_hash" in stamp
    assert "installed_at" in stamp
    assert "categories" in stamp
    assert "core" in stamp["categories"]


def test_install_nonexistent_category(installer):
    """Test error when installing nonexistent category."""
    result = installer.install(["nonexistent"], dry_run=False)

    # Should complete but with zero files
    assert result["stats"]["installed"] == 0


def test_template_resolution(installer, mock_claude_dir):
    """Test that template variables are resolved."""
    installer.install(["core"], dry_run=False)

    settings_file = mock_claude_dir / "settings.json"
    assert settings_file.exists()

    with open(settings_file) as f:
        settings = json.load(f)

    # {{HOME}} should be resolved to the test directory parent
    command = settings["statusLine"]["command"]
    assert "{{HOME}}" not in command
    # In tests, home is the parent of mock_claude_dir (which is .claude)
    expected_home = str(mock_claude_dir.parent)
    assert expected_home in command


def test_settings_merge(installer, mock_claude_dir):
    """Test that settings.json is merged, not overwritten."""
    # Create existing settings with user customizations
    settings_file = mock_claude_dir / "settings.json"
    existing = {
        "model": "sonnet",
        "permissions": {"allow": ["Write"], "deny": ["Edit"]},
        "feedbackSurveyState": {"lastShownTime": 1234567890},
    }
    settings_file.write_text(json.dumps(existing))

    installer.install(["core"], dry_run=False)

    with open(settings_file) as f:
        merged = json.load(f)

    # Team settings should override
    assert merged["model"] == "opusplan"

    # User deny should be preserved
    assert merged["permissions"]["deny"] == ["Edit"]

    # Permissions should be union
    assert "Bash" in merged["permissions"]["allow"]
    assert "Read" in merged["permissions"]["allow"]
    assert "Write" in merged["permissions"]["allow"]

    # User-specific should be preserved
    assert merged["feedbackSurveyState"] == {"lastShownTime": 1234567890}
