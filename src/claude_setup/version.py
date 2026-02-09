"""Version tracking and update detection."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class VersionManager:
    """Manages version stamps and update detection."""

    def __init__(self, claude_dir: Path, config_dir: Path):
        """Initialize version manager.

        Args:
            claude_dir: Path to ~/.claude directory
            config_dir: Path to config/ directory in the tool
        """
        self.claude_dir = claude_dir
        self.config_dir = config_dir
        self.stamp_path = claude_dir / ".claude-setup-version.json"

    def get_installed(self) -> dict:
        """Read installed version stamp.

        Returns:
            Dictionary with tool_version, config_hash, installed_at, categories
        """
        if not self.stamp_path.exists():
            return {}

        try:
            with open(self.stamp_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            return {}

    def get_available(self) -> dict:
        """Compute available version info from config files.

        Returns:
            Dictionary with tool_version and config_hash
        """
        from claude_setup import __version__

        config_hash = self._compute_config_hash()

        return {
            "tool_version": __version__,
            "config_hash": config_hash,
        }

    def has_updates(self) -> bool:
        """Check if updates are available.

        Returns:
            True if config has changed or no installation exists
        """
        installed = self.get_installed()
        if not installed:
            return True

        available = self.get_available()
        return installed.get("config_hash") != available.get("config_hash")

    def write_stamp(self, categories: list[str]) -> None:
        """Write version stamp after successful installation.

        Args:
            categories: List of installed category names
        """
        from claude_setup import __version__

        stamp = {
            "tool_version": __version__,
            "config_hash": self._compute_config_hash(),
            "installed_at": datetime.now().isoformat(),
            "categories": categories,
        }

        self.stamp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.stamp_path, "w") as f:
            json.dump(stamp, f, indent=2)
            f.write("\n")

    def _compute_config_hash(self) -> str:
        """Compute SHA256 hash of all config files.

        Returns:
            Hex string of the hash
        """
        hasher = hashlib.sha256()

        # Get all files in config/ directory, sorted for consistency
        config_files = sorted(self.config_dir.rglob("*"))

        for file_path in config_files:
            if not file_path.is_file():
                continue

            # Skip hidden files and system files
            if file_path.name.startswith("."):
                continue

            # Add file path (for structure changes) and content
            hasher.update(str(file_path.relative_to(self.config_dir)).encode())

            try:
                with open(file_path, "rb") as f:
                    hasher.update(f.read())
            except (IOError, PermissionError):
                # Skip files we can't read
                continue

        return hasher.hexdigest()
