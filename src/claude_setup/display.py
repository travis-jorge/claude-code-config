"""Rich UI display helpers."""

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.prompt import Confirm

console = Console()


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
    }

    for status, files in plan.items():
        for file_path, action in files:
            color = status_colors.get(status, "white")
            table.add_row(
                str(file_path),
                f"[{color}]{status}[/{color}]",
                action,
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
            backup["id"],
            created_str,
            ", ".join(backup.get("categories", [])),
            str(backup.get("file_count", 0)),
        )

    console.print(table)


def show_status(installed: dict[str, Any], available: dict[str, Any]) -> None:
    """Show version comparison status."""
    installed_version = installed.get("tool_version", "Not installed")
    available_version = available.get("tool_version", "Unknown")
    installed_hash = installed.get("config_hash", "")
    available_hash = available.get("config_hash", "")

    has_updates = installed_hash != available_hash if installed_hash else True

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
  {', '.join(installed.get('categories', [])) if installed.get('categories') else '[dim]None[/dim]'}
"""

    border_color = "yellow" if has_updates else "green"
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
