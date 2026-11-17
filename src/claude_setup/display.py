"""Rich UI display helpers."""

from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.prompt import Confirm

console = Console()


def _e(value: Any) -> str:
    """Escape any value for safe inclusion in Rich markup (paths may contain '[')."""
    return escape(str(value))


def show_banner(version: str) -> None:
    """Show tool banner."""
    banner_text = f"""[bold cyan]Claude Setup[/bold cyan]
[dim]Interactive CLI installer for Claude Code team configuration[/dim]
[dim]Version {version}[/dim]"""

    console.print(Panel(banner_text, border_style="cyan", padding=(1, 2)))


def show_categories(categories: list[Any]) -> None:
    """Show available categories in a table."""
    table = Table(title="Available Categories", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Files", justify="right", style="yellow")

    for cat in categories:
        table.add_row(cat.name, cat.description, str(len(cat.files)))

    console.print(table)


def show_install_plan(plan: dict[str, list[tuple[Path, str]]]) -> None:
    """Show installation plan with file statuses."""
    table = Table(title="Installation Plan", show_header=True, header_style="bold cyan")
    table.add_column("File", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Action", style="cyan")

    status_colors = {
        "New": "green",
        "Updated": "yellow",
        "Unchanged": "dim",
        "Merge": "magenta",
        "Archive": "red",
        "Refused": "bold red",
    }

    for status, files in plan.items():
        for file_path, action in files:
            color = status_colors.get(status, "white")
            table.add_row(
                _e(file_path),
                f"[{color}]{_e(status)}[/{color}]",
                _e(action),
            )

    console.print(table)


def show_progress(total: int) -> Progress:
    """Create and return a progress bar."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )
    return progress


def show_summary(result: dict[str, Any]) -> None:
    """Show installation summary."""
    stats = result.get("stats", {})
    categories = result.get("categories", [])
    backup_path = result.get("backup_path", "")

    summary_text = f"""[bold green]✓ Installation Complete[/bold green]

[bold]Statistics:[/bold]
  • Files installed: [cyan]{stats.get('installed', 0)}[/cyan]
  • Files updated: [yellow]{stats.get('updated', 0)}[/yellow]
  • Files unchanged: [dim]{stats.get('unchanged', 0)}[/dim]
  • Settings merged: [magenta]{'Yes' if stats.get('merged', False) else 'No'}[/magenta]
  • Retired paths archived: [red]{stats.get('archived', 0)}[/red]

[bold]Categories installed:[/bold]
  {', '.join(categories)}

[bold]Backup location:[/bold]
  [dim]{backup_path}[/dim]

[bold]Next steps:[/bold]
  1. Run [cyan]claude-setup plugins[/cyan] to check plugin installation
  2. Restart Claude Code to load the new configuration
  3. Run [cyan]claude-setup status[/cyan] to verify installation
"""

    console.print(Panel(summary_text, border_style="green", padding=(1, 2)))

    show_retired_result(result.get("retired") or {})


def show_retired_result(retired: dict[str, Any]) -> None:
    """Report where retired paths were archived, and any problems."""
    archive_dir = retired.get("archive_dir")
    if archive_dir:
        console.print(f"\n[bold]Retired paths moved to[/bold] [cyan]{_e(archive_dir)}[/cyan]:")
        for original, archived in retired.get("archived", []):
            console.print(f"  • {_e(original)} → {_e(archived)}")
        console.print(
            "  [dim]Nothing was deleted. Run 'claude-setup rollback' to move them back, "
            "or delete this folder once you're happy.[/dim]"
        )
    for path, message in retired.get("failed", []):
        console.print(
            f"[bold red]✗[/bold red] Could not archive retired path {_e(path)}: {_e(message)} (left in place)"
        )
    for entry, reason in retired.get("refused", []):
        console.print(f"[bold yellow]⚠[/bold yellow] Ignored retired entry {_e(repr(entry))}: {_e(reason)}")
    if retired.get("skipped"):
        console.print("[yellow]Retired paths were left in place (archiving declined).[/yellow]")


def show_archive_plan(items: list[tuple[Any, str]]) -> None:
    """List retired paths that will be moved, with their destinations."""
    console.print("\n[bold]Retired paths to archive (moved, not deleted):[/bold]")
    for path, action in items:
        console.print(f"  • {_e(path)} → {_e(str(action).replace('Move to ', '', 1))}")


def show_restore_result(
    restore: Optional[dict[str, Any]],
    skipped_files: Optional[list[tuple[str, str]]] = None,
) -> None:
    """Report backup files skipped and archived items moved back by a rollback."""
    for path, reason in skipped_files or []:
        console.print(f"[bold yellow]⚠[/bold yellow] Did not restore {_e(path)}: {_e(reason)}")
    if not restore:
        return
    for path in restore.get("restored", []):
        console.print(f"[green]✓[/green] Moved back from archive: {_e(path)}")
    for original, archived in restore.get("conflicts", []):
        console.print(
            f"[bold yellow]⚠[/bold yellow] Not restored, {_e(original)} already exists. "
            f"The archived copy is still at {_e(archived)}"
        )
    for archived in restore.get("missing", []):
        console.print(f"[bold yellow]⚠[/bold yellow] Archived item no longer exists: {_e(archived)}")
    for path, message in restore.get("failed", []):
        console.print(f"[bold red]✗[/bold red] Could not move back {_e(path)}: {_e(message)}")


def show_backup_list(backups: list[dict[str, Any]]) -> None:
    """Show list of available backups."""
    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        return

    table = Table(title="Available Backups", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Created", style="white")
    table.add_column("Categories", style="yellow")
    table.add_column("Files", justify="right", style="green")

    for backup in backups:
        # Format created time - could be ISO string or timestamp float
        created = backup["created"]
        if isinstance(created, (int, float)):
            # Legacy format with timestamp - format it
            from datetime import datetime
            created_str = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S")
        else:
            # ISO string format - clean it up
            created_str = str(created).split(".")[0].replace("T", " ")

        table.add_row(
            _e(backup["id"]),
            _e(created_str),
            _e(", ".join(str(c) for c in backup.get("categories", []))),
            str(backup.get("file_count", 0)),
        )

    console.print(table)


def show_status(
    installed: dict[str, Any],
    available: dict[str, Any],
    retired_present: Optional[list[Any]] = None,
    archives: Optional[list[dict[str, Any]]] = None,
) -> None:
    """Show version comparison status.

    Args:
        installed: Installed version stamp
        available: Available version info
        retired_present: Retired paths from the manifest that still exist
        archives: Previous archive runs ({"path", "items"}), newest first
    """
    installed_version = _e(installed.get("tool_version", "Not installed"))
    available_version = _e(available.get("tool_version", "Unknown"))
    installed_hash = _e(installed.get("config_hash") or "")
    available_hash = _e(available.get("config_hash") or "")

    has_updates = installed_hash != available_hash if installed_hash else True

    categories = installed.get("categories") if isinstance(installed.get("categories"), list) else []

    status_text = f"""[bold]Installation Status[/bold]

[bold]Tool Version:[/bold]
  Installed: [cyan]{installed_version}[/cyan]
  Available: [cyan]{available_version}[/cyan]

[bold]Configuration:[/bold]
  Installed: [dim]{installed_hash[:12] if installed_hash else 'None'}[/dim]
  Available: [dim]{available_hash[:12]}[/dim]

[bold]Status:[/bold]
  {"[yellow]⚠ Updates available[/yellow]" if has_updates else "[green]✓ Up to date[/green]"}

[bold]Installed Categories:[/bold]
  {_e(', '.join(str(c) for c in categories)) if categories else '[dim]None[/dim]'}
"""

    if retired_present:
        retired_lines = "\n".join(f"  [red]•[/red] {_e(path)}" for path in retired_present)
        status_text += (
            "\n[bold]Retired Paths Still Present:[/bold]\n"
            f"{retired_lines}\n"
            "  [dim]Run 'claude-setup update' to move them into ~/.claude/archived/[/dim]\n"
        )

    if archives:
        archive_lines = "\n".join(f"  • {_e(a['path'])} ({a['items']} item(s))" for a in archives)
        status_text += (
            "\n[bold]Archived Retired Paths:[/bold]\n"
            f"{archive_lines}\n"
            "  [dim]Safe to delete once you no longer need the old copies[/dim]\n"
        )

    border_color = "yellow" if has_updates or retired_present else "green"
    console.print(Panel(status_text, border_style=border_color, padding=(1, 2)))


def confirm(message: str, default: bool = True) -> bool:
    """Show styled confirmation prompt."""
    return Confirm.ask(f"[bold yellow]?[/bold yellow] {message}", default=default)


def print_error(message: str) -> None:
    """Print error message."""
    console.print(f"[bold red]✗ Error:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[bold cyan]ℹ[/bold cyan] {message}")


def show_scan_results(scan_result: Any) -> None:
    """Display scan results showing discovered files by category.

    Args:
        scan_result: ScanResult with files, settings, and plugins
    """
    # Group files by category and calculate totals
    category_data = {}
    for file in scan_result.files:
        if file.category not in category_data:
            category_data[file.category] = {"count": 0, "size": 0}
        category_data[file.category]["count"] += 1
        category_data[file.category]["size"] += file.size

    # Create table
    table = Table(title="📁 Scanned Files", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="yellow")
    table.add_column("Size", justify="right", style="white")

    # Add rows for each category
    total_count = 0
    total_size = 0
    for category in sorted(category_data.keys()):
        data = category_data[category]
        count = data["count"]
        size = data["size"]
        total_count += count
        total_size += size

        table.add_row(
            category,
            str(count),
            _format_size(size),
        )

    # Add summary row
    if total_count > 0:
        table.add_section()
        table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{total_count}[/bold]",
            f"[bold]{_format_size(total_size)}[/bold]",
        )

    console.print(table)

    # Show settings and plugins info
    if scan_result.settings:
        team_count = len(scan_result.settings.team_fields)
        personal_count = len(scan_result.settings.personal_fields)
        console.print(
            f"[green]✓[/green] Settings found "
            f"([cyan]{team_count} team fields[/cyan], "
            f"[dim]{personal_count} personal fields[/dim])"
        )

    if scan_result.plugins:
        console.print(f"[green]✓[/green] {len(scan_result.plugins)} plugins found")


def show_config_preview(preview: dict) -> None:
    """Display preview of config repo that will be generated.

    Args:
        preview: Preview dict with category_counts, file_lists, output_path, etc.
    """
    output_path = preview["output_path"]
    category_counts = preview["category_counts"]
    file_lists = preview["file_lists"]
    has_settings = preview["has_settings"]
    has_plugins = preview["has_plugins"]
    will_init_git = preview["will_init_git"]

    # Build directory tree structure
    tree_lines = []
    config_name = Path(output_path).name

    tree_lines.append(f"{config_name}/")
    tree_lines.append("├── manifest.json")

    # Core category
    if category_counts.get("core", 0) > 0:
        tree_lines.append("├── core/")
        core_files = file_lists.get("core", [])
        for i, file_path in enumerate(sorted(core_files)):
            filename = Path(file_path).name
            is_last = i == len(core_files) - 1
            prefix = "    └──" if is_last else "    ├──"

            # Add annotation for settings
            if filename == "settings.json":
                tree_lines.append(f"{prefix} {filename} [dim](team fields only)[/dim]")
            else:
                tree_lines.append(f"{prefix} {filename}")

    # Agents category
    if category_counts.get("agents", 0) > 0:
        tree_lines.append("├── agents/")
        agent_files = file_lists.get("agents", [])
        for i, file_path in enumerate(sorted(agent_files)):
            rel_path = Path(file_path).relative_to("agents")
            is_last = i == len(agent_files) - 1
            prefix = "    └──" if is_last else "    ├──"
            tree_lines.append(f"{prefix} {rel_path}")

    # Rules category
    if category_counts.get("rules", 0) > 0:
        tree_lines.append("├── rules/")
        rule_files = file_lists.get("rules", [])
        for i, file_path in enumerate(sorted(rule_files)):
            rel_path = Path(file_path).relative_to("rules")
            is_last = i == len(rule_files) - 1
            prefix = "    └──" if is_last else "    ├──"
            tree_lines.append(f"{prefix} {rel_path}")

    # Commands category
    if category_counts.get("commands", 0) > 0:
        tree_lines.append("├── commands/")
        command_files = file_lists.get("commands", [])

        # Build nested structure for commands
        command_tree = _build_tree_structure(command_files, "commands")
        tree_lines.extend(_format_tree_lines(command_tree, "    ", True))

    # Plugins category
    if has_plugins:
        # Get plugin count from preview or from plugins key if available
        plugin_count = preview.get("plugin_count", 0)
        if plugin_count == 0 and "plugins" in file_lists:
            plugin_count = len(file_lists.get("plugins", []))
        tree_lines.append("└── plugins/")
        tree_lines.append(f"    └── required.json [dim]({plugin_count} plugins)[/dim]")

    # Build preview text
    tree_str = "\n".join(tree_lines)
    preview_text = f"""[bold]Output:[/bold] {output_path}

[bold]Structure:[/bold]
{tree_str}
"""

    # Add footer notes
    notes = []
    if has_settings:
        notes.append("[green]✓[/green] Settings will be filtered (team fields only)")
    if has_plugins:
        plugin_count = preview.get("plugin_count", 0)
        notes.append(f"[green]✓[/green] {plugin_count} plugins included")
    if will_init_git:
        notes.append("[green]✓[/green] Git repository will be initialized")

    if notes:
        preview_text += "\n" + "\n".join(notes)

    console.print(Panel(preview_text, title="🏗️  Config Preview", border_style="cyan", padding=(1, 2)))


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string (e.g., "1.5 KB", "2.3 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _build_tree_structure(file_paths: list[str], base_dir: str) -> dict:
    """Build nested tree structure from file paths.

    Args:
        file_paths: List of file paths relative to ~/.claude
        base_dir: Base directory to remove from paths

    Returns:
        Nested dict representing directory tree
    """
    tree: dict = {}

    for file_path in file_paths:
        # Remove base directory
        rel_path = Path(file_path).relative_to(base_dir)
        parts = rel_path.parts

        # Navigate/create tree structure
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Leaf node (file)
                if "__files__" not in current:
                    current["__files__"] = []
                current["__files__"].append(part)
            else:
                # Directory node
                if part not in current:
                    current[part] = {}
                current = current[part]

    return tree


def _format_tree_lines(tree: dict, indent: str, is_last_category: bool) -> list[str]:
    """Format tree structure as lines with box drawing characters.

    Args:
        tree: Nested dict from _build_tree_structure
        indent: Current indentation level
        is_last_category: Whether this is the last category in the parent

    Returns:
        List of formatted lines
    """
    lines = []

    # Get directories and files
    dirs = {k: v for k, v in tree.items() if k != "__files__"}
    files = tree.get("__files__", [])

    # Sort directories and files
    dir_items = sorted(dirs.items())
    file_items = sorted(files)

    total_items = len(dir_items) + len(file_items)

    # Format directories
    for i, (dir_name, subtree) in enumerate(dir_items):
        is_last = (i == len(dir_items) - 1) and len(file_items) == 0
        prefix = "└──" if is_last else "├──"
        lines.append(f"{indent}{prefix} {dir_name}/")

        # Recursively format subdirectory
        sub_indent = indent + ("    " if is_last else "│   ")
        sub_lines = _format_tree_lines(subtree, sub_indent, False)
        lines.extend(sub_lines)

    # Format files
    for i, filename in enumerate(file_items):
        is_last = i == len(file_items) - 1
        prefix = "└──" if is_last else "├──"
        lines.append(f"{indent}{prefix} {filename}")

    return lines
