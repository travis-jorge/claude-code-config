"""Initialization and source configuration."""

import json
from pathlib import Path

from claude_setup.sources import SourceManager


def get_sources_file(claude_dir: Path) -> Path:
    """Get path to sources configuration file.

    Checks in order:
    1. ~/.claude/sources.json
    2. .claude-setup-sources.json in tool directory
    3. None (will need to use examples)

    Args:
        claude_dir: Path to ~/.claude directory

    Returns:
        Path to sources file, or None if not found
    """
    # User-specific sources
    user_sources = claude_dir / "sources.json"
    if user_sources.exists():
        return user_sources

    # Tool-bundled sources (for organizations that fork the tool)
    from claude_setup.cli import get_tool_dir

    tool_sources = get_tool_dir() / ".claude-setup-sources.json"
    if tool_sources.exists():
        return tool_sources

    return None


def has_sources_configured(claude_dir: Path) -> bool:
    """Check if sources are configured."""
    return get_sources_file(claude_dir) is not None


def create_default_sources(claude_dir: Path, source_config: dict) -> Path:
    """Create default sources.json file.

    Args:
        claude_dir: Path to ~/.claude directory
        source_config: Source configuration dict

    Returns:
        Path to created sources.json file
    """
    sources_file = claude_dir / "sources.json"
    sources_file.parent.mkdir(parents=True, exist_ok=True)

    with open(sources_file, "w") as f:
        json.dump(source_config, f, indent=2)
        f.write("\n")

    return sources_file


def get_config_dir_from_sources(claude_dir: Path) -> Path:
    """Get configuration directory by fetching from configured sources.

    Args:
        claude_dir: Path to ~/.claude directory

    Returns:
        Path to configuration directory

    Raises:
        FileNotFoundError: If no sources configured
        SourceError: If fetch fails
    """
    sources_file = get_sources_file(claude_dir)

    if not sources_file:
        raise FileNotFoundError(
            "No sources configured. Run 'claude-setup init' or see ADMIN-GUIDE.md"
        )

    cache_dir = claude_dir / "sources"
    source_mgr = SourceManager(cache_dir)
    source_mgr.load_sources(sources_file)

    # Get primary source
    config_dir = source_mgr.get_primary_source()

    if not config_dir:
        raise FileNotFoundError("No sources configured")

    return config_dir


def get_config_dir_fallback() -> Path:
    """Get config directory, checking examples if sources not configured.

    Returns:
        Path to configuration directory

    Raises:
        FileNotFoundError: If no config available
    """
    claude_dir = Path.home() / ".claude"

    # Try sources first
    try:
        return get_config_dir_from_sources(claude_dir)
    except FileNotFoundError:
        pass

    # Fall back to examples (for development/testing)
    from claude_setup.cli import get_tool_dir

    example_config = get_tool_dir() / "examples" / "config-template"
    if example_config.exists():
        return example_config

    raise FileNotFoundError(
        "No configuration source found. Please run 'claude-setup init' "
        "to configure a source, or use 'claude-setup init --local examples/config-template' "
        "to use the included template. See ADMIN-GUIDE.md for details."
    )
