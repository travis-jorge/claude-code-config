"""Plugin and marketplace management functionality.

Required plugins are declared in the team config's ``plugins/required.json``
as a list of entries. Two entry formats are supported:

Legacy (marketplace must already be known to Claude Code)::

    {"name": "plugin@marketplace", "description": "..."}

With a marketplace declaration (marketplace is added if it is not known)::

    {
        "name": "plugin@team-marketplace",
        "description": "...",
        "marketplace": {"name": "team-marketplace", "source": "example-org/team-config"}
    }

``source`` is anything ``claude plugin marketplace add <source>`` accepts:
a GitHub ``owner/repo``, a git or https URL, or a local path. A local path
starting with ``./`` or ``../`` is resolved against the config directory; a
bare ``owner/repo`` is always treated as GitHub.

Names and sources that start with ``-`` are rejected so they can't be read as
CLI options.
"""

import json
import os
import shlex
import signal
import subprocess
from pathlib import Path
from typing import Any, Optional

# Timeouts (seconds). Marketplace add/update clone or fetch git repos, so they
# get a longer budget than a single plugin install.
PLUGIN_TIMEOUT = 120
MARKETPLACE_TIMEOUT = 300

CLI_NOT_FOUND = "claude CLI not found in PATH"
MARKETPLACE_SKIPPED = "skipped: an earlier marketplace operation timed out"


def _execute(
    argv: list[str], timeout: int, env: dict[str, str]
) -> subprocess.CompletedProcess:
    """Run argv with no stdin in its own process group.

    On timeout (or Ctrl-C) the whole process group is killed, so git children
    of the claude CLI don't linger, and TimeoutExpired/KeyboardInterrupt is
    re-raised.
    """
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except BaseException:
        _kill_group(proc)
        raise
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill proc's process group (POSIX) or proc itself, then reap it."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows
            proc.kill()
    except OSError:
        pass
    try:
        proc.communicate(timeout=5)
    except Exception:  # noqa: BLE001 - best effort reap
        pass


def _git_ssh_configured() -> bool:
    """True if git already has an SSH command configured (core.sshCommand)."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "core.sshCommand"],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _valid_token(value: Any) -> bool:
    """A non-empty string that can't be mistaken for a CLI option."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not value.strip().startswith("-")
    )


