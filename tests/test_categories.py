"""Tests for category registry."""

import json
from pathlib import Path

import pytest

from claude_setup.categories import CategoryRegistry, Category, FileEntry


def test_load_manifest(mock_config_dir):
    """Test loading manifest from config directory."""
    registry = CategoryRegistry(mock_config_dir)

    assert len(registry.categories) > 0
    assert "core" in registry.categories


def test_get_category(mock_config_dir):
    """Test getting a specific category."""
    registry = CategoryRegistry(mock_config_dir)

    core = registry.get("core")
    assert core is not None
    assert core.name == "core"
    assert core.description == "Core files"
    assert len(core.files) > 0


def test_get_nonexistent_category(mock_config_dir):
    """Test getting nonexistent category returns None."""
    registry = CategoryRegistry(mock_config_dir)

    result = registry.get("nonexistent")
    assert result is None


def test_get_all_categories(mock_config_dir):
    """Test getting all categories."""
    registry = CategoryRegistry(mock_config_dir)

    all_cats = registry.get_all()
    assert len(all_cats) > 0
    assert all(isinstance(cat, Category) for cat in all_cats)


def test_get_file_count(mock_config_dir):
    """Test getting file count for a category."""
    registry = CategoryRegistry(mock_config_dir)

    count = registry.get_file_count("core")
    assert count == 3  # CLAUDE.md, settings.json, statusline.sh


def test_get_by_names(mock_config_dir):
    """Test getting multiple categories by name."""
    registry = CategoryRegistry(mock_config_dir)

    categories = registry.get_by_names(["core"])
    assert len(categories) == 1
    assert categories[0].name == "core"


def test_discover_files(mock_config_dir, temp_dir):
    """Test file discovery for recursive directories."""
    # Create a commands directory with nested structure
    commands_dir = mock_config_dir / "commands"
    commands_dir.mkdir()
    (commands_dir / "cmd1.md").write_text("command 1")
    (commands_dir / "cmd2.sh").write_text("#!/bin/bash")

    subdir = commands_dir / "subdir"
    subdir.mkdir()
    (subdir / "nested.md").write_text("nested command")

    # Update manifest to include commands category
    manifest_path = mock_config_dir / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    manifest["categories"].append(
        {
            "name": "commands",
            "description": "Commands",
            "target_dir": ".claude/commands",
            "install_type": "discover",
            "files": [],
        }
    )

    with open(manifest_path, "w") as f:
        json.dump(manifest, f)

    # Create new registry to load updated manifest
    registry = CategoryRegistry(mock_config_dir)

    commands_cat = registry.get("commands")
    assert commands_cat is not None
    assert len(commands_cat.files) == 3

    # Check that .sh files are marked executable
    sh_files = [f for f in commands_cat.files if f.src.endswith(".sh")]
    assert len(sh_files) == 1
    assert sh_files[0].executable is True

    # Check nested file is included
    nested_files = [f for f in commands_cat.files if "subdir" in f.src]
    assert len(nested_files) == 1


def test_file_entry_attributes():
    """Test FileEntry dataclass attributes."""
    entry = FileEntry(
        src="test.md",
        dest="test.md",
        merge=False,
        executable=False,
        template=False,
    )

    assert entry.src == "test.md"
    assert entry.dest == "test.md"
    assert entry.merge is False
    assert entry.executable is False
    assert entry.template is False


def test_category_attributes():
    """Test Category dataclass attributes."""
    files = [FileEntry("src.md", "dest.md")]
    category = Category(
        name="test",
        description="Test category",
        target_dir=".claude",
        install_type="overwrite",
        files=files,
    )

    assert category.name == "test"
    assert category.description == "Test category"
    assert category.target_dir == ".claude"
    assert category.install_type == "overwrite"
    assert len(category.files) == 1
