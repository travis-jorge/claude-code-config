"""Tests for environment variable expansion in sources."""

import os
import pytest
from pathlib import Path

from claude_setup.sources import (
    expand_env_vars,
    expand_config_env_vars,
    SourceError,
)


def test_expand_env_vars_simple():
    """Test simple environment variable expansion."""
    os.environ["TEST_VAR"] = "test_value"
    assert expand_env_vars("${TEST_VAR}") == "test_value"
    assert expand_env_vars("$TEST_VAR") == "test_value"


def test_expand_env_vars_in_string():
    """Test environment variable expansion within a string."""
    os.environ["USER"] = "alice"
    assert expand_env_vars("Hello ${USER}!") == "Hello alice!"
    assert expand_env_vars("/home/$USER/config") == "/home/alice/config"


def test_expand_env_vars_multiple():
    """Test multiple environment variables in one string."""
    os.environ["HOST"] = "github.com"
    os.environ["REPO"] = "myorg/myrepo"
    result = expand_env_vars("https://${HOST}/${REPO}.git")
    assert result == "https://github.com/myorg/myrepo.git"


def test_expand_env_vars_missing():
    """Test that missing environment variable raises error."""
    # Ensure variable doesn't exist
    if "NONEXISTENT_VAR" in os.environ:
        del os.environ["NONEXISTENT_VAR"]

    with pytest.raises(SourceError, match="Environment variable 'NONEXISTENT_VAR' not set"):
        expand_env_vars("${NONEXISTENT_VAR}")


def test_expand_env_vars_non_string():
    """Test that non-strings are returned unchanged."""
    assert expand_env_vars(123) == 123
    assert expand_env_vars(None) is None
    assert expand_env_vars(True) is True


def test_expand_config_env_vars_dict():
    """Test environment variable expansion in nested dict."""
    os.environ["TOKEN"] = "secret123"
    os.environ["REPO"] = "myorg/myrepo"

    config = {
        "name": "test-source",
        "type": "github",
        "repo": "${REPO}",
        "token": "${TOKEN}",
        "nested": {
            "value": "$TOKEN"
        }
    }

    result = expand_config_env_vars(config)

    assert result["repo"] == "myorg/myrepo"
    assert result["token"] == "secret123"
    assert result["nested"]["value"] == "secret123"
    # Check original dict unchanged
    assert config["repo"] == "${REPO}"


def test_expand_config_env_vars_list():
    """Test environment variable expansion in list."""
    os.environ["VAR1"] = "value1"
    os.environ["VAR2"] = "value2"

    config = ["${VAR1}", "$VAR2", "static"]
    result = expand_config_env_vars(config)

    assert result == ["value1", "value2", "static"]


def test_expand_config_env_vars_mixed():
    """Test environment variable expansion in mixed structures."""
    os.environ["GITHUB_TOKEN"] = "ghp_test123"

    config = {
        "sources": [
            {
                "name": "source1",
                "token": "${GITHUB_TOKEN}",
                "static": "value"
            },
            {
                "name": "source2",
                "no_vars": "plain"
            }
        ]
    }

    result = expand_config_env_vars(config)

    assert result["sources"][0]["token"] == "ghp_test123"
    assert result["sources"][0]["static"] == "value"
    assert result["sources"][1]["no_vars"] == "plain"


def test_github_token_pattern():
    """Test the documented GITHUB_TOKEN pattern."""
    test_token = "ghp_" + "fake" + "token" + "example123"
    os.environ["GITHUB_TOKEN"] = test_token

    config = {
        "name": "company-config",
        "type": "github",
        "repo": "myorg/private-repo",
        "ref": "main",
        "token": "${GITHUB_TOKEN}"
    }

    result = expand_config_env_vars(config)
    assert result["token"] == test_token
