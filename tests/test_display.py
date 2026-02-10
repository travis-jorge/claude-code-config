"""Tests for display module visualization functions."""

from pathlib import Path

import pytest

from claude_setup.create_config import ScannedFile, ScannedSettings, ScanResult
from claude_setup.display import show_config_preview, show_scan_results


def test_show_scan_results_with_all_categories():
    """Test scan results display with files in all categories."""
    files = [
        ScannedFile(Path("/home/.claude/CLAUDE.md"), "CLAUDE.md", "core", 2400, False),
        ScannedFile(Path("/home/.claude/settings.json"), "settings.json", "core", 800, False),
        ScannedFile(Path("/home/.claude/agents/test.md"), "agents/test.md", "agents", 1200, False),
        ScannedFile(Path("/home/.claude/rules/team.md"), "rules/team.md", "rules", 900, False),
        ScannedFile(Path("/home/.claude/commands/simple.sh"), "commands/simple.sh", "commands", 400, True),
    ]

    settings = ScannedSettings(
        raw={"model": "claude-3", "statusLine": "~/status.sh"},
        team_fields={"model": "claude-3", "statusLine": "~/status.sh"},
        personal_fields={"feedbackSurveyState": "dismissed"},
        home_dir="/home/user",
    )

    plugins = [
        {"name": "plugin1", "description": "First plugin"},
        {"name": "plugin2", "description": "Second plugin"},
    ]

    scan_result = ScanResult(files, settings, plugins, Path("/home/.claude"))

    # Should not raise - just check it runs
    show_scan_results(scan_result)


def test_show_scan_results_empty():
    """Test scan results display with no files."""
    scan_result = ScanResult([], None, [], Path("/home/.claude"))

    # Should handle empty gracefully
    show_scan_results(scan_result)


def test_show_scan_results_without_settings():
    """Test scan results display when settings.json is missing."""
    files = [
        ScannedFile(Path("/home/.claude/CLAUDE.md"), "CLAUDE.md", "core", 2400, False),
    ]

    scan_result = ScanResult(files, None, [], Path("/home/.claude"))

    # Should handle missing settings gracefully
    show_scan_results(scan_result)


def test_show_scan_results_without_plugins():
    """Test scan results display when no plugins are installed."""
    files = [
        ScannedFile(Path("/home/.claude/CLAUDE.md"), "CLAUDE.md", "core", 2400, False),
    ]

    settings = ScannedSettings(
        raw={"model": "claude-3"},
        team_fields={"model": "claude-3"},
        personal_fields={},
        home_dir="/home/user",
    )

    scan_result = ScanResult(files, settings, [], Path("/home/.claude"))

    # Should handle missing plugins gracefully
    show_scan_results(scan_result)


def test_show_config_preview_full():
    """Test config preview display with all features enabled."""
    preview = {
        "category_counts": {"core": 3, "agents": 2, "rules": 1, "commands": 2},
        "file_lists": {
            "core": ["CLAUDE.md", "settings.json", "statusline.sh"],
            "agents": ["agents/test.md", "agents/debug.md"],
            "rules": ["rules/team.md"],
            "commands": ["commands/simple.sh", "commands/nested/deep.py"],
        },
        "output_path": "/Users/user/my-config",
        "has_settings": True,
        "has_plugins": True,
        "plugin_count": 3,
        "will_init_git": True,
    }

    # Should not raise - just check it runs
    show_config_preview(preview)


def test_show_config_preview_minimal():
    """Test config preview display with minimal configuration."""
    preview = {
        "category_counts": {"core": 1},
        "file_lists": {
            "core": ["CLAUDE.md"],
        },
        "output_path": "/Users/user/minimal-config",
        "has_settings": False,
        "has_plugins": False,
        "plugin_count": 0,
        "will_init_git": False,
    }

    # Should handle minimal config gracefully
    show_config_preview(preview)


def test_show_config_preview_nested_commands():
    """Test config preview display with deeply nested command structure."""
    preview = {
        "category_counts": {"commands": 4},
        "file_lists": {
            "commands": [
                "commands/top.sh",
                "commands/level1/mid.py",
                "commands/level1/level2/deep.sh",
                "commands/level1/level2/level3/deeper.py",
            ],
        },
        "output_path": "/Users/user/nested-config",
        "has_settings": False,
        "has_plugins": False,
        "plugin_count": 0,
        "will_init_git": False,
    }

    # Should handle deeply nested structure
    show_config_preview(preview)


