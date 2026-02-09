"""Plugin management functionality."""

import json
import subprocess
from pathlib import Path
from typing import Optional


class PluginManager:
    """Manages Claude Code plugins."""

    def __init__(self, claude_dir: Path, required_plugins: list[dict]):
        """Initialize plugin manager.

        Args:
            claude_dir: Path to ~/.claude directory
            required_plugins: List of required plugin definitions
        """
        self.claude_dir = claude_dir
        self.required_plugins = required_plugins
        self.installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"

    def check_installed(self) -> dict[str, bool]:
        """Check which required plugins are installed.

        Returns:
            Dictionary mapping plugin name to installation status
        """
        installed = self._get_installed_plugins()
        status = {}

        for plugin in self.required_plugins:
            plugin_name = plugin["name"]
            status[plugin_name] = plugin_name in installed

        return status

    def _get_installed_plugins(self) -> set[str]:
        """Get set of installed plugin names."""
        if not self.installed_plugins_path.exists():
            return set()

        try:
            with open(self.installed_plugins_path) as f:
                data = json.load(f)

            # Extract plugin names from the "plugins" object
            plugins = data.get("plugins", {})
            return set(plugins.keys())
        except (json.JSONDecodeError, KeyError):
            return set()

    def get_missing_plugins(self) -> list[dict]:
        """Get list of required plugins that are not installed."""
        status = self.check_installed()
        missing = []

        for plugin in self.required_plugins:
            if not status[plugin["name"]]:
                missing.append(plugin)

        return missing

    def get_install_commands(self) -> list[str]:
        """Get install commands for missing plugins."""
        missing = self.get_missing_plugins()
        commands = []

        for plugin in missing:
            commands.append(f"claude plugin install {plugin['name']}")

        return commands

    def install_plugin(self, name: str) -> tuple[bool, str]:
        """Install a plugin using claude CLI.

        Args:
            name: Plugin name (e.g., "ralph-loop@claude-plugins-official")

        Returns:
            Tuple of (success, output/error message)
        """
        try:
            result = subprocess.run(
                ["claude", "plugin", "install", name],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout

        except subprocess.TimeoutExpired:
            return False, "Plugin installation timed out"
        except FileNotFoundError:
            return False, "claude CLI not found in PATH"
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def install_all_missing(self) -> dict[str, tuple[bool, str]]:
        """Install all missing plugins.

        Returns:
            Dictionary mapping plugin name to (success, message) tuple
        """
        missing = self.get_missing_plugins()
        results = {}

        for plugin in missing:
            plugin_name = plugin["name"]
            success, message = self.install_plugin(plugin_name)
            results[plugin_name] = (success, message)

        return results
