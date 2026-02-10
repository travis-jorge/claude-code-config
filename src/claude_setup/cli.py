"""CLI interface using Typer."""

import json
from pathlib import Path
from typing import Optional

import questionary
import typer
from rich.console import Console

from claude_setup import __version__
from claude_setup.backup import BackupManager
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
    show_backup_list,
    show_banner,
    show_categories,
    show_config_preview,
    show_install_plan,
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

    # Load required plugins
    plugins_file = config_dir / "plugins" / "required.json"
    with open(plugins_file) as f:
        required_plugins = json.load(f)

    plugin_mgr = PluginManager(claude_dir, required_plugins)

    installer = Installer(config_dir, claude_dir, registry, backup_mgr, version_mgr)

    return registry, backup_mgr, version_mgr, plugin_mgr, installer


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
    plan = installer.compute_plan(selected_categories)

    # Show plan
    print_info("Installation plan:")
    show_install_plan(plan)

    # Check if any changes needed
    total_changes = len(plan["New"]) + len(plan["Updated"]) + len(plan["Merge"])
    if total_changes == 0:
        print_success("All files are up to date. No changes needed.")
        raise typer.Exit(0)

    # Confirm unless force or dry-run
    if not dry_run and not force:
        if not confirm(f"Install {total_changes} file(s)?"):
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
        print_error(f"Installation failed: {e}")
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
        _, backup_mgr, _, _, _ = initialize_managers()
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
        backup_id = backups[0]["id"]
        print_info(f"Using most recent backup: {backup_id}")

    # Verify backup exists
    backup_path = backup_mgr.backup_dir / backup_id
    if not backup_path.exists():
        print_error(f"Backup not found: {backup_id}")
        raise typer.Exit(1)

    # Confirm
    if not dry_run and not force:
        if not confirm(f"Restore from backup {backup_id}?"):
            print_warning("Rollback cancelled.")
            raise typer.Exit(0)

    if dry_run:
        print_info(f"Would restore from: {backup_path}")
        raise typer.Exit(0)

    # Perform rollback
    try:
        restored_path = backup_mgr.restore_backup(backup_id)
        print_success(f"Configuration restored from {restored_path.name}")
    except FileNotFoundError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command()
def status():
    """Show installation status and check for updates."""
    show_banner(__version__)

    try:
        _, _, version_mgr, _, _ = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    installed = version_mgr.get_installed()
    available = version_mgr.get_available()

    show_status(installed, available)


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
):
    """Check and install required plugins."""
    show_banner(__version__)

    try:
        _, _, _, plugin_mgr, _ = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

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

        results = plugin_mgr.install_all_missing()
        for plugin_name, (success, message) in results.items():
            if success:
                print_success(f"Installed {plugin_name}")
            else:
                print_error(f"Failed to install {plugin_name}: {message}")


@app.command()
def update(
    check: bool = typer.Option(False, "--check", help="Check for updates only"),
):
    """Check for and install updates."""
    show_banner(__version__)

    try:
        registry, _, version_mgr, _, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        raise typer.Exit(1)

    has_updates = version_mgr.has_updates()

    if check:
        if has_updates:
            print_warning("Updates are available. Run 'claude-setup update' to install.")
        else:
            print_success("Configuration is up to date")
        raise typer.Exit(0)

    if not has_updates:
        print_success("Configuration is already up to date")
        raise typer.Exit(0)

    print_info("Updates available. Re-running installation...")

    # Get previously installed categories
    installed = version_mgr.get_installed()
    categories = installed.get("categories", [])

    if not categories:
        print_warning("No previous installation found. Use 'claude-setup install' instead.")
        raise typer.Exit(0)

    # Re-install with same categories
    try:
        result = installer.install(categories, dry_run=False, force=False)
        show_summary(result)
        print_success("Update complete!")
    except InstallationError as e:
        print_error(f"Update failed: {e}")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    console.print(f"[bold cyan]claude-setup[/bold cyan] version [yellow]{__version__}[/yellow]")


def interactive_menu():
    """Show interactive menu for navigating commands."""
    show_banner(__version__)

    while True:
        try:
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    questionary.Choice("📦 Install Configuration", value="install"),
                    questionary.Choice("📊 Check Installation Status", value="status"),
                    questionary.Choice("🔌 Manage Plugins", value="plugins"),
                    questionary.Choice("💾 View Backups", value="backups"),
                    questionary.Choice("⏮️ Rollback to Backup", value="rollback"),
                    questionary.Choice("🔄 Check for Updates", value="update"),
                    questionary.Choice("🏗️ Create Config Repo", value="create-config"),
                    questionary.Choice("🚪 Exit", value="exit"),
                ],
            ).ask()

            if choice is None or choice == "exit":
                console.print("\n[dim]Goodbye! 👋[/dim]\n")
                break

            console.print()  # Add spacing

            if choice == "install":
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
            elif choice == "create-config":
                interactive_create_config()

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
    total_changes = len(plan["New"]) + len(plan["Updated"]) + len(plan["Merge"])
    if total_changes == 0:
        print_success("All files are up to date. No changes needed.")
        return

    # Confirm
    if not confirm(f"Install {total_changes} file(s)?"):
        print_warning("Installation cancelled.")
        return

    # Install
    try:
        result = installer.install(selected_categories, dry_run=False, force=False)
        show_summary(result)
        print_success("Installation complete!")
    except InstallationError as e:
        print_error(f"Installation failed: {e}")


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
            results = plugin_mgr.install_all_missing()

            for plugin_name, (success, message) in results.items():
                if success:
                    print_success(f"Installed {plugin_name}")
                else:
                    print_error(f"Failed to install {plugin_name}: {message}")
    else:
        print_success("All required plugins are installed")


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
        _, backup_mgr, _, _, _ = initialize_managers()
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
        restored_path = backup_mgr.restore_backup(backup_id)
        print_success(f"Configuration restored from {restored_path.name}")
    except FileNotFoundError as e:
        print_error(str(e))