def test_show_config_preview_no_plugins():
    """Test config preview when has_plugins is True but plugin_count is 0."""
    preview = {
        "category_counts": {"core": 1},
        "file_lists": {
            "core": ["CLAUDE.md"],
        },
        "output_path": "/Users/user/config",
        "has_settings": False,
        "has_plugins": True,
        "plugin_count": 0,  # Edge case: has_plugins True but count is 0
        "will_init_git": False,
    }

    # Should handle inconsistent plugin state gracefully
    show_config_preview(preview)


def test_show_config_preview_only_one_category():
    """Test config preview with only one category."""
    preview = {
        "category_counts": {"agents": 5},
        "file_lists": {
            "agents": [
                "agents/test-agent.md",
                "agents/debug-agent.md",
                "agents/code-agent.md",
                "agents/review-agent.md",
                "agents/deploy-agent.md",
            ],
        },
        "output_path": "/Users/user/agents-only",
        "has_settings": False,
        "has_plugins": False,
        "plugin_count": 0,
        "will_init_git": True,
    }

    # Should handle single category gracefully
    show_config_preview(preview)


def test_format_size_bytes():
    """Test file size formatting helper."""
    from claude_setup.display import _format_size

    assert _format_size(0) == "0 B"
    assert _format_size(500) == "500 B"
    assert _format_size(1023) == "1023 B"
    assert _format_size(1024) == "1.0 KB"
    assert _format_size(1536) == "1.5 KB"
    assert _format_size(1024 * 1024) == "1.0 MB"
    assert _format_size(int(2.5 * 1024 * 1024)) == "2.5 MB"


def test_build_tree_structure():
    """Test tree structure building helper."""
    from claude_setup.display import _build_tree_structure

    file_paths = [
        "commands/top.sh",
        "commands/level1/mid.py",
        "commands/level1/level2/deep.sh",
    ]

    tree = _build_tree_structure(file_paths, "commands")

    # Check structure
    assert "__files__" in tree
    assert "top.sh" in tree["__files__"]
    assert "level1" in tree
    assert "__files__" in tree["level1"]
    assert "mid.py" in tree["level1"]["__files__"]
    assert "level2" in tree["level1"]
    assert "__files__" in tree["level1"]["level2"]
    assert "deep.sh" in tree["level1"]["level2"]["__files__"]


def test_build_tree_structure_flat():
    """Test tree structure with flat file list."""
    from claude_setup.display import _build_tree_structure

    file_paths = [
        "commands/file1.sh",
        "commands/file2.py",
        "commands/file3.sh",
    ]

    tree = _build_tree_structure(file_paths, "commands")

    # All files should be at root level
    assert "__files__" in tree
    assert len(tree["__files__"]) == 3
    assert "file1.sh" in tree["__files__"]
    assert "file2.py" in tree["__files__"]
    assert "file3.sh" in tree["__files__"]


def test_format_tree_lines_simple():
    """Test tree line formatting with simple structure."""
    from claude_setup.display import _format_tree_lines

    tree = {
        "__files__": ["file1.sh", "file2.py"],
    }

    lines = _format_tree_lines(tree, "    ", False)

    # Should have two lines with proper prefixes
    assert len(lines) == 2
    assert "├──" in lines[0] or "└──" in lines[0]
    assert "file1.sh" in lines[0] or "file1.sh" in lines[1]
    assert "file2.py" in lines[0] or "file2.py" in lines[1]


def test_format_tree_lines_nested():
    """Test tree line formatting with nested structure."""
    from claude_setup.display import _format_tree_lines

    tree = {
        "subdir": {
            "__files__": ["nested.sh"],
        },
        "__files__": ["top.py"],
    }

    lines = _format_tree_lines(tree, "    ", False)

    # Should have lines for directory, nested file, and top file
    assert len(lines) >= 3
    assert any("subdir/" in line for line in lines)
    assert any("nested.sh" in line for line in lines)
    assert any("top.py" in line for line in lines)
