"""Tests for settings merge logic."""

import json
from pathlib import Path

import pytest

from claude_setup.merge import merge_settings, resolve_templates, load_settings, save_settings


def test_merge_fresh_install():
    """Test merge with no existing settings."""
    source = {
        "model": "opusplan",
        "permissions": {"allow": ["Bash", "Read"]},
        "enabledPlugins": {"plugin1": True},
    }
    target = {}

    result = merge_settings(source, target)

    assert result["model"] == "opusplan"
    assert set(result["permissions"]["allow"]) == {"Bash", "Read"}
    assert result["enabledPlugins"] == {"plugin1": True}


def test_merge_with_existing():
    """Test merge with existing settings."""
    source = {
        "model": "opusplan",
        "permissions": {"allow": ["Bash", "Read"]},
        "enabledPlugins": {"team-plugin": True},
        "alwaysThinkingEnabled": True,
    }
    target = {
        "model": "sonnet",
        "permissions": {
            "allow": ["Write"],
            "deny": ["Edit"],
        },
        "enabledPlugins": {"user-plugin": True},
        "feedbackSurveyState": {"lastShownTime": 1234567890},
    }

    result = merge_settings(source, target)

    # Team settings override
    assert result["model"] == "opusplan"
    assert result["alwaysThinkingEnabled"] is True

    # Permissions union on allow
    assert set(result["permissions"]["allow"]) == {"Bash", "Read", "Write"}

    # User deny preserved
    assert result["permissions"]["deny"] == ["Edit"]

    # Plugins union (team plugin overwrites)
    assert result["enabledPlugins"]["team-plugin"] is True
    assert result["enabledPlugins"]["user-plugin"] is True

    # User-specific preserved
    assert result["feedbackSurveyState"] == {"lastShownTime": 1234567890}


def test_merge_unknown_keys():
    """Test that unknown keys are preserved."""
    source = {"model": "opusplan"}
    target = {"customKey": "customValue", "nested": {"key": "value"}}

    result = merge_settings(source, target)

    assert result["model"] == "opusplan"
    assert result["customKey"] == "customValue"
    assert result["nested"] == {"key": "value"}


def test_resolve_templates():
    """Test template variable resolution."""
    settings = {
        "statusLine": {
            "command": "bash {{HOME}}/.claude/statusline.sh"
        }
    }

    home_dir = Path("/Users/testuser")
    result = resolve_templates(settings, home_dir)

    assert result["statusLine"]["command"] == "bash /Users/testuser/.claude/statusline.sh"


def test_load_save_settings(temp_dir):
    """Test loading and saving settings files."""
    settings_path = temp_dir / "settings.json"

    # Test save
    settings = {"model": "opusplan", "enabledPlugins": {"test": True}}
    save_settings(settings_path, settings)

    assert settings_path.exists()

    # Test load
    loaded = load_settings(settings_path)
    assert loaded == settings


def test_load_nonexistent_settings(temp_dir):
    """Test loading settings from nonexistent file."""
    settings_path = temp_dir / "nonexistent.json"
    result = load_settings(settings_path)
    assert result == {}


def test_permissions_merge_edge_cases():
    """Test edge cases in permissions merging."""
    # Source with only allow
    source = {"permissions": {"allow": ["Bash"]}}
    target = {"permissions": {"allow": ["Read"], "deny": ["Write"], "ask": ["Edit"]}}

    result = merge_settings(source, target)

    assert set(result["permissions"]["allow"]) == {"Bash", "Read"}
    assert result["permissions"]["deny"] == ["Write"]
    assert result["permissions"]["ask"] == ["Edit"]


def test_plugins_merge_overwrite():
    """Test that team plugins overwrite user settings."""
    source = {"enabledPlugins": {"shared-plugin": True}}
    target = {"enabledPlugins": {"shared-plugin": False, "user-plugin": True}}

    result = merge_settings(source, target)

    # Team setting overwrites user
    assert result["enabledPlugins"]["shared-plugin"] is True
    # User plugin preserved
    assert result["enabledPlugins"]["user-plugin"] is True


class TestExtraKnownMarketplacesMerge:
    """extraKnownMarketplaces is union-merged keyed by marketplace name."""

    TEAM_MKT = {"source": {"source": "github", "repo": "example-org/team-config"}}

    def test_team_marketplace_added_to_user_settings(self):
        source = {"extraKnownMarketplaces": {"team": self.TEAM_MKT}}
        target = {"model": "sonnet"}

        result = merge_settings(source, target)

        assert result["extraKnownMarketplaces"] == {"team": self.TEAM_MKT}

    def test_user_marketplaces_preserved(self):
        user_mkt = {"source": {"source": "git", "url": "https://example.com/personal.git"}}
        source = {"extraKnownMarketplaces": {"team": self.TEAM_MKT}}
        target = {"extraKnownMarketplaces": {"personal": user_mkt}}

        result = merge_settings(source, target)

        assert result["extraKnownMarketplaces"] == {"team": self.TEAM_MKT, "personal": user_mkt}

    def test_team_entry_wins_for_same_name(self):
        stale = {"source": {"source": "github", "repo": "example-org/old-config"}}
        source = {"extraKnownMarketplaces": {"team": self.TEAM_MKT}}
        target = {"extraKnownMarketplaces": {"team": stale}}

        result = merge_settings(source, target)

        assert result["extraKnownMarketplaces"]["team"] == self.TEAM_MKT

    def test_user_marketplaces_kept_when_team_has_none(self):
        user_mkt = {"source": {"source": "directory", "path": "/tmp/mkt"}}
        result = merge_settings({"model": "opus"}, {"extraKnownMarketplaces": {"personal": user_mkt}})

        assert result["extraKnownMarketplaces"] == {"personal": user_mkt}

    def test_non_dict_user_value_is_replaced(self):
        source = {"extraKnownMarketplaces": {"team": self.TEAM_MKT}}
        result = merge_settings(source, {"extraKnownMarketplaces": ["not", "a", "dict"]})

        assert result["extraKnownMarketplaces"] == {"team": self.TEAM_MKT}

    def test_does_not_mutate_inputs(self):
        source = {"extraKnownMarketplaces": {"team": self.TEAM_MKT}}
        target = {"extraKnownMarketplaces": {"personal": {"source": {"source": "github", "repo": "me/mine"}}}}

        merge_settings(source, target)

        assert list(target["extraKnownMarketplaces"]) == ["personal"]
        assert list(source["extraKnownMarketplaces"]) == ["team"]
