"""CLI interface using Typer."""

import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

import questionary
import typer
from rich.console import Console
from rich.markup import escape

from claude_setup import __version__
from claude_setup.backup import BackupError, BackupManager
from claude_setup.categories import CategoryRegistry
from claude_setup.create_config import (
    ConfigPlan,
    filter_settings_for_team,
    generate_config_repo,
    preview_config_plan,
    scan_claude_dir,
    scan_settings,
)
from claude_setup.display import (
    confirm,
    print_error,
    print_info,
    print_success,
    print_warning,
    show_archive_plan,
    show_backup_list,
    show_banner,
    show_categories,
    show_config_preview,
    show_install_plan,
    show_restore_result,
    show_scan_results,
    show_status,
    show_summary,
)
from claude_setup.installer import Installer, InstallationError
from claude_setup.plugins import PluginManager
from claude_setup.version import VersionManager

app = typer.Typer(
    name="claude-setup",
    help="Interactive CLI installer for Claude Code team configuration",
    add_completion=False,
)

console = Console()


def get_tool_dir() -> Path:
    """Get path to tool directory (repo root)."""
    # When installed as package or running in development
    return Path(__file__).parent.parent.parent


def get_config_dir() -> Path:
    """Get path to config directory from sources or fallback."""
    from claude_setup.init import get_config_dir_fallback

    try:
        return get_config_dir_fallback()
    except FileNotFoundError as e:
        # Provide helpful error message
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}\n")
        console.print("[bold]Quick Start:[/bold]")
        console.print("  1. Run: [cyan]claude-setup init[/cyan]")
        console.print("  2. Or see: [cyan]ADMIN-GUIDE.md[/cyan] for setting up sources\n")
        raise typer.Exit(1)


def get_claude_dir() -> Path:
    """Get path to ~/.claude directory."""
    return Path.home() / ".claude"


def initialize_managers():
    """Initialize all manager objects."""
    config_dir = get_config_dir()
    claude_dir = get_claude_dir()

    registry = CategoryRegistry(config_dir)
    backup_mgr = BackupManager(claude_dir)
    version_mgr = VersionManager(claude_dir, config_dir)

    # Load required plugins (optional file)
    plugins_file = config_dir / "plugins" / "required.json"
    required_plugins = []
    if plugins_file.exists():
        with open(plugins_file) as f:
            required_plugins = json.load(f)
        if not isinstance(required_plugins, list):
            raise ValueError(f"{plugins_file} must contain a JSON list of plugin entries")

    plugin_mgr = PluginManager(claude_dir, required_plugins, config_dir=config_dir)

    installer = Installer(config_dir, claude_dir, registry, backup_mgr, version_mgr)

    return registry, backup_mgr, version_mgr, plugin_mgr, installer


def _print_results(results: dict[str, tuple[bool, str]], ok_verb: str, fail_verb: str) -> int:
    """Print (success, message) results; return the number of failures."""
    failures = 0
    for name, (success, message) in results.items():
        if success:
            print_success(f"{ok_verb} {name}")
        else:
            failures += 1
            print_error(f"{fail_verb} {name}: {message}")
    return failures


def sync_plugins(plugin_mgr: PluginManager) -> int:
    """Refresh team marketplaces, install missing and update installed required plugins.

    Failures are reported, never raised, so a plugin problem cannot fail a
    configuration update.

    Returns:
        Number of failed steps
    """
    if not plugin_mgr.required_plugins:
        print_info("No required plugins declared; skipping plugin sync")
        return 0

    for warning in plugin_mgr.get_warnings():
        print_warning(warning)

    console.print("\n[bold]Syncing plugins...[/bold]")
    try:
        results = plugin_mgr.sync()
    except Exception as e:  # noqa: BLE001 - plugin sync must never be fatal
        print_error(f"Plugin sync failed: {e}")
        return 1

    failures = 0
    failures += _print_results(results["marketplaces"], "Refreshed marketplace", "Failed to refresh marketplace")
    failures += _print_results(results["installed"], "Installed plugin", "Failed to install plugin")
    failures += _print_results(results["updated"], "Updated plugin", "Failed to update plugin")

    if plugin_mgr.cli_missing:
        print_warning("The claude CLI was not found in PATH; plugin steps were skipped")
    if failures:
        print_warning(f"{failures} plugin step(s) failed. Run 'claude-setup plugins' for details.")
    else:
        print_success("Plugins are up to date (restart Claude Code to apply plugin updates)")
    return failures


def _parse_github_url(url: str) -> Optional[tuple[str, str]]:
    """Parse GitHub URL into owner/repo tuple.

    Supports formats:
    - https://github.com/owner/repo(.git)
    - git@github.com:owner/repo(.git)
    - github.com/owner/repo

    Args:
        url: GitHub URL string

    Returns:
        Tuple of (owner, repo) or None if not a GitHub URL
    """
    # Remove .git suffix if present
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # Pattern 1: https://github.com/owner/repo
    match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/?$", url)
    if match:
        return match.group(1), match.group(2)

    # Pattern 2: git@github.com:owner/repo
    match = re.match(r"^git@github\.com:([^/]+)/([^/]+)/?$", url)
    if match:
        return match.group(1), match.group(2)

    # Pattern 3: github.com/owner/repo (without protocol)
    match = re.match(r"^github\.com/([^/]+)/([^/]+)/?$", url)
    if match:
        return match.group(1), match.group(2)

    return None


