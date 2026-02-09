"""Core installation logic."""

import os
import shutil
from pathlib import Path
from typing import Optional

from claude_setup.backup import BackupManager
from claude_setup.categories import CategoryRegistry, FileEntry
from claude_setup.merge import load_settings, merge_settings, resolve_templates, save_settings
from claude_setup.version import VersionManager


class InstallationError(Exception):
    """Raised when installation fails."""

    pass


class Installer:
    """Handles installation of configuration files."""

    def __init__(
        self,
        config_dir: Path,
        target_dir: Path,
        registry: CategoryRegistry,
        backup_mgr: BackupManager,
        version_mgr: VersionManager,
    ):
        """Initialize installer.

        Args:
            config_dir: Path to config/ directory
            target_dir: Path to installation target (e.g., ~/.claude)
            registry: Category registry
            backup_mgr: Backup manager
            version_mgr: Version manager
        """
        self.config_dir = config_dir
        self.target_dir = target_dir
        self.registry = registry
        self.backup_mgr = backup_mgr
        self.version_mgr = version_mgr

    def preflight_check(self) -> None:
        """Verify target directory exists and is writable.

        Raises:
            InstallationError: If preflight checks fail
        """
        # Create target directory if it doesn't exist
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise InstallationError(
                f"Permission denied: Cannot create {self.target_dir}"
            )

        # Check if directory is writable
        if not os.access(self.target_dir, os.W_OK):
            raise InstallationError(
                f"Permission denied: Cannot write to {self.target_dir}"
            )

    def compute_plan(self, categories: list[str]) -> dict[str, list[tuple[Path, str]]]:
        """Compute installation plan by comparing source and target files.

        Args:
            categories: List of category names to install

        Returns:
            Dictionary mapping status to list of (file_path, action) tuples
            Status values: "New", "Updated", "Unchanged", "Merge"
        """
        plan = {
            "New": [],
            "Updated": [],
            "Unchanged": [],
            "Merge": [],
        }

        selected_categories = self.registry.get_by_names(categories)

        for category in selected_categories:
            # Use target_dir for installation, resolve relative to it
            if category.target_dir == ".claude":
                target_base = self.target_dir
            else:
                target_base = self.target_dir.parent / category.target_dir

            for file_entry in category.files:
                src_path = self.config_dir / file_entry.src
                dest_path = target_base / file_entry.dest

                if file_entry.merge:
                    plan["Merge"].append((dest_path, "Smart merge"))
                elif not dest_path.exists():
                    plan["New"].append((dest_path, "Copy"))
                elif self._files_differ(src_path, dest_path):
                    plan["Updated"].append((dest_path, "Overwrite"))
                else:
                    plan["Unchanged"].append((dest_path, "Skip"))

        return plan

    def _files_differ(self, src: Path, dest: Path) -> bool:
        """Check if two files have different content."""
        if not src.exists() or not dest.exists():
            return True

        try:
            with open(src, "rb") as f1, open(dest, "rb") as f2:
                return f1.read() != f2.read()
        except (IOError, PermissionError):
            return True

    def install(
        self,
        categories: list[str],
        dry_run: bool = False,
        force: bool = False,
    ) -> dict:
        """Perform installation.

        Args:
            categories: List of category names to install
            dry_run: If True, only show plan without making changes
            force: If True, skip confirmation prompts

        Returns:
            Dictionary with installation results and statistics

        Raises:
            InstallationError: If installation fails
        """
        # Preflight checks
        self.preflight_check()

        # Compute plan
        plan = self.compute_plan(categories)

        # If dry run, return plan only
        if dry_run:
            return {"plan": plan, "dry_run": True}

        # Collect files to backup
        files_to_backup = []
        for status in ["Updated", "Merge"]:
            files_to_backup.extend([f[0] for f in plan[status]])

        # Create backup if there are files to backup
        backup_path = None
        if files_to_backup:
            backup_path = self.backup_mgr.create_backup(files_to_backup, categories)

        # Install files
        stats = {
            "installed": 0,
            "updated": 0,
            "unchanged": 0,
            "merged": False,
        }

        selected_categories = self.registry.get_by_names(categories)

        for category in selected_categories:
            # Use target_dir for installation, resolve relative to it
            if category.target_dir == ".claude":
                target_base = self.target_dir
            else:
                target_base = self.target_dir.parent / category.target_dir

            for file_entry in category.files:
                if file_entry.merge:
                    # Handle settings.json merge
                    self._merge_settings_file(file_entry, target_base)
                    stats["merged"] = True
                else:
                    # Regular file copy
                    result = self.install_file(file_entry, target_base)
                    if result == "installed":
                        stats["installed"] += 1
                    elif result == "updated":
                        stats["updated"] += 1
                    elif result == "unchanged":
                        stats["unchanged"] += 1

        # Write version stamp
        self.version_mgr.write_stamp(categories)

        return {
            "stats": stats,
            "categories": categories,
            "backup_path": str(backup_path) if backup_path else None,
            "plan": plan,
        }

    def install_file(self, entry: FileEntry, target_base: Path) -> str:
        """Install a single file.

        Args:
            entry: File entry to install
            target_base: Base directory for installation

        Returns:
            Status: "installed", "updated", or "unchanged"
        """
        src_path = self.config_dir / entry.src
        dest_path = target_base / entry.dest

        if not src_path.exists():
            raise InstallationError(f"Source file not found: {src_path}")

        # Check if file needs updating
        if dest_path.exists() and not self._files_differ(src_path, dest_path):
            return "unchanged"

        status = "updated" if dest_path.exists() else "installed"

        # Create parent directories
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(src_path, dest_path)

        # Apply template resolution if needed
        if entry.template:
            content = dest_path.read_text()
            resolved = self._apply_templates(content)
            dest_path.write_text(resolved)

        # Set executable flag if needed
        if entry.executable:
            dest_path.chmod(0o755)

        return status

    def _merge_settings_file(self, entry: FileEntry, target_base: Path) -> None:
        """Merge settings.json file.

        Args:
            entry: File entry for settings.json
            target_base: Base directory for installation
        """
        src_path = self.config_dir / entry.src
        dest_path = target_base / entry.dest

        # Load source settings
        source_settings = load_settings(src_path)

        # Load target settings (if exists)
        target_settings = load_settings(dest_path) if dest_path.exists() else {}

        # Merge settings
        if target_settings:
            merged_settings = merge_settings(source_settings, target_settings)
        else:
            # No existing settings, use source as-is
            merged_settings = source_settings

        # Resolve templates - use target_dir parent as home for tests
        home_dir = self.target_dir.parent if self.target_dir.name == ".claude" else Path.home()
        merged_settings = resolve_templates(merged_settings, home_dir)

        # Save merged settings
        save_settings(dest_path, merged_settings)

    def _apply_templates(self, content: str) -> str:
        """Apply template variable resolution.

        Args:
            content: File content with template variables

        Returns:
            Content with templates resolved
        """
        # Replace {{HOME}} with user's home directory (or test directory)
        home_dir = self.target_dir.parent if self.target_dir.name == ".claude" else Path.home()
        return content.replace("{{HOME}}", str(home_dir))
