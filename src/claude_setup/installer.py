"""Core installation logic."""

import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from claude_setup.archive import (
    ArchiveManager,
    UnsafePathError,
    check_retirable,
    fold_parts,
    within,
)
from claude_setup.backup import BackupManager
from claude_setup.categories import CategoryRegistry, FileEntry
from claude_setup.merge import load_settings, merge_settings, resolve_templates, save_settings
from claude_setup.version import VersionManager


class InstallationError(Exception):
    """Raised when installation fails."""

    pass


class ManifestEntryError(InstallationError):
    """A manifest file entry is malformed (e.g. "dest": null)."""


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
        self.archive_mgr = ArchiveManager(target_dir)
        # Archive run directory the most recent plan would move retired paths into
        self.planned_archive_dir: Optional[Path] = None

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
            Status values: "New", "Updated", "Unchanged", "Merge", plus
            "Archive" (retired paths still present, to be moved into
            ~/.claude/archived/<timestamp>/) and "Refused" (retired entries that
            failed validation; never touched)
        """
        plan = {
            "New": [],
            "Updated": [],
            "Unchanged": [],
            "Merge": [],
        }

        selected_categories = self.registry.get_by_names(categories)
        self._all_install_dests()  # raises ManifestEntryError for malformed entries

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

        retired = self.compute_retired()
        # Keep the destination stable between a preview and the install that follows
        if self.planned_archive_dir is None or os.path.lexists(self.planned_archive_dir):
            self.planned_archive_dir = self.archive_mgr.next_run_dir()
        plan["Archive"] = [
            (path, f"Move to {self.planned_archive_dir / path.relative_to(self.target_dir)}")
            for path in retired["archive"]
        ]
        plan["Refused"] = [(entry, f"Not archived: {reason}") for entry, reason in retired["refused"]]

        return plan

    # ------------------------------------------------------------------
    # Retired paths
    # ------------------------------------------------------------------

    def _category_base(self, target_dir: str) -> Path:
        """Resolve a category's target_dir to an absolute base directory."""
        if target_dir == ".claude":
            return self.target_dir
        return self.target_dir.parent / target_dir

    def _all_install_dests(self) -> list[Path]:
        """Destinations of every file in the manifest (all categories).

        Raises:
            ManifestEntryError: if any category or file entry is malformed
        """
        dests = []
        for category in self.registry.get_all():
            if not isinstance(category.target_dir, str):
                raise ManifestEntryError(f"category {category.name!r} has an invalid target_dir")
            base = self._category_base(category.target_dir)
            for file_entry in category.files:
                if not isinstance(file_entry.src, str) or not isinstance(file_entry.dest, str):
                    raise ManifestEntryError(
                        f"category {category.name!r} has a file entry with an invalid 'src' or 'dest'"
                    )
                dests.append(Path(os.path.normpath(base / file_entry.dest)))
        return dests

    def managed_relpaths(self) -> set[str]:
        """Files the manifest installs, relative to target_dir (empty if malformed)."""
        try:
            dests = self._all_install_dests()
        except ManifestEntryError:
            return set()
        rel = set()
        for dest in dests:
            try:
                rel.add(dest.relative_to(Path(os.path.normpath(self.target_dir))).as_posix())
            except ValueError:
                continue
        return rel

    def _protected_source_paths(self) -> list[Path]:
        """The config dir plus every local source path listed in sources.json."""
        paths = [self.config_dir.resolve()]
        try:
            with open(self.target_dir / "sources.json") as f:
                data = json.load(f)
        except (OSError, ValueError, RecursionError):
            return paths
        sources = data.get("sources", []) if isinstance(data, dict) else []
        for source in sources if isinstance(sources, list) else []:
            # Only local sources name a real directory; github/zip "path" is a subdirectory
            if isinstance(source, dict) and source.get("type") == "local" and isinstance(source.get("path"), str):
                try:
                    paths.append(Path(source["path"]).expanduser().resolve())
                except (OSError, ValueError, RuntimeError):
                    continue
        return paths

    def validate_retired_path(self, entry: Any) -> tuple[Optional[Path], Optional[str]]:
        """Validate one manifest "retired" entry.

        Rules (see archive.py): strictly inside skills/, agents/ or commands/;
        no symlinked component above the leaf; resolved parent inside the
        resolved allowlisted root; no overlap with installed files, the config
        source or any local source from sources.json. Comparisons use NFC +
        casefold.

        Returns:
            (path, None) when safe (leaf unresolved, so a symlink is moved as a
            link), or (None, reason) when refused. Never raises.
        """
        try:
            return self._validate_retired_path(entry), None
        except UnsafePathError as e:
            return None, str(e)
        except (ValueError, OSError, RuntimeError, TypeError) as e:
            return None, f"invalid path ({e})"

    def _validate_retired_path(self, entry: Any) -> Path:
        candidate = check_retirable(self.target_dir, entry)
        resolved = candidate.parent.resolve() / candidate.name

        for protected in self._protected_source_paths():
            if within(resolved, protected) or within(protected, resolved):
                raise UnsafePathError("overlaps a configuration source directory")

        for dest in self._all_install_dests():
            dest_resolved = dest.parent.resolve() / dest.name
            if within(dest, candidate) or within(dest_resolved, resolved):
                raise UnsafePathError(f"overlaps a file the manifest installs ({dest})")

        return candidate

    def compute_retired(self) -> dict[str, list]:
        """Classify the manifest's "retired" entries.

        Entries inside another entry that is being archived (e.g. "skills/x/y"
        when "skills/x" is listed) are reported as covered and not counted twice.

        Returns:
            {"archive": [Path] present and safe to move,
             "absent": [Path] valid but not present,
             "covered": [Path] inside another archived entry,
             "refused": [(entry, reason)] rejected by validation}
        """
        result: dict[str, list] = {"archive": [], "absent": [], "covered": [], "refused": []}
        entries = getattr(self.registry, "retired", []) or []

        # A malformed manifest file entry makes overlap checks impossible: refuse everything.
        try:
            self._all_install_dests()
        except ManifestEntryError as e:
            result["refused"] = [(repr(entry), f"not processed: {e}") for entry in entries]
            return result

        root_problem = self.archive_mgr.root_problem()
        valid: list[Path] = []
        seen: set[tuple[str, ...]] = set()

        for entry in entries:
            path, reason = self.validate_retired_path(entry)
            if path is None:
                result["refused"].append((repr(entry) if not isinstance(entry, str) else entry, reason))
                continue
            key = fold_parts(path)
            if key not in seen:
                seen.add(key)
                valid.append(path)

        # Parents first, so children of an archived directory are "covered"
        for path in sorted(valid, key=lambda p: len(p.parts)):
            if any(within(path, parent) for parent in result["archive"]):
                result["covered"].append(path)
            elif os.path.lexists(path):
                result["archive"].append(path)
            else:
                result["absent"].append(path)

        if root_problem and result["archive"]:
            result["refused"].extend((str(p), root_problem) for p in result["archive"])
            result["archive"] = []

        return result

    def get_retired_present(self) -> list[Path]:
        """Retired paths that still exist under the target directory."""
        return self.compute_retired()["archive"]

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
        archive_retired: bool = True,
    ) -> dict:
        """Perform installation.

        Args:
            categories: List of category names to install
            dry_run: If True, only show plan without making changes
            force: If True, skip confirmation prompts
            archive_retired: If False, leave retired paths where they are

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

        # Collect files to backup. Retired paths are not copied: they are moved
        # into the archive, and the backup records which archive run to undo.
        files_to_backup = []
        for status in ["Updated", "Merge"]:
            files_to_backup.extend([f[0] for f in plan[status]])

        to_archive = [f[0] for f in plan["Archive"]] if archive_retired else []
        archive_dir = self.planned_archive_dir if to_archive else None
        archive_ref = None
        if archive_dir is not None:
            try:
                archive_ref = str(archive_dir.relative_to(self.backup_mgr.claude_dir))
            except ValueError:
                archive_ref = None

        # Create backup if there are files to backup or retired paths to archive
        backup_path = None
        if files_to_backup or to_archive:
            backup_path = self.backup_mgr.create_backup(files_to_backup, categories, archive=archive_ref)

        # Install files
        stats = {
            "installed": 0,
            "updated": 0,
            "unchanged": 0,
            "merged": False,
            "archived": 0,
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

        # Move retired paths into the archive (never deleted)
        archived: list = []
        retired_failed: list = []
        if to_archive:
            outcome = self.archive_mgr.archive(to_archive, archive_dir)
            archived = outcome["moved"]
            retired_failed = outcome["failed"]
        stats["archived"] = len(archived)
        self.planned_archive_dir = None

        # Write version stamp
        self.version_mgr.write_stamp(categories)

        return {
            "stats": stats,
            "categories": categories,
            "backup_path": str(backup_path) if backup_path else None,
            "plan": plan,
            "retired": {
                "archive_dir": str(archive_dir) if archived else None,
                "archived": [(str(orig), str(dest)) for orig, dest in archived],
                "failed": [(str(p), msg) for p, msg in retired_failed],
                "refused": list(plan["Refused"]),
                "skipped": [] if archive_retired else [str(f[0]) for f in plan["Archive"]],
            },
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