def interactive_update():
    """Interactive update check and install."""
    try:
        registry, _, version_mgr, _, installer = initialize_managers()
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        return

    has_updates = version_mgr.has_updates()

    if not has_updates:
        print_success("Configuration is already up to date")
        return

    print_info("Updates are available!")

    installed = version_mgr.get_installed()
    available = version_mgr.get_available()
    show_status(installed, available)

    if not questionary.confirm("Install updates now?", default=True).ask():
        print_info("Update cancelled. Run 'claude-setup update' later to install.")
        return

    # Get previously installed categories
    categories = installed.get("categories", [])
    if not categories:
        print_warning("No previous installation found. Use 'Install Configuration' instead.")
        return

    # Re-install with same categories
    try:
        result = installer.install(categories, dry_run=False, force=False)
        show_summary(result)
        print_success("Update complete!")
    except InstallationError as e:
        print_error(f"Update failed: {e}")


def interactive_create_config():
    """Interactive config repository creation wizard."""
    # Step 1: Verify ~/.claude exists
    claude_dir = get_claude_dir()
    if not claude_dir.exists():
        print_error(f"Directory {claude_dir} does not exist")
        console.print("\n[bold]This wizard requires an existing ~/.claude directory.[/bold]")
        console.print("Run [cyan]Install Configuration[/cyan] first to set up your configuration.\n")
        return

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
            return

    # Step 3: Scan ~/.claude
    try:
        print_info("Scanning ~/.claude directory...")
        scan_result = scan_claude_dir(claude_dir)
        console.print()
        show_scan_results(scan_result)
        console.print()
    except Exception as e:
        print_error(f"Failed to scan {claude_dir}: {e}")
        return

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
        return

    if not selected_categories:
        print_warning("No categories selected.")
        return

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
        return

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
            return

        force = True

    # Step 9: Config name
    config_name = questionary.text(
        "Configuration name:",
        default="team-config",
    ).ask()

    if config_name is None:
        print_warning("Cancelled.")
        return

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
        return

    # Step 13: Generate
    try:
        generated_path = generate_config_repo(plan, force=force)
        console.print()
        print_success(f"Config repository created at {generated_path}")

        # Step 14: Show next steps
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

    except Exception as e:
        print_error(f"Failed to generate config: {e}")


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
        # Interactive setup
        print_info("No source specified. Let's set one up interactively!")

        choice = questionary.select(
            "How do you want to provide configuration?",
            choices=[
                questionary.Choice("📦 GitHub Repository", value="github"),
                questionary.Choice("📁 Local Directory", value="local"),
                questionary.Choice("📦 Zip File (URL)", value="zip"),
                questionary.Choice("📄 Custom sources.json", value="file"),
                questionary.Choice("⬅️  Cancel", value="cancel"),
            ],
        ).ask()

        if choice == "cancel" or choice is None:
            print_warning("Initialization cancelled.")
            return

        if choice == "github":
            repo = questionary.text(
                "GitHub repository (format: owner/repo):",
                validate=lambda x: "/" in x,
            ).ask()

            if repo is None:
                return

            ref = questionary.text("Branch or tag:", default="main").ask()

            source_entry = {
                "name": "company-config",
                "type": "github",
                "repo": repo,
                "ref": ref or "main",
            }

            # Auto-detect GITHUB_TOKEN for private repos
            import os
            if "GITHUB_TOKEN" in os.environ:
                source_entry["token"] = "${GITHUB_TOKEN}"
                console.print("[dim]Detected GITHUB_TOKEN environment variable[/dim]")

            sources_config["sources"].append(source_entry)

        elif choice == "local":
            path = questionary.path(
                "Path to local config directory:",
                only_directories=True,
            ).ask()

            if path is None:
                return

            sources_config["sources"].append({
                "name": "local-config",
                "type": "local",
                "path": path,
            })

        elif choice == "zip":
            url = questionary.text(
                "URL to zip file:",
                validate=lambda x: x.startswith("http"),
            ).ask()

            if url is None:
                return

            sources_config["sources"].append({
                "name": "company-config",
                "type": "zip",
                "url": url,
            })

        elif choice == "file":
            path = questionary.path("Path to sources.json file:").ask()

            if path is None:
                return

            import shutil

            source_path = Path(path)
            dest_path = claude_dir / "sources.json"
            shutil.copy(source_path, dest_path)
            print_success(f"Copied sources configuration")
            return

        sources_file = create_default_sources(claude_dir, sources_config)
        print_success(f"Created sources configuration at {sources_file}")

    # Show next steps
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