def _detect_github_remote(repo_path: Path) -> Optional[str]:
    """Detect GitHub remote from a git repository.

    Args:
        repo_path: Path to git repository

    Returns:
        String "owner/repo" or None if no GitHub remote found
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        remote_url = result.stdout.strip()

        parsed = _parse_github_url(remote_url)
        if parsed:
            owner, repo = parsed
            return f"{owner}/{repo}"

        return None

    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


@app.command()
def install(
    all: bool = typer.Option(False, "--all", help="Install all categories"),
    category: Optional[list[str]] = typer.Option(None, "--category", "-c", help="Select specific categories"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without making changes"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompts"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output"),
):
    """Install Claude Code configuration.

    By default, runs in interactive mode with category selection.
    Use --all to install everything without prompting.
    """
    show_banner(__version__)

    try:
        registry, backup_mgr, version_mgr, plugin_mgr, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    # Determine which categories to install
    if all:
        selected_categories = [cat.name for cat in registry.get_all()]
    elif category:
        selected_categories = category
    else:
        # Interactive mode
        categories = registry.get_all()
        show_categories(categories)

        choices = [
            {
                "name": f"{cat.name:12} - {cat.description} ({len(cat.files)} files)",
                "value": cat.name,
                "checked": True,  # All checked by default
            }
            for cat in categories
        ]

        selected_categories = questionary.checkbox(
            "Select categories to install:",
            choices=choices,
        ).ask()

        if not selected_categories:
            print_warning("No categories selected. Exiting.")
            raise typer.Exit(0)

    # Compute installation plan
    try:
        plan = installer.compute_plan(selected_categories)
    except InstallationError as e:
        print_error(f"Installation failed: {escape(str(e))}")
        raise typer.Exit(1)

    # Show plan
    print_info("Installation plan:")
    show_install_plan(plan)

    # Check if any changes needed
    total_changes = len(plan["New"]) + len(plan["Updated"]) + len(plan["Merge"]) + len(plan.get("Archive", []))
    if total_changes == 0:
        print_success("All files are up to date. No changes needed.")
        raise typer.Exit(0)

    # Confirm unless force or dry-run
    if not dry_run and not force:
        if not confirm(f"Apply {total_changes} change(s)?"):
            print_warning("Installation cancelled.")
            raise typer.Exit(0)

    # Perform installation
    if dry_run:
        print_info("Dry run complete. No changes made.")
        raise typer.Exit(0)

    try:
        result = installer.install(selected_categories, dry_run=False, force=force)
        show_summary(result)
        print_success("Installation complete!")

    except InstallationError as e:
        print_error(f"Installation failed: {escape(str(e))}")
        raise typer.Exit(1)


@app.command()
def rollback(
    backup_id: Optional[str] = typer.Argument(None, help="Backup ID to restore (default: most recent)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be restored"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompt"),
):
    """Restore configuration from a backup."""
    show_banner(__version__)

    try:
        _, backup_mgr, _, _, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    # List available backups
    backups = backup_mgr.list_backups()
    if not backups:
        print_error("No backups available")
        raise typer.Exit(1)

    show_backup_list(backups)

    # Determine which backup to restore
    if backup_id is None:
        valid = [b for b in backups if not b.get("invalid")]
        if not valid:
            print_error("No valid backups available")
            raise typer.Exit(1)
        backup_id = valid[0]["id"]
        print_info(f"Using most recent backup: {backup_id}")

    # Verify backup exists (a single name inside the backups folder)
    try:
        backup_path = backup_mgr.resolve_backup(backup_id)
    except FileNotFoundError:
        print_error(f"Backup not found: {escape(str(backup_id))}")
        raise typer.Exit(1)

    # Confirm
    if not dry_run and not force:
        if not confirm(f"Restore from backup {backup_id}?"):
            print_warning("Rollback cancelled.")
            raise typer.Exit(0)

    if dry_run:
        print_info(f"Would restore from: {escape(str(backup_path))}")
        archive_dir = backup_mgr.get_archive_dir(backup_id)
        if archive_dir is not None:
            print_info(
                f"Would move archived retired paths back from: {escape(str(archive_dir))} "
                "(only where the path is free)"
            )
        raise typer.Exit(0)

    # Perform rollback
    try:
        restored_path = backup_mgr.restore_backup(backup_id, managed_files=installer.managed_relpaths())
        print_success(f"Configuration restored from {escape(restored_path.name)}")
        show_restore_result(backup_mgr.last_archive_restore, backup_mgr.last_restore_skipped)
    except (FileNotFoundError, BackupError) as e:
        print_error(escape(str(e)))
        raise typer.Exit(1)


@app.command()
def status():
    """Show installation status and check for updates."""
    show_banner(__version__)

    try:
        _, _, version_mgr, _, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    installed = version_mgr.get_installed()
    available = version_mgr.get_available()

    show_status(
        installed,
        available,
        retired_present=installer.get_retired_present(),
        archives=installer.archive_mgr.list_runs(),
    )


@app.command()
def backups(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of backups to show"),
    clean: bool = typer.Option(False, "--clean", help="Remove old backups"),
    keep: int = typer.Option(5, "--keep", help="Number of backups to keep when cleaning"),
):
    """List and manage configuration backups."""
    show_banner(__version__)

    try:
        _, backup_mgr, _, _, _ = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    if clean:
        deleted = backup_mgr.clean_old_backups(keep=keep)
        print_success(f"Deleted {deleted} old backup(s), kept {keep} most recent")
        return

    backups_list = backup_mgr.list_backups()
    if limit:
        backups_list = backups_list[:limit]

    show_backup_list(backups_list)


@app.command()
def plugins(
    install: bool = typer.Option(False, "--install", help="Install missing plugins"),
    check: bool = typer.Option(True, "--check/--no-check", help="Check installation status"),
    update_plugins: bool = typer.Option(
        False,
        "--update",
        help="Refresh team marketplaces, install missing and update installed required plugins",
    ),
):
    """Check, install and update required plugins."""
    show_banner(__version__)

    try:
        _, _, _, plugin_mgr, _ = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    for warning in plugin_mgr.get_warnings():
        print_warning(warning)

    if update_plugins:
        sync_plugins(plugin_mgr)
        return

    if check:
        status_dict = plugin_mgr.check_installed()
        missing = plugin_mgr.get_missing_plugins()

        console.print("\n[bold]Plugin Status:[/bold]")
        for plugin_name, is_installed in status_dict.items():
            status = "[green]✓ Installed[/green]" if is_installed else "[red]✗ Not installed[/red]"
            console.print(f"  {plugin_name}: {status}")

        if missing:
            console.print("\n[bold yellow]Missing Plugins:[/bold yellow]")
            for plugin in missing:
                console.print(f"  • {plugin['name']}: {plugin['description']}")

            console.print("\n[bold]Install commands:[/bold]")
            for cmd in plugin_mgr.get_install_commands():
                console.print(f"  {cmd}")

            if not install:
                console.print("\nRun [cyan]claude-setup plugins --install[/cyan] to install missing plugins")
        else:
            print_success("All required plugins are installed")

    if install:
        missing = plugin_mgr.get_missing_plugins()
        if not missing:
            print_info("All plugins already installed")
            return

        console.print(f"\n[bold]Installing {len(missing)} plugin(s)...[/bold]")

        marketplace_results: dict[str, tuple[bool, str]] = {}
        results = plugin_mgr.install_all_missing(marketplace_results)
        _print_results(
            {k: v for k, v in marketplace_results.items() if v[1] != "already known"},
            "Added marketplace",
            "Failed to add marketplace",
        )
        _print_results(results, "Installed", "Failed to install")


@app.command()
def update(
    check: bool = typer.Option(False, "--check", help="Check for updates only"),
    skip_plugins: bool = typer.Option(
        False,
        "--skip-plugins",
        help="Do not refresh marketplaces or install/update required plugins",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        "--force",
        help="Archive retired paths without asking for confirmation",
    ),
):
    """Check for and install updates.

    Retired paths listed in the manifest are moved (never deleted) into
    ~/.claude/archived/<timestamp>/ after confirmation (or with --yes).
    Declining cancels the whole update (exit 0, nothing changed); Ctrl-C
    aborts with exit code 130.

    After the configuration files are updated (or found up to date), team
    marketplaces are refreshed, missing required plugins are installed and
    installed required plugins are updated. Plugin failures are reported but
    do not fail the command. Use --skip-plugins to skip the plugin steps.
    """
    show_banner(__version__)

    try:
        registry, _, version_mgr, plugin_mgr, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    has_updates = version_mgr.has_updates()
    retired_present = installer.get_retired_present()

    if check:
        if has_updates:
            print_warning("Updates are available. Run 'claude-setup update' to install.")
        else:
            print_success("Configuration is up to date")
        if retired_present:
            print_warning(f"{len(retired_present)} retired path(s) still present (would be archived by 'update'):")
            for path in retired_present:
                console.print(f"  • {escape(str(path))}")
        raise typer.Exit(0)

    # Get previously installed categories
    installed = version_mgr.get_installed()
    categories = installed.get("categories", [])

    if not has_updates and not retired_present:
        print_success("Configuration is already up to date")
    else:
        if has_updates:
            print_info("Updates available. Re-running installation...")
        else:
            print_info(f"{len(retired_present)} retired path(s) still present. Re-running installation...")

        if not categories:
            print_warning("No previous installation found. Use 'claude-setup install' instead.")
            raise typer.Exit(0)

        try:
            archive_retired = _confirm_archive(installer, categories, assume_yes=yes)
        except KeyboardInterrupt:
            print_warning("Update aborted. Nothing was changed.")
            raise typer.Exit(130)
        except InstallationError as e:
            print_error(f"Update failed: {escape(str(e))}")
            raise typer.Exit(1)

        if not archive_retired:
            # Declining (or EOF) cancels the whole update: no install, backup,
            # settings merge, version stamp or plugin steps.
            print_warning("Update cancelled; nothing changed.")
            raise typer.Exit(0)

        # Re-install with same categories
        try:
            result = installer.install(categories, dry_run=False, force=False)
            show_summary(result)
            print_success("Update complete!")
        except InstallationError as e:
            print_error(f"Update failed: {escape(str(e))}")
            raise typer.Exit(1)
        except KeyboardInterrupt:
            print_warning(
                "Update interrupted. Anything already moved is recorded in ~/.claude/archived/; "
                "run 'claude-setup rollback' to undo."
            )
            raise typer.Exit(130)

    _maybe_sync_plugins(plugin_mgr, categories, skip_plugins)


def _confirm_archive(installer: Installer, categories: list[str], assume_yes: bool) -> bool:
    """Show retired paths that would be archived and ask before moving them.

    Returns True to go ahead (also when there is nothing to archive). False
    means the user declined (or EOF / no answer available): callers cancel
    the whole update.

    Raises:
        KeyboardInterrupt: Ctrl-C aborts; callers stop without installing.
        InstallationError: the manifest is malformed.
    """
    plan = installer.compute_plan(categories)
    items = plan.get("Archive", [])
    for entry, reason in plan.get("Refused", []):
        print_warning(f"Ignored retired entry {escape(repr(entry))}: {escape(str(reason))}")
    if not items:
        return True

    show_archive_plan(items)
    if assume_yes:
        return True
    try:
        answer = confirm(f"Move {len(items)} retired path(s) into the archive?")
    except EOFError:
        answer = False
    return bool(answer)


def _maybe_sync_plugins(plugin_mgr: PluginManager, categories: list[str], skip: bool) -> None:
    """Run the plugin sync after an update unless it is skipped or not applicable."""
    if skip:
        print_info("Skipping plugin steps (--skip-plugins)")
        return
    if "plugins" not in categories:
        print_info("The 'plugins' category is not installed; skipping plugin steps")
        return
    sync_plugins(plugin_mgr)


@app.command()
def upgrade(
    check: bool = typer.Option(False, "--check", help="Check if upgrade is available"),
):
    """Upgrade claude-setup tool to the latest version.

    This upgrades the tool itself (not the config). For config updates, use 'update'.
    """
    import subprocess
    import sys

    show_banner(__version__)

    # Get the installation directory
    tool_dir = get_tool_dir()

    # Check if this is a git repository
    git_dir = tool_dir / ".git"
    if not git_dir.exists():
        print_error("This installation is not from git.")
        console.print("\n[yellow]To upgrade:[/yellow]")
        console.print("  If installed via pip: [cyan]pip install --upgrade claude-setup[/cyan]")
        console.print("  If from source: Clone the repo and reinstall")
        raise typer.Exit(1)

    print_info("Checking for updates...")

    # Fetch latest from remote
    try:
        subprocess.run(
            ["git", "-C", str(tool_dir), "fetch", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to fetch updates: {e.stderr}")
        raise typer.Exit(1)

    # Check if updates are available
    try:
        result = subprocess.run(
            ["git", "-C", str(tool_dir), "rev-list", "HEAD...origin/main", "--count"],
            check=True,
            capture_output=True,
            text=True,
        )
        commits_behind = int(result.stdout.strip())
    except subprocess.CalledProcessError:
        # Try master branch if main doesn't exist
        try:
            result = subprocess.run(
                ["git", "-C", str(tool_dir), "rev-list", "HEAD...origin/master", "--count"],
                check=True,
                capture_output=True,
                text=True,
            )
            commits_behind = int(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to check for updates: {e.stderr}")
            raise typer.Exit(1)

    if commits_behind == 0:
        print_success("You're already on the latest version!")
        raise typer.Exit(0)

    console.print(f"\n[yellow]→[/yellow] {commits_behind} update(s) available")

    if check:
        console.print("\n[dim]Run without --check to upgrade[/dim]")
        raise typer.Exit(0)

    # Confirm upgrade
    if not confirm(f"Upgrade to latest version?"):
        print_warning("Upgrade cancelled.")
        raise typer.Exit(0)

    print_info("Upgrading tool...")

    # Check for uncommitted changes
    try:
        result = subprocess.run(
            ["git", "-C", str(tool_dir), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            print_warning("You have uncommitted changes. Creating backup...")
            # Stash changes
            subprocess.run(
                ["git", "-C", str(tool_dir), "stash", "push", "-m", "claude-setup auto-upgrade"],
                check=True,
                capture_output=True,
            )
            console.print("[dim]Changes stashed. Run 'git stash pop' to restore.[/dim]")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to check git status: {e.stderr}")
        raise typer.Exit(1)

    # Pull latest changes
    try:
        subprocess.run(
            ["git", "-C", str(tool_dir), "pull", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
        print_success("Downloaded latest version")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to pull updates: {e.stderr}")
        raise typer.Exit(1)

    # Reinstall package
    print_info("Reinstalling package...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(tool_dir), "--quiet"],
            check=True,
            capture_output=True,
            text=True,
        )
        print_success("Package reinstalled")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to reinstall: {e.stderr}")
        raise typer.Exit(1)

    # Show new version
    try:
        result = subprocess.run(
            [sys.executable, "-m", "claude_setup", "version"],
            check=True,
            capture_output=True,
            text=True,
        )
        console.print(f"\n[green]✓[/green] Upgrade complete! {result.stdout.strip()}")
    except subprocess.CalledProcessError:
        print_success("Upgrade complete!")

    console.print("\n[dim]Note: Config updates use 'claude-setup update', not 'upgrade'[/dim]")


@app.command()
def version():
    """Show version information."""
    console.print(f"[bold cyan]claude-setup[/bold cyan] version [yellow]{__version__}[/yellow]")


def interactive_admin_menu():
    """Show admin/advanced tools submenu."""
    console.clear()
    show_banner(__version__)
    console.print("\n[bold cyan]Advanced/Admin Tools[/bold cyan]")
    console.print("[dim]These tools are for creating and managing configuration repositories.[/dim]\n")

    while True:
        try:
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    questionary.Choice("🏗️ Create Config Repo (for sharing)", value="create-config"),
                    questionary.Choice("⬅️ Back to Main Menu", value="back"),
                ],
            ).ask()

            if choice is None or choice == "back":
                return

            console.print()  # Add spacing

            if choice == "create-config":
                interactive_create_config()

            # Pause before showing menu again
            console.print()
            questionary.press_any_key_to_continue("Press any key to return to menu...").ask()
            console.clear()
            show_banner(__version__)
            console.print("\n[bold cyan]Advanced/Admin Tools[/bold cyan]")
            console.print("[dim]These tools are for creating and managing configuration repositories.[/dim]\n")

        except KeyboardInterrupt:
            return
        except Exception as e:
            print_error(f"An error occurred: {e}")
            questionary.press_any_key_to_continue("Press any key to continue...").ask()


def interactive_menu():
    """Show interactive menu for navigating commands."""
    show_banner(__version__)

    while True:
        try:
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    questionary.Choice("⚙️ Setup Configuration", value="init"),
                    questionary.Choice("📦 Install Configuration", value="install"),
                    questionary.Choice("📊 Check Installation Status", value="status"),
                    questionary.Choice("🔌 Manage Plugins", value="plugins"),
                    questionary.Choice("💾 View Backups", value="backups"),
                    questionary.Choice("⏮️ Rollback to Backup", value="rollback"),
                    questionary.Choice("🔄 Check for Updates", value="update"),
                    questionary.Choice("🔧 Advanced/Admin Tools", value="admin"),
                    questionary.Choice("🚪 Exit", value="exit"),
                ],
            ).ask()

            if choice is None or choice == "exit":
                console.print("\n[dim]Goodbye! 👋[/dim]\n")
                break

            console.print()  # Add spacing

            if choice == "init":
                interactive_init_wizard()
            elif choice == "install":
                interactive_install()
            elif choice == "status":
                status()
            elif choice == "plugins":
                interactive_plugins()
            elif choice == "backups":
                interactive_backups()
            elif choice == "rollback":
                interactive_rollback()
            elif choice == "update":
                interactive_update()
            elif choice == "admin":
                interactive_admin_menu()
                # Clear and show main banner again after returning from admin menu
                console.clear()
                show_banner(__version__)
                continue  # Skip the press any key prompt

            # Pause before showing menu again
            console.print()
            questionary.press_any_key_to_continue("Press any key to return to menu...").ask()
            console.clear()
            show_banner(__version__)

        except KeyboardInterrupt:
            console.print("\n\n[dim]Goodbye! 👋[/dim]\n")
            break
        except Exception as e:
            print_error(f"An error occurred: {e}")
            questionary.press_any_key_to_continue("Press any key to continue...").ask()


def interactive_install():
    """Interactive installation flow."""
    try:
        registry, backup_mgr, version_mgr, plugin_mgr, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        return

    # Ask installation mode
    mode = questionary.select(
        "How would you like to install?",
        choices=[
            questionary.Choice("🎯 Select categories (recommended)", value="select"),
            questionary.Choice("📦 Install everything", value="all"),
            questionary.Choice("👁️  Preview changes only (dry run)", value="dry-run"),
            questionary.Choice("⬅️  Back to menu", value="back"),
        ],
    ).ask()

    if mode is None or mode == "back":
        return

    if mode == "dry-run":
        # Show dry run
        plan = installer.compute_plan([cat.name for cat in registry.get_all()])
        print_info("Installation plan (no changes will be made):")
        show_install_plan(plan)
        return

    # Determine categories
    if mode == "all":
        selected_categories = [cat.name for cat in registry.get_all()]
    else:
        # Interactive category selection
        categories = registry.get_all()
        show_categories(categories)

        choices = [
            {
                "name": f"{cat.name:12} - {cat.description} ({len(cat.files)} files)",
                "value": cat.name,
                "checked": True,
            }
            for cat in categories
        ]

        selected_categories = questionary.checkbox(
            "Select categories to install:",
            choices=choices,
        ).ask()

        if not selected_categories:
            print_warning("No categories selected.")
            return

    # Compute plan
    plan = installer.compute_plan(selected_categories)
    print_info("Installation plan:")
    show_install_plan(plan)

    # Check if changes needed
    total_changes = len(plan["New"]) + len(plan["Updated"]) + len(plan["Merge"]) + len(plan.get("Archive", []))
    if total_changes == 0:
        print_success("All files are up to date. No changes needed.")
        return

    # Confirm
    if not confirm(f"Apply {total_changes} change(s)?"):
        print_warning("Installation cancelled.")
        return

    # Install
    try:
        result = installer.install(selected_categories, dry_run=False, force=False)
        show_summary(result)
        print_success("Installation complete!")
    except InstallationError as e:
        print_error(f"Installation failed: {escape(str(e))}")


def interactive_plugins():
    """Interactive plugin management."""
    try:
        _, _, _, plugin_mgr, _ = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        return

    status_dict = plugin_mgr.check_installed()
    missing = plugin_mgr.get_missing_plugins()

    console.print("\n[bold]Plugin Status:[/bold]")
    for plugin_name, is_installed in status_dict.items():
        status = "[green]✓ Installed[/green]" if is_installed else "[red]✗ Not installed[/red]"
        console.print(f"  {plugin_name}: {status}")

    if missing:
        console.print("\n[bold yellow]Missing Plugins:[/bold yellow]")
        for plugin in missing:
            console.print(f"  • {plugin['name']}: {plugin['description']}")

        console.print("\n[bold]Install commands:[/bold]")
        for cmd in plugin_mgr.get_install_commands():
            console.print(f"  {cmd}")

        # Ask if they want to install
        if questionary.confirm("Install missing plugins now?", default=True).ask():
            console.print(f"\n[bold]Installing {len(missing)} plugin(s)...[/bold]")
            marketplace_results: dict[str, tuple[bool, str]] = {}
            results = plugin_mgr.install_all_missing(marketplace_results)
            _print_results(
                {k: v for k, v in marketplace_results.items() if v[1] != "already known"},
                "Added marketplace",
                "Failed to add marketplace",
            )
            _print_results(results, "Installed", "Failed to install")
    else:
        print_success("All required plugins are installed")
        if questionary.confirm("Refresh team marketplaces and update required plugins now?", default=False).ask():
            sync_plugins(plugin_mgr)


def interactive_backups():
    """Interactive backup management."""
    try:
        _, backup_mgr, _, _, _ = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        return

    action = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("📋 List all backups", value="list"),
            questionary.Choice("🧹 Clean old backups", value="clean"),
            questionary.Choice("⬅️  Back", value="back"),
        ],
    ).ask()

    if action is None or action == "back":
        return

    if action == "list":
        backups_list = backup_mgr.list_backups()
        show_backup_list(backups_list)

    elif action == "clean":
        keep = questionary.text(
            "How many recent backups to keep?",
            default="5",
            validate=lambda x: x.isdigit() and int(x) > 0,
        ).ask()

        if keep is None:
            return

        keep = int(keep)

        if questionary.confirm(f"Delete all backups except the {keep} most recent?", default=False).ask():
            deleted = backup_mgr.clean_old_backups(keep=keep)
            print_success(f"Deleted {deleted} old backup(s), kept {keep} most recent")


def interactive_rollback():
    """Interactive rollback."""
    try:
        _, backup_mgr, _, _, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        return

    backups = backup_mgr.list_backups()
    if not backups:
        print_error("No backups available")
        return

    show_backup_list(backups)

    # Ask which backup to restore
    choices = [
        questionary.Choice(
            f"{b['id']} - {b['created'] if isinstance(b['created'], str) else 'Legacy backup'} ({b['file_count']} files)",
            value=b['id']
        )
        for b in backups
    ]
    choices.append(questionary.Choice("⬅️  Cancel", value=None))

    backup_id = questionary.select(
        "Select backup to restore:",
        choices=choices,
    ).ask()

    if backup_id is None:
        print_warning("Rollback cancelled.")
        return

    # Confirm
    if not confirm(f"Restore from backup {backup_id}?"):
        print_warning("Rollback cancelled.")
        return

    # Perform rollback
    try:
        restored_path = backup_mgr.restore_backup(backup_id, managed_files=installer.managed_relpaths())
        print_success(f"Configuration restored from {escape(restored_path.name)}")
        show_restore_result(backup_mgr.last_archive_restore, backup_mgr.last_restore_skipped)
    except (FileNotFoundError, BackupError) as e:
        print_error(escape(str(e)))


def interactive_update():
    """Interactive update check and install."""
    try:
        registry, _, version_mgr, plugin_mgr, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        return

    has_updates = version_mgr.has_updates() or bool(installer.get_retired_present())

    if not has_updates:
        print_success("Configuration is already up to date")
        categories = version_mgr.get_installed().get("categories", [])
        if "plugins" in categories and plugin_mgr.required_plugins:
            if questionary.confirm("Refresh team marketplaces and update required plugins?", default=True).ask():
                sync_plugins(plugin_mgr)
        return

    print_info("Updates are available!")

    installed = version_mgr.get_installed()
    available = version_mgr.get_available()
    show_status(
        installed,
        available,
        retired_present=installer.get_retired_present(),
        archives=installer.archive_mgr.list_runs(),
    )

    if not questionary.confirm("Install updates now?", default=True).ask():
        print_info("Update cancelled. Run 'claude-setup update' later to install.")
        return

    # Get previously installed categories
    categories = installed.get("categories", [])
    if not categories:
        print_warning("No previous installation found. Use 'Install Configuration' instead.")
        return

    try:
        archive_retired = _confirm_archive(installer, categories, assume_yes=False)
    except KeyboardInterrupt:
        print_warning("Update aborted. Nothing was changed.")
        return
    except InstallationError as e:
        print_error(f"Update failed: {escape(str(e))}")
        return

    if not archive_retired:
        print_warning("Update cancelled; nothing changed.")
        return

    # Re-install with same categories
    try:
        result = installer.install(categories, dry_run=False, force=False)
        show_summary(result)
        print_success("Update complete!")
    except InstallationError as e:
        print_error(f"Update failed: {escape(str(e))}")
        return

    _maybe_sync_plugins(plugin_mgr, categories, skip=False)


def interactive_create_config(show_next_steps: bool = True) -> Optional[Path]:
    """Interactive config repository creation wizard.

    Args:
        show_next_steps: Whether to display next steps after generation

    Returns:
        Path to generated config directory on success, None on cancel/failure
    """
    # Step 1: Verify ~/.claude exists
    claude_dir = get_claude_dir()
    if not claude_dir.exists():
        print_error(f"Directory {claude_dir} does not exist")
        console.print("\n[bold]This wizard requires an existing ~/.claude directory.[/bold]")
        console.print("Run [cyan]Install Configuration[/cyan] first to set up your configuration.\n")
        return None

    # Step 2: Create backup first
    try:
        backup_mgr = BackupManager(claude_dir)
        print_info("Creating safety backup of ~/.claude...")

        # Collect all files in ~/.claude for backup
        files_to_backup = []
        for item in claude_dir.rglob("*"):
            if item.is_file():
                # Skip the backups directory itself
                try:
                    rel = item.relative_to(claude_dir)
                    if "backups" not in rel.parts:
                        files_to_backup.append(item)
                except ValueError:
                    continue

        # Create backup with a special category marker
        backup_path = backup_mgr.create_backup(files_to_backup, ["pre-create-config-wizard"])
        print_success(f"Backup created: {backup_path.name}")
    except Exception as e:
        print_warning(f"Could not create backup: {e}")
        if not questionary.confirm("Continue without backup?", default=False).ask():
            return None

    # Step 3: Scan ~/.claude
    try:
        print_info("Scanning ~/.claude directory...")
        scan_result = scan_claude_dir(claude_dir)
        console.print()
        show_scan_results(scan_result)
        console.print()
    except Exception as e:
        print_error(f"Failed to scan {claude_dir}: {e}")
        return None

    # Step 4: Category selection
    categories = ["core", "agents", "rules", "commands"]
    selected_categories = questionary.checkbox(
        "Select categories to include:",
        choices=[
            {"name": cat, "value": cat, "checked": True}
            for cat in categories
        ],
    ).ask()

    if selected_categories is None:
        print_warning("Cancelled.")
        return None

    if not selected_categories:
        print_warning("No categories selected.")
        return None

    # Filter files by selected categories
    selected_files = [
        f for f in scan_result.files
        if f.category in selected_categories
    ]

    # Step 5: Settings.json handling (if core selected)
    settings = None
    if "core" in selected_categories and scan_result.settings:
        console.print("\n[bold cyan]Settings.json Configuration[/bold cyan]")
        console.print()

        # Show team vs personal split using Panels
        from rich.panel import Panel

        team_fields = list(scan_result.settings.team_fields.keys())
        personal_fields = list(scan_result.settings.personal_fields.keys())

        team_text = "\n".join(f"  • {field}" for field in team_fields)
        personal_text = "\n".join(f"  • {field}" for field in personal_fields)

        console.print(Panel(
            f"[bold]Team Fields[/bold] (included in config):\n{team_text}",
            border_style="green",
            padding=(1, 2),
        ))
        console.print()
        console.print(Panel(
            f"[bold]Personal Fields[/bold] (excluded):\n{personal_text}",
            border_style="dim",
            padding=(1, 2),
        ))
        console.print()

        # Optional: edit permissions.allow
        if "permissions" in scan_result.settings.team_fields:
            current_allow = scan_result.settings.team_fields["permissions"].get("allow", [])
            if questionary.confirm("Edit permissions.allow list?", default=False).ask():
                selected_allow = questionary.checkbox(
                    "Select allowed permissions:",
                    choices=[
                        {"name": perm, "value": perm, "checked": True}
                        for perm in current_allow
                    ],
                ).ask()
                if selected_allow is not None:
                    custom_allow = selected_allow
                else:
                    custom_allow = current_allow
            else:
                custom_allow = current_allow
        else:
            custom_allow = None

        # Optional: edit enabledPlugins
        custom_plugins = None
        if "enabledPlugins" in scan_result.settings.team_fields:
            current_plugins = scan_result.settings.team_fields["enabledPlugins"]
            if questionary.confirm("Edit enabled plugins?", default=False).ask():
                # For plugins, we can't easily use checkbox (it's a dict)
                # Just ask if they want to keep it
                if not questionary.confirm("Keep current plugin configuration?", default=True).ask():
                    custom_plugins = {}
                else:
                    custom_plugins = current_plugins
            else:
                custom_plugins = current_plugins

        # Filter settings
        settings = filter_settings_for_team(
            scan_result.settings,
            custom_allow=custom_allow,
            custom_plugins=custom_plugins,
        )

    # Step 6: Plugins handling
    plugins = scan_result.plugins
    if plugins:
        console.print(f"\n[cyan]ℹ[/cyan] Found {len(plugins)} installed plugins")
        if questionary.confirm("Include all plugins in config?", default=True).ask():
            # Optional: edit plugin list
            if questionary.confirm("Edit plugin list?", default=False).ask():
                selected_plugins = questionary.checkbox(
                    "Select plugins to include:",
                    choices=[
                        {"name": p["name"], "value": p, "checked": True}
                        for p in plugins
                    ],
                ).ask()
                if selected_plugins is not None:
                    plugins = selected_plugins
        else:
            plugins = []

    # Step 7: Output directory
    console.print()
    default_output = str(Path.home() / "claude-config")
    output_dir_str = questionary.path(
        "Output directory:",
        default=default_output,
    ).ask()

    if output_dir_str is None:
        print_warning("Cancelled.")
        return None

    output_dir = Path(output_dir_str).expanduser()

    # Step 8: Overwrite check
    force = False
    if output_dir.exists() and any(output_dir.iterdir()):
        print_warning(f"Directory {output_dir} already exists and is not empty")

        # List first 10 files
        existing_files = list(output_dir.rglob("*"))[:10]
        console.print("\n[bold]Existing files:[/bold]")
        for f in existing_files:
            if f.is_file():
                rel = f.relative_to(output_dir)
                console.print(f"  • {rel}")

        remaining = len(list(output_dir.rglob("*"))) - 10
        if remaining > 0:
            console.print(f"  [dim]... and {remaining} more[/dim]")

        console.print()
        if not questionary.confirm("Overwrite existing directory?", default=False).ask():
            print_warning("Cancelled.")
            return None

        force = True

    # Step 9: Config name
    config_name = questionary.text(
        "Configuration name:",
        default="team-config",
    ).ask()

    if config_name is None:
        print_warning("Cancelled.")
        return None

    # Step 10: Git init
    init_git = questionary.confirm(
        "Initialize git repository?",
        default=True,
    ).ask()

    if init_git is None:
        init_git = True

    # Step 11: Build plan and preview
    plan = ConfigPlan(
        output_dir=output_dir,
        selected_files=selected_files,
        settings=settings,
        plugins=plugins,
        init_git=init_git,
        config_name=config_name,
    )

    console.print()
    preview = preview_config_plan(plan)
    show_config_preview(preview)

    # Step 12: Final confirmation
    console.print()
    if not questionary.confirm("Generate config repository?", default=True).ask():
        print_warning("Cancelled.")
        return None

    # Step 13: Generate
    try:
        generated_path = generate_config_repo(plan, force=force)
        console.print()
        print_success(f"Config repository created at {generated_path}")

        # Step 14: Show next steps
        if show_next_steps:
            console.print("\n[bold green]✓ Config repository created![/bold green]")
            console.print("\n[bold]Next steps:[/bold]")
            console.print(f"  1. Review the generated files in [cyan]{generated_path}[/cyan]")
            console.print("  2. Commit to git and push to GitHub:")
            console.print(f"     [dim]cd {generated_path}[/dim]")
            console.print(f"     [dim]git add .[/dim]")
            console.print(f"     [dim]git commit -m 'Initial config'[/dim]")
            console.print(f"     [dim]git remote add origin <your-repo-url>[/dim]")
            console.print(f"     [dim]git push -u origin main[/dim]")
            console.print("  3. Team members can install with:")
            console.print(f"     [cyan]claude-setup init --github your-org/repo-name[/cyan]")
            console.print(f"     [cyan]claude-setup install[/cyan]\n")

        return generated_path

    except Exception as e:
        print_error(f"Failed to generate config: {e}")
        return None


@app.command(name="create-config")
def create_config(
    output_dir: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory for config repo"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be generated without creating files"),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git init"),
    all_categories: bool = typer.Option(False, "--all", help="Include all categories without prompting"),
):
    """Create a new config repository from your current ~/.claude setup."""
    show_banner(__version__)

    # Get claude_dir
    claude_dir = get_claude_dir()

    # Verify ~/.claude exists
    if not claude_dir.exists():
        print_error(f"Directory {claude_dir} does not exist")
        console.print("\n[bold]This command requires an existing ~/.claude directory.[/bold]")
        console.print("Run [cyan]claude-setup install[/cyan] first to set up your configuration.\n")
        raise typer.Exit(1)

    # Scan ~/.claude
    try:
        scan_result = scan_claude_dir(claude_dir)
    except Exception as e:
        print_error(f"Failed to scan {claude_dir}: {e}")
        raise typer.Exit(1)

    # Select all files if --all flag
    selected_files = scan_result.files
    settings = None
    if scan_result.settings:
        settings = filter_settings_for_team(scan_result.settings)
    plugins = scan_result.plugins

    # Build plan
    output_path = Path(output_dir if output_dir else Path.home() / "claude-config")
    plan = ConfigPlan(
        output_dir=output_path,
        selected_files=selected_files,
        settings=settings,
        plugins=plugins,
        init_git=not no_git,
        config_name=output_path.name,
    )

    # Preview
    preview = preview_config_plan(plan)
    show_config_preview(preview)

    if dry_run:
        print_info("Dry run complete. No files created.")
        raise typer.Exit(0)

    # Confirm
    if not confirm(f"Generate config repo at {output_path}?"):
        print_warning("Cancelled.")
        raise typer.Exit(0)

    # Generate
    try:
        generated_path = generate_config_repo(plan)
        print_success(f"Config repository created at {generated_path}")

        # Show next steps
        console.print("\n[bold green]✓ Config repository created![/bold green]")
        console.print("\n[bold]Next steps:[/bold]")
        console.print(f"  1. Review the generated files in [cyan]{generated_path}[/cyan]")
        console.print("  2. Commit to git and push to GitHub")
        console.print("  3. Team members can install with:")
        console.print(f"     [cyan]claude-setup init --github your-org/repo-name[/cyan]")
        console.print(f"     [cyan]claude-setup install[/cyan]\n")

    except FileExistsError as e:
        print_error(str(e))
        console.print("\n[bold]To overwrite:[/bold]")
        console.print("  • Delete the directory and run again")
        console.print("  • Or use the interactive wizard for more control\n")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Failed to generate config: {e}")
        raise typer.Exit(1)


def _wizard_from_scratch() -> Optional[dict]:
    """Wizard: Create config from scratch using interactive_create_config.

    Returns:
        sources_config dict or None if cancelled
    """
    generated_path = interactive_create_config(show_next_steps=False)

    if generated_path is None:
        return None

    # Build sources config with local source
    sources_config = {
        "version": "1.0",
        "sources": [
            {
                "name": "local-config",
                "type": "local",
                "path": str(generated_path),
            }
        ],
    }

    return sources_config


def _wizard_from_zip() -> Optional[dict]:
    """Wizard: Extract and validate zip file as config source.

    Returns:
        sources_config dict or None if cancelled/failed
    """
    # Step 1: Ask for zip file path
    zip_path_str = questionary.path(
        "Path to zip file:",
        validate=lambda x: x.endswith(".zip"),
    ).ask()

    if zip_path_str is None:
        return None

    zip_path = Path(zip_path_str).expanduser()

    if not zip_path.exists():
        print_error(f"Zip file not found: {zip_path}")
        return None

    # Step 2: Ask for extraction location
    default_extract = str(Path.home() / ".claude" / "sources" / "config-from-zip")
    extract_path_str = questionary.path(
        "Extract to:",
        default=default_extract,
    ).ask()

    if extract_path_str is None:
        return None

    extract_path = Path(extract_path_str).expanduser()

    # Step 3: Extract zip file
    try:
        print_info(f"Extracting {zip_path.name}...")
        extract_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_path)

        # Handle single top-level directory (mirror ZipSource logic)
        items = list(extract_path.iterdir())
        if len(items) == 1 and items[0].is_dir():
            temp_dir = extract_path.parent / f"{extract_path.name}_temp"
            items[0].rename(temp_dir)
            shutil.rmtree(extract_path)
            temp_dir.rename(extract_path)

        print_success(f"Extracted to {extract_path}")

    except zipfile.BadZipFile:
        print_error(f"Invalid zip file: {zip_path}")
        return None
    except Exception as e:
        print_error(f"Failed to extract zip: {e}")
        return None

    # Step 4: Validate extracted config
    from claude_setup.init import validate_config_source

    is_valid, message, resolved_path = validate_config_source(extract_path)

    if not is_valid:
        print_error(f"Invalid config source: {message}")
        # Clean up
        if extract_path.exists():
            shutil.rmtree(extract_path)
        return None

    # Use resolved path if manifest was found one level deep
    final_path = resolved_path if resolved_path else extract_path

    print_success(f"Valid config source: {message}")

    # Build sources config
    sources_config = {
        "version": "1.0",
        "sources": [
            {
                "name": "local-config",
                "type": "local",
                "path": str(final_path),
            }
        ],
    }

    return sources_config


def _wizard_git_clone() -> Optional[dict]:
    """Wizard: Clone a git repository and set up as source.

    Returns:
        sources_config dict or None if cancelled/failed
    """
    # Step 1: Ask for git URL
    git_url = questionary.text(
        "Git repository URL:",
        validate=lambda x: len(x) > 0,
    ).ask()

    if git_url is None:
        return None

    # Step 2: Ask for branch
    branch = questionary.text(
        "Branch or tag:",
        default="main",
    ).ask()

    if branch is None:
        branch = "main"

    # Step 3: Derive repo name and default location
    repo_name = git_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    # Check if it's a GitHub repo for informational message
    parsed = _parse_github_url(git_url)
    if parsed:
        owner, repo = parsed
        console.print(f"[dim]Detected GitHub repository: {owner}/{repo}[/dim]")
        if "GITHUB_TOKEN" in os.environ:
            console.print("[dim]Will use GITHUB_TOKEN for authentication[/dim]")

    # Step 4: Ask where to clone (for all repo types)
    default_dest = str(Path.home() / ".claude" / "sources" / repo_name)
    dest_path_str = questionary.path(
        "Clone to:",
        default=default_dest,
    ).ask()

    if dest_path_str is None:
        return None

    dest_path = Path(dest_path_str).expanduser()

    # Step 5: Clone the repository
    try:
        print_info(f"Cloning {git_url}...")
        subprocess.run(
            ["git", "clone", "-b", branch, git_url, str(dest_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        print_success(f"Cloned to {dest_path}")

    except subprocess.CalledProcessError as e:
        print_error(f"Git clone failed: {e.stderr}")
        return None
    except FileNotFoundError:
        print_error("git command not found. Please install git.")
        return None

    # Step 6: Validate
    from claude_setup.init import validate_config_source

    is_valid, message, resolved_path = validate_config_source(dest_path)

    if not is_valid:
        print_error(f"Invalid config source: {message}")
        return None

    final_path = resolved_path if resolved_path else dest_path
    print_success(f"Valid config source: {message}")

    # Step 7: Build local source (same for all repo types)
    sources_config = {
        "version": "1.0",
        "sources": [
            {
                "name": "local-config",
                "type": "local",
                "path": str(final_path),
            }
        ],
    }

    return sources_config


def _wizard_git_existing() -> Optional[dict]:
    """Wizard: Use an existing git repository on disk.

    Returns:
        sources_config dict or None if cancelled/failed
    """
    # Step 1: Ask for repo path
    repo_path_str = questionary.path(
        "Path to git repository:",
        only_directories=True,
    ).ask()

    if repo_path_str is None:
        return None

    repo_path = Path(repo_path_str).expanduser()

    # Step 2: Validate
    from claude_setup.init import validate_config_source

    is_valid, message, resolved_path = validate_config_source(repo_path)

    if not is_valid:
        print_error(f"Invalid config source: {message}")
        return None

    final_path = resolved_path if resolved_path else repo_path
    print_success(f"Valid config source: {message}")

    # Step 3: Detect GitHub remote (informational only)
    github_remote = _detect_github_remote(repo_path)

    if github_remote:
        console.print(f"[dim]Detected GitHub remote: {github_remote}[/dim]")
        if "GITHUB_TOKEN" in os.environ:
            console.print("[dim]GITHUB_TOKEN available for authenticated updates[/dim]")

    # Always use local source - updates will use git pull
    sources_config = {
        "version": "1.0",
        "sources": [
            {
                "name": "local-config",
                "type": "local",
                "path": str(final_path),
            }
        ],
    }

    return sources_config


def _wizard_from_git() -> Optional[dict]:
    """Wizard: Git repository flow - route to clone or existing.

    Returns:
        sources_config dict or None if cancelled
    """
    choice = questionary.select(
        "Is the repository already on your computer?",
        choices=[
            questionary.Choice("No, I need to clone it", value="clone"),
            questionary.Choice("Yes, it's already on disk", value="existing"),
        ],
    ).ask()

    if choice is None:
        return None

    if choice == "clone":
        return _wizard_git_clone()
    else:
        return _wizard_git_existing()


def _wizard_advanced() -> Optional[dict]:
    """Wizard: Copy custom sources.json file.

    Returns:
        Sentinel value (empty dict) to skip create_default_sources, or None if cancelled
    """
    path = questionary.path("Path to sources.json file:").ask()

    if path is None:
        return None

    source_path = Path(path)

    if not source_path.exists():
        print_error(f"File not found: {source_path}")
        return None

    claude_dir = get_claude_dir()
    dest_path = claude_dir / "sources.json"

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source_path, dest_path)
        print_success("Copied sources configuration")
        # Return empty dict as sentinel to indicate sources.json already written
        return {}
    except Exception as e:
        print_error(f"Failed to copy file: {e}")
        return None


def interactive_init_wizard():
    """Interactive init wizard with beginner-friendly options."""
    claude_dir = get_claude_dir()

    # Welcome message
    print_info("Welcome to Claude Setup! Let's configure your source.")
    console.print("\n[bold]How would you like to set up your configuration?[/bold]\n")

    # Step 1: Main choice
    choice = questionary.select(
        "Choose an option:",
        choices=[
            questionary.Choice("✨ Create a new config from scratch", value="scratch"),
            questionary.Choice("📦 Use a zip file with a pre-made config", value="zip"),
            questionary.Choice("📁 Use an existing git repository", value="git"),
            questionary.Choice("⚙️  Advanced: Custom sources.json", value="advanced"),
            questionary.Choice("⬅️  Cancel", value="cancel"),
        ],
    ).ask()

    if choice is None or choice == "cancel":
        print_warning("Initialization cancelled.")
        return

    # Step 2: Route to appropriate wizard
    sources_config = None

    if choice == "scratch":
        sources_config = _wizard_from_scratch()
    elif choice == "zip":
        sources_config = _wizard_from_zip()
    elif choice == "git":
        sources_config = _wizard_from_git()
    elif choice == "advanced":
        sources_config = _wizard_advanced()

    if sources_config is None:
        print_warning("Setup cancelled.")
        return

    # Step 3: Check if sources.json already exists
    sources_file = claude_dir / "sources.json"
    if sources_file.exists():
        print_warning(f"{sources_file} already exists")
        if not questionary.confirm("Overwrite existing sources.json?", default=False).ask():
            print_warning("Cancelled.")
            return

    # Step 4: Write sources.json (unless advanced already wrote it)
    if sources_config:  # Empty dict means advanced already wrote it
        from claude_setup.init import create_default_sources

        sources_file = create_default_sources(claude_dir, sources_config)
        print_success(f"Created sources configuration at {sources_file}")

    # Step 5: Show confirmation summary
    console.print("\n[bold green]✓ Sources configured![/bold green]\n")

    # Show source type and location
    if choice == "scratch":
        console.print("[bold]Source:[/bold] Local config (generated from your ~/.claude)")
    elif choice == "zip":
        console.print("[bold]Source:[/bold] Local config (extracted from zip)")
    elif choice == "git":
        if sources_config and sources_config.get("sources"):
            source = sources_config["sources"][0]
            if source["type"] == "github":
                console.print(f"[bold]Source:[/bold] GitHub repository [cyan]{source['repo']}[/cyan]")
            else:
                console.print(f"[bold]Source:[/bold] Local git repository")
    elif choice == "advanced":
        console.print("[bold]Source:[/bold] Custom sources.json")

    # Step 6: Show next steps
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Run: [cyan]claude-setup install[/cyan]")
    console.print("  2. Or: [cyan]claude-setup[/cyan] for interactive menu\n")


@app.command()
def init(
    source_file: Optional[str] = typer.Option(None, "--source", "-s", help="Path to sources.json file"),
    github_repo: Optional[str] = typer.Option(None, "--github", help="GitHub repo (owner/repo format)"),
    github_ref: Optional[str] = typer.Option("main", "--ref", help="GitHub branch/tag"),
    local_path: Optional[str] = typer.Option(None, "--local", help="Local config directory path"),
    zip_url: Optional[str] = typer.Option(None, "--zip", help="URL to zip file"),
):
    """Initialize configuration sources.

    Examples:
        claude-setup init --github your-org/claude-config
        claude-setup init --local ~/my-config
        claude-setup init --zip https://example.com/config.zip
        claude-setup init --source sources.json
    """
    show_banner(__version__)
    from claude_setup.init import create_default_sources

    claude_dir = get_claude_dir()
    sources_config = {"sources": []}

    if source_file:
        # Copy provided sources file
        import shutil

        source_path = Path(source_file)
        if not source_path.exists():
            print_error(f"Source file not found: {source_file}")
            raise typer.Exit(1)

        dest_path = claude_dir / "sources.json"
        shutil.copy(source_path, dest_path)
        print_success(f"Copied sources configuration to {dest_path}")

    elif github_repo:
        # Create GitHub source
        source_entry = {
            "name": "company-config",
            "type": "github",
            "repo": github_repo,
            "ref": github_ref,
        }

        # Auto-detect GITHUB_TOKEN for private repos
        import os
        if "GITHUB_TOKEN" in os.environ:
            source_entry["token"] = "${GITHUB_TOKEN}"
            console.print("[dim]Detected GITHUB_TOKEN environment variable[/dim]")

        sources_config["sources"].append(source_entry)
        sources_file = create_default_sources(claude_dir, sources_config)
        print_success(f"Created sources configuration at {sources_file}")
        console.print(f"\n[bold]Source:[/bold] GitHub repo [cyan]{github_repo}[/cyan] (ref: {github_ref})")

        if "token" in source_entry:
            console.print("[dim]Token will be read from $GITHUB_TOKEN environment variable[/dim]")

    elif local_path:
        # Create local source
        sources_config["sources"].append({
            "name": "local-config",
            "type": "local",
            "path": local_path,
        })
        sources_file = create_default_sources(claude_dir, sources_config)
        print_success(f"Created sources configuration at {sources_file}")
        console.print(f"\n[bold]Source:[/bold] Local path [cyan]{local_path}[/cyan]")

    elif zip_url:
        # Create zip source
        sources_config["sources"].append({
            "name": "company-config",
            "type": "zip",
            "url": zip_url,
        })
        sources_file = create_default_sources(claude_dir, sources_config)
        print_success(f"Created sources configuration at {sources_file}")
        console.print(f"\n[bold]Source:[/bold] Zip file [cyan]{zip_url}[/cyan]")

    else:
        # Interactive wizard
        interactive_init_wizard()
        return

    # Show next steps (only for CLI flag paths)
    console.print("\n[bold green]✓ Sources configured![/bold green]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Run: [cyan]claude-setup install[/cyan]")
    console.print("  2. Or: [cyan]claude-setup[/cyan] for interactive menu\n")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Claude Setup - Interactive CLI installer for Claude Code team configuration.

    Run without a command to start interactive menu.
    """
    if ctx.invoked_subcommand is None:
        # No subcommand provided, show interactive menu
        interactive_menu()


if __name__ == "__main__":
    app()