class PluginManager:
    """Manages Claude Code plugins and the marketplaces they come from."""

    def __init__(
        self,
        claude_dir: Path,
        required_plugins: list[dict],
        config_dir: Optional[Path] = None,
    ):
        """Initialize plugin manager.

        Args:
            claude_dir: Path to ~/.claude directory
            required_plugins: List of required plugin definitions
            config_dir: Team config directory; relative ``./`` marketplace
                sources are resolved against it
        """
        self.claude_dir = claude_dir
        self.config_dir = config_dir
        self.rejected: list[str] = []
        self.required_plugins = []
        for plugin in required_plugins or []:
            if not isinstance(plugin, dict):
                self.rejected.append(f"{plugin!r}: entry is not an object; ignoring it")
            elif not _valid_token(plugin.get("name")):
                self.rejected.append(
                    f"{plugin.get('name')!r}: 'name' must be a non-empty string not starting with '-'; ignoring it"
                )
            else:
                self.required_plugins.append(plugin)
        self.installed_plugins_path = claude_dir / "plugins" / "installed_plugins.json"
        self.known_marketplaces_path = (
            claude_dir / "plugins" / "known_marketplaces.json"
        )
        # Set once the claude CLI is found to be missing, so later steps are skipped
        self.cli_missing = False
        # Set once a marketplace add/update times out; later marketplace calls are skipped
        self.marketplace_timed_out = False
        # Cached: does the user have their own git SSH command configured?
        self._ssh_override: Optional[bool] = None

    # ------------------------------------------------------------------
    # Required plugin helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_marketplace(plugin: dict) -> Optional[dict[str, str]]:
        """Return the plugin's marketplace declaration, if it is well formed.

        Returns:
            ``{"name": ..., "source": ...}`` or None when absent/invalid.
        """
        marketplace = plugin.get("marketplace")
        if not isinstance(marketplace, dict):
            return None

        name = marketplace.get("name")
        source = marketplace.get("source")
        if not _valid_token(name) or not _valid_token(source):
            return None

        return {"name": name.strip(), "source": source.strip()}

    @classmethod
    def plugin_id(cls, plugin: dict) -> str:
        """Return the identifier used for install/update and status checks.

        If the entry declares a marketplace but its name has no ``@marketplace``
        suffix, the declared marketplace name is appended.
        """
        name = plugin["name"]
        marketplace = cls.get_marketplace(plugin)
        if marketplace and "@" not in name:
            return f"{name}@{marketplace['name']}"
        return name

    @classmethod
    def validate_entry(cls, plugin: dict) -> list[str]:
        """Return warnings about a required plugin entry (empty when fine)."""
        warnings = []
        name = plugin.get("name", "")

        if "marketplace" in plugin and cls.get_marketplace(plugin) is None:
            warnings.append(
                f"{name}: 'marketplace' must be an object with non-empty 'name' and 'source' "
                "(not starting with '-'); ignoring it"
            )
            return warnings

        marketplace = cls.get_marketplace(plugin)
        if marketplace and "@" in name:
            suffix = name.split("@", 1)[1]
            if suffix != marketplace["name"]:
                warnings.append(
                    f"{name}: marketplace name '{marketplace['name']}' does not match the '@{suffix}' suffix"
                )

        return warnings

    def get_warnings(self) -> list[str]:
        """Return warnings for all required plugin entries (including rejected ones)."""
        warnings = list(self.rejected)
        for plugin in self.required_plugins:
            warnings.extend(self.validate_entry(plugin))
        return warnings

    def get_team_marketplaces(self) -> dict[str, str]:
        """Return marketplaces declared by required plugins, as {name: source}.

        The first declaration of a name wins if several entries disagree.
        """
        marketplaces: dict[str, str] = {}
        for plugin in self.required_plugins:
            marketplace = self.get_marketplace(plugin)
            if marketplace and marketplace["name"] not in marketplaces:
                marketplaces[marketplace["name"]] = self.resolve_source(
                    marketplace["source"]
                )
        return marketplaces

    def resolve_source(self, source: str) -> str:
        """Resolve a ``./`` or ``../`` marketplace source against the config dir."""
        if self.config_dir is not None and source.startswith(
            ("./", "../", ".\\", "..\\")
        ):
            return str((self.config_dir / source).resolve())
        return source

    # ------------------------------------------------------------------
    # State files written by Claude Code
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> Any:
        """Read a JSON file, returning None when it is missing or unreadable."""
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError, RecursionError):
            return None

    def _get_installed_plugins(self) -> set[str]:
        """Get set of installed plugin names."""
        data = self._read_json(self.installed_plugins_path)
        if not isinstance(data, dict):
            return set()

        # Extract plugin names from the "plugins" object
        plugins = data.get("plugins", {})
        if not isinstance(plugins, dict):
            return set()
        return set(plugins.keys())

    def get_known_marketplaces(self) -> set[str]:
        """Get names of marketplaces Claude Code already knows about.

        Reads ``~/.claude/plugins/known_marketplaces.json`` (a dict keyed by
        marketplace name). A missing, invalid or unexpectedly shaped file is
        treated as "no marketplaces known".
        """
        data = self._read_json(self.known_marketplaces_path)

        if isinstance(data, dict):
            return {name for name in data.keys() if isinstance(name, str)}

        if isinstance(data, list):
            # Tolerate a list of {"name": ...} objects
            return {
                item["name"]
                for item in data
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }

        return set()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def check_installed(self) -> dict[str, bool]:
        """Check which required plugins are installed.

        Returns:
            Dictionary mapping plugin name to installation status
        """
        installed = self._get_installed_plugins()
        status = {}

        for plugin in self.required_plugins:
            status[plugin["name"]] = self.plugin_id(plugin) in installed

        return status

    def get_missing_plugins(self) -> list[dict]:
        """Get list of required plugins that are not installed."""
        status = self.check_installed()
        return [
            plugin for plugin in self.required_plugins if not status[plugin["name"]]
        ]

    def get_installed_required_plugins(self) -> list[dict]:
        """Get list of required plugins that are installed."""
        status = self.check_installed()
        return [plugin for plugin in self.required_plugins if status[plugin["name"]]]

    def get_install_commands(self) -> list[str]:
        """Get shell commands that would install the missing plugins."""
        known = self.get_known_marketplaces()
        commands = []
        added = set()

        for plugin in self.get_missing_plugins():
            marketplace = self.get_marketplace(plugin)
            if (
                marketplace
                and marketplace["name"] not in known
                and marketplace["name"] not in added
            ):
                source = self.resolve_source(marketplace["source"])
                commands.append(f"claude plugin marketplace add {shlex.quote(source)}")
                added.add(marketplace["name"])
            commands.append(
                f"claude plugin install {shlex.quote(self.plugin_id(plugin))}"
            )

        return commands

    # ------------------------------------------------------------------
    # claude CLI wrappers
    # ------------------------------------------------------------------

    def _env(self) -> dict[str, str]:
        """Environment for claude CLI calls: git must never wait for a prompt.

        GIT_TERMINAL_PROMPT=0 stops credential prompts. GIT_SSH_COMMAND is set
        to BatchMode only when the user has no SSH override of their own
        (GIT_SSH_COMMAND, GIT_SSH or git config core.sshCommand).
        """
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        if self._ssh_override is None:
            self._ssh_override = (
                bool(env.get("GIT_SSH_COMMAND") or env.get("GIT_SSH"))
                or _git_ssh_configured()
            )
        if not self._ssh_override:
            env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
        return env

    def _run(
        self,
        args: list[str],
        timeout: int,
        timeout_message: str,
        marketplace: bool = False,
    ) -> tuple[bool, str]:
        """Run a ``claude`` CLI command non-interactively.

        stdin is closed so a confirmation prompt fails fast instead of hanging.
        We deliberately do not pass ``-y``: that would auto-accept commands a
        marketplace declares, which should stay a human decision.
        """
        if self.cli_missing:
            return False, CLI_NOT_FOUND
        if marketplace and self.marketplace_timed_out:
            return False, MARKETPLACE_SKIPPED

        try:
            result = _execute(["claude", *args], timeout=timeout, env=self._env())
        except subprocess.TimeoutExpired:
            if marketplace:
                self.marketplace_timed_out = True
            return False, timeout_message
        except FileNotFoundError:
            self.cli_missing = True
            return False, CLI_NOT_FOUND
        except Exception as e:  # noqa: BLE001 - report, never crash the caller
            return False, f"Unexpected error: {e}"

        if result.returncode == 0:
            return True, (result.stdout or "").strip()
        return False, (
            (result.stderr or "").strip()
            or (result.stdout or "").strip()
            or f"exit code {result.returncode}"
        )

    def install_plugin(self, name: str) -> tuple[bool, str]:
        """Install a plugin: ``claude plugin install <plugin>``.

        Args:
            name: Plugin name (e.g., "ralph-loop@claude-plugins-official")

        Returns:
            Tuple of (success, output/error message)
        """
        return self._run(
            ["plugin", "install", name], PLUGIN_TIMEOUT, "Plugin installation timed out"
        )

    def update_plugin(self, name: str) -> tuple[bool, str]:
        """Update an installed plugin: ``claude plugin update <plugin>``."""
        return self._run(
            ["plugin", "update", name], PLUGIN_TIMEOUT, "Plugin update timed out"
        )

    def add_marketplace(self, source: str) -> tuple[bool, str]:
        """Add a marketplace: ``claude plugin marketplace add <source>``."""
        return self._run(
            ["plugin", "marketplace", "add", self.resolve_source(source)],
            MARKETPLACE_TIMEOUT,
            "Adding marketplace timed out",
            marketplace=True,
        )

    def update_marketplace(self, name: str) -> tuple[bool, str]:
        """Refresh a marketplace: ``claude plugin marketplace update <name>``."""
        return self._run(
            ["plugin", "marketplace", "update", name],
            MARKETPLACE_TIMEOUT,
            "Updating marketplace timed out",
            marketplace=True,
        )

    def ensure_marketplace(self, name: str, source: str) -> tuple[bool, str]:
        """Add the marketplace unless Claude Code already knows it."""
        if name in self.get_known_marketplaces():
            return True, "already known"
        return self.add_marketplace(source)

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def install_all_missing(
        self, marketplace_results: Optional[dict[str, tuple[bool, str]]] = None
    ) -> dict[str, tuple[bool, str]]:
        """Install all missing plugins, adding declared marketplaces first.

        Args:
            marketplace_results: Optional dict of marketplace outcomes already
                known for this run (e.g. from refresh_marketplaces), keyed by
                name. Those marketplaces are not attempted again; outcomes of
                any marketplaces ensured here are added to it.

        Returns:
            Dictionary mapping plugin name to (success, message) tuple
        """
        results: dict[str, tuple[bool, str]] = {}
        ensured: dict[str, tuple[bool, str]] = dict(marketplace_results or {})

        for plugin in self.get_missing_plugins():
            plugin_name = plugin["name"]
            marketplace = self.get_marketplace(plugin)

            if marketplace:
                mkt_name = marketplace["name"]
                if mkt_name not in ensured:
                    ensured[mkt_name] = self.ensure_marketplace(
                        mkt_name, marketplace["source"]
                    )
                ok, message = ensured[mkt_name]
                if not ok:
                    results[plugin_name] = (
                        False,
                        f"marketplace '{mkt_name}' could not be added: {message}",
                    )
                    continue

            results[plugin_name] = self.install_plugin(self.plugin_id(plugin))

        if marketplace_results is not None:
            marketplace_results.update(ensured)

        return results

    def refresh_marketplaces(self) -> dict[str, tuple[bool, str]]:
        """Refresh every team marketplace declared in required.json.

        Known marketplaces are updated; unknown ones are added from their
        declared source.
        """
        results: dict[str, tuple[bool, str]] = {}
        known = self.get_known_marketplaces()

        for name, source in self.get_team_marketplaces().items():
            if name in known:
                results[name] = self.update_marketplace(name)
            else:
                ok, message = self.add_marketplace(source)
                results[name] = (ok, f"added: {message}" if ok else message)

        return results

    def update_installed(self) -> dict[str, tuple[bool, str]]:
        """Run ``claude plugin update`` for every installed required plugin."""
        results: dict[str, tuple[bool, str]] = {}
        for plugin in self.get_installed_required_plugins():
            results[plugin["name"]] = self.update_plugin(self.plugin_id(plugin))
        return results

    def sync(self) -> dict[str, dict[str, tuple[bool, str]]]:
        """Bring required plugins up to date. Never raises for CLI failures.

        Order: refresh team marketplaces, install missing required plugins,
        then update the required plugins that were already installed.

        Returns:
            ``{"marketplaces": {...}, "installed": {...}, "updated": {...}}``,
            each mapping a name to (success, message).
        """
        already_installed = self.get_installed_required_plugins()

        known_before = self.get_known_marketplaces()
        marketplaces = self.refresh_marketplaces()
        # Reuse the outcome of marketplaces that had to be *added*, so a failed add
        # is not retried and its plugins are reported as blocked by it. A failed
        # refresh of an already-known marketplace does not block installs.
        added = {
            name: result
            for name, result in marketplaces.items()
            if name not in known_before
        }
        installed = self.install_all_missing(added)

        updated: dict[str, tuple[bool, str]] = {}
        for plugin in already_installed:
            updated[plugin["name"]] = self.update_plugin(self.plugin_id(plugin))

        return {
            "marketplaces": marketplaces,
            "installed": installed,
            "updated": updated,
        }
