"""Scan ~/.claude and generate exportable config repos."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class ScannedFile:
    """File discovered in ~/.claude."""
    source_path: Path       # Absolute path in ~/.claude
    relative_path: str      # Path relative to ~/.claude
    category: str           # core, agents, rules, commands
    size: int
    is_executable: bool


@dataclass
class ScannedSettings:
    """Settings.json analysis."""
    raw: dict               # Full settings.json
    team_fields: dict       # Fields for team config
    personal_fields: dict   # Fields to exclude
    home_dir: str           # For reverse template substitution


@dataclass
class ScanResult:
    """Complete scan of ~/.claude directory."""
    files: list[ScannedFile]
    settings: Optional[ScannedSettings]
    plugins: list[dict]     # Derived required plugins
    claude_dir: Path


@dataclass
class ConfigPlan:
    """Plan for generating config repo."""
    output_dir: Path
    selected_files: list[ScannedFile]
    settings: Optional[dict]  # Filtered team settings with {{HOME}}
    plugins: list[dict]
    init_git: bool
    config_name: str


# Skip patterns for scanning
SKIP_DIRS = {
    "backups",
    "sources",
    "plugins",
    "__pycache__",
    ".git",
    "plans",
}

SKIP_FILES = {
    ".claude-setup-version.json",
    "sources.json",
}


def scan_claude_dir(claude_dir: Path) -> ScanResult:
    """Scan ~/.claude directory and classify files.

    Args:
        claude_dir: Path to ~/.claude directory

    Returns:
        ScanResult with classified files, settings, and plugins
    """
    files = []

    # Walk the directory
    for item in claude_dir.rglob("*"):
        # Skip if not a file
        if not item.is_file():
            continue

        # Skip symlinks pointing outside claude_dir (security)
        if item.is_symlink():
            try:
                resolved = item.resolve(strict=True)
                if not str(resolved).startswith(str(claude_dir.resolve())):
                    continue  # Skip symlinks pointing outside the source
            except (OSError, RuntimeError):
                continue  # Skip broken symlinks

        # Get relative path
        try:
            rel_path = item.relative_to(claude_dir)
        except ValueError:
            continue

        # Skip files in excluded directories
        if any(part in SKIP_DIRS for part in rel_path.parts):
            continue

        # Skip specific files
        if rel_path.name in SKIP_FILES:
            continue

        # Classify by path
        category = _classify_file(rel_path)
        if not category:
            continue

        # Get file info
        stat = item.stat()
        is_executable = bool(stat.st_mode & 0o111)

        files.append(ScannedFile(
            source_path=item,
            relative_path=str(rel_path),
            category=category,
            size=stat.st_size,
            is_executable=is_executable,
        ))

    # Scan settings and plugins separately
    settings = scan_settings(claude_dir)
    plugins = scan_plugins(claude_dir)

    return ScanResult(
        files=files,
        settings=settings,
        plugins=plugins,
        claude_dir=claude_dir,
    )


def _classify_file(rel_path: Path) -> Optional[str]:
    """Classify file by its path.

    Args:
        rel_path: Path relative to ~/.claude

    Returns:
        Category name or None if unclassified
    """
    parts = rel_path.parts

    # Top-level known files
    if len(parts) == 1:
        name = parts[0]
        if name in ("CLAUDE.md", "settings.json", "statusline.sh"):
            return "core"
        return None

    # Subdirectories
    first_dir = parts[0]
    if first_dir == "agents":
        return "agents"
    elif first_dir == "rules":
        return "rules"
    elif first_dir == "commands":
        return "commands"

    return None


def scan_settings(claude_dir: Path) -> Optional[ScannedSettings]:
    """Scan and classify settings.json fields.

    Args:
        claude_dir: Path to ~/.claude directory

    Returns:
        ScannedSettings or None if settings.json doesn't exist
    """
    settings_path = claude_dir / "settings.json"
    if not settings_path.exists():
        return None

    with open(settings_path) as f:
        raw = json.load(f)

    # Classify fields
    team_fields = {}
    personal_fields = {}

    # Team standard fields (will be overwritten on install)
    TEAM_FIELD_NAMES = {
        "$schema",
        "model",
        "statusLine",
        "alwaysThinkingEnabled",
    }

    for key, value in raw.items():
        if key in TEAM_FIELD_NAMES:
            team_fields[key] = value
        elif key == "permissions":
            # Split permissions - allow is team, deny/ask are personal
            perms = {}
            if "allow" in value:
                perms["allow"] = value["allow"]
            if perms:
                team_fields["permissions"] = perms

            personal_perms = {}
            if "deny" in value:
                personal_perms["deny"] = value["deny"]
            if "ask" in value:
                personal_perms["ask"] = value["ask"]
            if personal_perms:
                personal_fields["permissions"] = personal_perms
        elif key == "enabledPlugins":
            team_fields["enabledPlugins"] = value
        elif key == "feedbackSurveyState":
            personal_fields[key] = value
        else:
            # Unknown keys are personal
            personal_fields[key] = value

    return ScannedSettings(
        raw=raw,
        team_fields=team_fields,
        personal_fields=personal_fields,
        home_dir=str(Path.home()),
    )


def scan_plugins(claude_dir: Path) -> list[dict]:
    """Scan installed plugins.

    Args:
        claude_dir: Path to ~/.claude directory

    Returns:
        List of plugin dicts with name and description
    """
    plugins_path = claude_dir / "plugins" / "installed_plugins.json"
    if not plugins_path.exists():
        return []

    with open(plugins_path) as f:
        installed = json.load(f)

    # Convert to required.json format
    plugins = []
    for name in installed.keys():
        plugins.append({
            "name": name,
            "description": "",
        })

    return plugins


def filter_settings_for_team(
    settings: ScannedSettings,
    custom_allow: Optional[list] = None,
    custom_plugins: Optional[dict] = None,
) -> dict:
    """Filter settings to include only team-relevant fields.

    Args:
        settings: ScannedSettings with classified fields
        custom_allow: Optional override for permissions.allow
        custom_plugins: Optional override for enabledPlugins

    Returns:
        Filtered settings dict with {{HOME}} templates
    """
    result = dict(settings.team_fields)

    # Override permissions.allow if provided
    if custom_allow is not None:
        if "permissions" not in result:
            result["permissions"] = {}
        result["permissions"]["allow"] = custom_allow

    # Override enabledPlugins if provided
    if custom_plugins is not None:
        result["enabledPlugins"] = custom_plugins

    # Apply reverse templates
    result = apply_reverse_templates(result, settings.home_dir)

    return result


def apply_reverse_templates(data: dict, home_dir: str) -> dict:
    """Replace home directory paths with {{HOME}} template variable.

    Args:
        data: Settings dictionary
        home_dir: User's home directory path

    Returns:
        Settings with home_dir replaced by {{HOME}}
    """
    data_str = json.dumps(data)
    data_str = data_str.replace(home_dir, "{{HOME}}")
    return json.loads(data_str)


def generate_config_repo(plan: ConfigPlan, force: bool = False) -> Path:
    """Generate a config repo from the plan.

    Args:
        plan: ConfigPlan with all generation parameters
        force: If True, overwrite existing directory

    Returns:
        Path to generated config directory

    Raises:
        FileExistsError: If output_dir exists and force=False
    """
    output_dir = plan.output_dir

    # Check if directory exists and is non-empty
    if output_dir.exists():
        if any(output_dir.iterdir()):
            if not force:
                raise FileExistsError(
                    f"Directory {output_dir} already exists and is not empty. "
                    "Use force=True to overwrite."
                )
            # Clear directory contents
            for item in output_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

    # Create directory structure
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "core").mkdir(exist_ok=True)
    (output_dir / "agents").mkdir(exist_ok=True)
    (output_dir / "rules").mkdir(exist_ok=True)
    (output_dir / "commands").mkdir(exist_ok=True)
    (output_dir / "plugins").mkdir(exist_ok=True)

    # Copy files by category
    for file in plan.selected_files:
        # Skip settings.json - we'll write the filtered version
        if file.relative_path == "settings.json":
            continue

        try:
            # Determine destination
            dest_dir = output_dir / file.category
            dest_path = dest_dir / Path(file.relative_path).name

            # For nested paths (commands, rules, agents), preserve structure
            if file.category in ("commands", "rules", "agents"):
                rel_to_category = Path(file.relative_path).relative_to(file.category)
                dest_path = dest_dir / rel_to_category
                dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(file.source_path, dest_path)

            # Preserve executable bit
            if file.is_executable:
                dest_path.chmod(dest_path.stat().st_mode | 0o111)

        except (OSError, PermissionError, IOError) as e:
            # Skip files that can't be copied, but continue with others
            print(f"Warning: Skipped {file.relative_path}: {e}", file=sys.stderr)
            continue

    # Write filtered settings.json
    if plan.settings:
        settings_path = output_dir / "core" / "settings.json"
        with open(settings_path, "w") as f:
            json.dump(plan.settings, f, indent=2)
            f.write("\n")

    # Write plugins/required.json
    if plan.plugins:
        plugins_path = output_dir / "plugins" / "required.json"
        with open(plugins_path, "w") as f:
            json.dump({"plugins": plan.plugins}, f, indent=2)
            f.write("\n")

    # Generate manifest.json
    has_settings = plan.settings is not None
    has_plugins = len(plan.plugins) > 0
    manifest = generate_manifest(
        output_dir,
        plan.selected_files,
        has_settings,
        has_plugins,
    )
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    # Initialize git if requested
    if plan.init_git:
        try:
            result = subprocess.run(
                ["git", "init"],
                cwd=output_dir,
                capture_output=True,
                check=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # Git not installed or init failed - not critical, continue
            print(
                f"Warning: Could not initialize git repository: {e}",
                file=sys.stderr
            )

    return output_dir


def generate_manifest(
    output_dir: Path,
    selected_files: list[ScannedFile],
    has_settings: bool,
    has_plugins: bool,
) -> dict:
    """Generate manifest.json for config repo.

    Args:
        output_dir: Output directory path
        selected_files: List of files to include
        has_settings: Whether settings.json is included
        has_plugins: Whether plugins are included

    Returns:
        Manifest dictionary
    """
    # Group files by category
    files_by_category = {
        "core": [],
        "agents": [],
        "rules": [],
        "commands": [],
    }

    for file in selected_files:
        if file.category in files_by_category:
            files_by_category[file.category].append(file)

    # Build categories
    categories = []

    # Core category
    core_files = []
    for file in files_by_category["core"]:
        filename = Path(file.relative_path).name

        # Determine flags
        merge = False
        executable = file.is_executable
        template = False

        if filename == "settings.json":
            merge = True
            template = True
        elif filename == "statusline.sh":
            executable = True
            template = True
        elif filename == "CLAUDE.md":
            template = True

        core_files.append({
            "src": f"core/{filename}",
            "dest": filename,
            "merge": merge,
            "executable": executable,
            "template": template,
        })

    # Add settings.json if present but not in files list
    if has_settings and not any(f["dest"] == "settings.json" for f in core_files):
        core_files.append({
            "src": "core/settings.json",
            "dest": "settings.json",
            "merge": True,
            "executable": False,
            "template": True,
        })

    categories.append({
        "name": "core",
        "description": "Core configuration files (CLAUDE.md, settings.json, statusline)",
        "target_dir": ".claude",
        "install_type": "merge",
        "files": core_files,
    })

    # Agents category
    agent_files = []
    for file in files_by_category["agents"]:
        rel_to_agents = Path(file.relative_path).relative_to("agents")
        agent_files.append({
            "src": f"agents/{rel_to_agents}",
            "dest": str(rel_to_agents),
            "merge": False,
            "executable": file.is_executable,
            "template": False,
        })

    categories.append({
        "name": "agents",
        "description": "Agent definition files",
        "target_dir": ".claude/agents",
        "install_type": "overwrite",
        "files": agent_files,
    })

    # Rules category
    rule_files = []
    for file in files_by_category["rules"]:
        rel_to_rules = Path(file.relative_path).relative_to("rules")
        rule_files.append({
            "src": f"rules/{rel_to_rules}",
            "dest": str(rel_to_rules),
            "merge": False,
            "executable": file.is_executable,
            "template": False,
        })

    categories.append({
        "name": "rules",
        "description": "Team rules and guidelines",
        "target_dir": ".claude/rules",
        "install_type": "overwrite",
        "files": rule_files,
    })

    # Commands category (discover mode)
    categories.append({
        "name": "commands",
        "description": "Custom commands and workflows",
        "target_dir": ".claude/commands",
        "install_type": "discover",
        "files": [],
    })

    # Plugins category (check mode)
    categories.append({
        "name": "plugins",
        "description": "Required Claude Code plugins",
        "target_dir": ".claude/plugins",
        "install_type": "check",
        "files": [],
    })

    return {
        "version": "1.0.0",
        "categories": categories,
    }


def preview_config_plan(plan: ConfigPlan) -> dict:
    """Preview what will be generated from the plan.

    Args:
        plan: ConfigPlan to preview

    Returns:
        Summary dictionary
    """
    # Count files by category
    category_counts = {}
    file_lists = {}

    for category in ("core", "agents", "rules", "commands"):
        files = [f for f in plan.selected_files if f.category == category]
        category_counts[category] = len(files)
        file_lists[category] = [f.relative_path for f in files]

    # Add settings to core count if present
    if plan.settings and "settings.json" not in file_lists["core"]:
        category_counts["core"] = category_counts.get("core", 0) + 1
        file_lists.setdefault("core", []).append("settings.json")

    return {
        "category_counts": category_counts,
        "file_lists": file_lists,
        "output_path": str(plan.output_dir),
        "has_settings": plan.settings is not None,
        "has_plugins": len(plan.plugins) > 0,
        "plugin_count": len(plan.plugins),
        "will_init_git": plan.init_git,
    }
