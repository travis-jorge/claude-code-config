"""Smart settings.json merge logic."""

import json
from pathlib import Path
from typing import Any


def merge_settings(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Merge team settings with user settings intelligently.

    Rules:
    - Union permissions.allow (team + user, sorted)
    - Preserve user's permissions.deny and permissions.ask
    - Union enabledPlugins (team plugins added, user extras preserved)
    - Overwrite model, statusLine, alwaysThinkingEnabled with team standard
    - Preserve feedbackSurveyState and any unknown keys

    Args:
        source: Team settings (from config/)
        target: User's existing settings (from ~/.claude/)

    Returns:
        Merged settings dictionary
    """
    result = {}

    # Start with target (preserves unknown keys)
    result.update(target)

    # Merge permissions
    if "permissions" in source or "permissions" in target:
        result["permissions"] = _merge_permissions(
            source.get("permissions", {}), target.get("permissions", {})
        )

    # Overwrite model (team standard)
    if "model" in source:
        result["model"] = source["model"]

    # Overwrite statusLine (team standard)
    if "statusLine" in source:
        result["statusLine"] = source["statusLine"]

    # Overwrite alwaysThinkingEnabled (team standard)
    if "alwaysThinkingEnabled" in source:
        result["alwaysThinkingEnabled"] = source["alwaysThinkingEnabled"]

    # Union enabledPlugins
    if "enabledPlugins" in source or "enabledPlugins" in target:
        result["enabledPlugins"] = _merge_plugins(
            source.get("enabledPlugins", {}), target.get("enabledPlugins", {})
        )

    # Preserve feedbackSurveyState (user-specific)
    if "feedbackSurveyState" in target:
        result["feedbackSurveyState"] = target["feedbackSurveyState"]

    # Preserve $schema if present
    if "$schema" in source:
        result["$schema"] = source["$schema"]

    return result


def _merge_permissions(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Merge permissions with union on allow, preserve deny and ask."""
    result = {}

    # Union allow list (team + user, sorted)
    source_allow = set(source.get("allow", []))
    target_allow = set(target.get("allow", []))
    combined_allow = sorted(source_allow | target_allow)
    if combined_allow:
        result["allow"] = combined_allow

    # Preserve user's deny list
    if "deny" in target:
        result["deny"] = target["deny"]

    # Preserve user's ask list
    if "ask" in target:
        result["ask"] = target["ask"]

    return result


def _merge_plugins(source: dict[str, bool], target: dict[str, bool]) -> dict[str, bool]:
    """Merge enabled plugins - union of team and user plugins."""
    result = {}

    # Start with user plugins
    result.update(target)

    # Add team plugins (overwrites if user disabled)
    result.update(source)

    return result


def load_settings(path: Path) -> dict[str, Any]:
    """Load settings.json from a path."""
    if not path.exists():
        return {}

    with open(path) as f:
        return json.load(f)


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    """Save settings.json to a path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")  # Add trailing newline


def resolve_templates(settings: dict[str, Any], home_dir: Path) -> dict[str, Any]:
    """Resolve template variables in settings.

    Currently supports:
    - {{HOME}} -> User's home directory

    Args:
        settings: Settings dictionary
        home_dir: Path to user's home directory

    Returns:
        Settings with templates resolved
    """
    settings_str = json.dumps(settings)
    settings_str = settings_str.replace("{{HOME}}", str(home_dir))
    return json.loads(settings_str)
