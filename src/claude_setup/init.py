"""Initialization and source configuration."""

import json
from pathlib import Path
from typing import Optional, Tuple

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


def validate_config_source(path: Path) -> Tuple[bool, str, Optional[Path]]:
    """Check if a directory is a valid config source.

    Args:
        path: Path to check

    Returns:
        Tuple of (is_valid, message, resolved_path_if_different)
        - is_valid: True if valid config source
        - message: Description of the result
        - resolved_path: Path if manifest found one level deep, else None
    """
    if not path.exists():
        return False, f"Path does not exist: {path}", None

    if not path.is_dir():
        return False, f"Path is not a directory: {path}", None

    # Check for manifest.json at this level
    manifest_path = path / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                data = json.load(f)

            if "categories" not in data:
                return False, "manifest.json missing 'categories' field", None

            if not isinstance(data["categories"], list) or len(data["categories"]) == 0:
                return False, "manifest.json 'categories' must be a non-empty list", None

            return True, "Valid config source", None

        except json.JSONDecodeError as e:
            return False, f"manifest.json is not valid JSON: {e}", None
        except Exception as e:
            return False, f"Error reading manifest.json: {e}", None

    # Check one level deep (for zip extractions with wrapper directory)
    subdirs = [d for d in path.iterdir() if d.is_dir()]
    if len(subdirs) == 1:
        subdir = subdirs[0]
        subdir_manifest = subdir / "manifest.json"

        if subdir_manifest.exists():
            try:
                with open(subdir_manifest) as f:
                    data = json.load(f)

                if "categories" not in data:
                    return False, "manifest.json missing 'categories' field", None

                if not isinstance(data["categories"], list) or len(data["categories"]) == 0:
                    return False, "manifest.json 'categories' must be a non-empty list", None

                return True, f"Valid config source (found in subdirectory {subdir.name})", subdir

            except json.JSONDecodeError as e:
                return False, f"manifest.json is not valid JSON: {e}", None
            except Exception as e:
                return False, f"Error reading manifest.json: {e}", None

    return False, "manifest.json not found (checked current directory and one level deep)", None
