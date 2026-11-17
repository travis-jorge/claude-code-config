"""Backup and rollback functionality."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import claude_setup.archive as archive
from claude_setup.archive import ARCHIVE_DIR_NAME, ArchiveManager, fold

MANIFEST_NAME = "backup-manifest.json"


class BackupError(ValueError):
    """A backup exists but cannot be used (e.g. invalid backup-manifest.json)."""


def _parse_created(value: Any) -> Optional[datetime]:
    """Parse a manifest created_at value (ISO timestamp string) or return None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_manifest(path: Path) -> dict:
    """Load and validate a backup-manifest.json; raise BackupError if invalid.

    Required: a JSON object with ``created_at`` (ISO timestamp string). If
    present, ``files`` must be a list, ``categories`` a list of strings and
    ``archive`` a string.
    """
    try:
        with open(path) as f:
            manifest = json.load(f)
    except (OSError, ValueError, RecursionError) as e:
        raise BackupError(f"Cannot read {path}: {type(e).__name__}") from e
    if not isinstance(manifest, dict):
        raise BackupError(
            f"{path} is not a valid backup manifest (expected a JSON object)"
        )
    if _parse_created(manifest.get("created_at")) is None:
        raise BackupError(
            f"{path} is not a valid backup manifest ('created_at' must be an ISO timestamp)"
        )
    if not isinstance(manifest.get("files", []), list):
        raise BackupError(
            f"{path} is not a valid backup manifest ('files' must be a list)"
        )
    categories = manifest.get("categories", [])
    if not isinstance(categories, list) or not all(
        isinstance(c, str) for c in categories
    ):
        raise BackupError(
            f"{path} is not a valid backup manifest ('categories' must be a list of strings)"
        )
    if "archive" in manifest and not isinstance(manifest["archive"], str):
        raise BackupError(
            f"{path} is not a valid backup manifest ('archive' must be a string)"
        )
    return manifest


def _unique_dir(path: Path) -> Path:
    """Create and return path, or path-1, path-2, ... if it already exists."""
    candidate, n = path, 0
    while True:
        try:
            candidate.mkdir(parents=False)
            return candidate
        except FileExistsError:
            n += 1
            candidate = path.with_name(f"{path.name}-{n}")


class BackupManager:
    """Manages configuration backups."""

    def __init__(self, claude_dir: Path):
        """Initialize backup manager."""
        self.claude_dir = claude_dir
        self.backup_dir = claude_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        # Outcome of moving archived (retired) items back during the last restore
        self.last_archive_restore: Optional[dict] = None
        # Files the last restore refused to touch: [(relative path, reason)]
        self.last_restore_skipped: list[tuple[str, str]] = []

    def create_backup(
        self,
        files: list[Path],
        categories: list[str],
        archive: Optional[str] = None,
    ) -> Path:
        """Create a timestamped backup of specified files.

        Backups created in the same second get a ``-1``, ``-2``, ... suffix; an
        existing backup directory is never reused.

        Args:
            files: List of file paths to backup
            categories: List of category names being backed up
            archive: Archive run (path relative to claude_dir, e.g.
                "archived/2026-01-01-120000") that this install moved retired
                paths into. Rollback moves those items back.

        Returns:
            Path to the created backup directory
        """
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        backup_path = _unique_dir(self.backup_dir / f"claude-setup-{timestamp}")

        # Backup each file, preserving directory structure
        backed_up_files = []
        for file_path in files:
            if not file_path.exists():
                continue

            # Get relative path from claude_dir
            try:
                rel_path = file_path.relative_to(self.claude_dir)
            except ValueError:
                # File is not in claude_dir, skip
                continue

            dest_path = backup_path / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(file_path, dest_path)
            backed_up_files.append(str(rel_path))

        # Create backup manifest
        manifest = {
            "created_at": datetime.now().isoformat(),
            "categories": categories,
            "files": backed_up_files,
            "tool_version": "1.0.0",
        }
        if archive:
            manifest["archive"] = archive

        manifest_path = backup_path / MANIFEST_NAME
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return backup_path

    def list_backups(self) -> list[dict]:
        """List all available backups, sorted by creation time (newest first).

        Invalid manifests are listed with ``"invalid": True`` and dated by the
        directory mtime, so they never sort ahead of newer valid backups.
        Symlinked backup directories are ignored.

        Returns:
            List of backup info dictionaries
        """
        backups = []
        if os.path.islink(self.backup_dir):
            return backups

        # Support both new 'claude-setup-*' and legacy 'backup-*' prefixes
        for backup_dir in self.backup_dir.glob("*"):
            if backup_dir.is_symlink() or not backup_dir.is_dir():
                continue

            # Only include directories with valid backup prefixes
            if not (
                backup_dir.name.startswith("claude-setup-")
                or backup_dir.name.startswith("backup-")
            ):
                continue

            mtime = backup_dir.stat().st_mtime
            manifest_path = backup_dir / MANIFEST_NAME
            if not os.path.lexists(manifest_path):
                # Legacy backup without manifest
                backups.append(
                    {
                        "id": backup_dir.name,
                        "path": backup_dir,
                        "created": mtime,
                        "categories": [],
                        "file_count": sum(
                            1 for _ in backup_dir.rglob("*") if _.is_file()
                        ),
                        "sort_key": mtime,
                    }
                )
                continue

            try:
                if os.path.islink(manifest_path):
                    raise BackupError("backup manifest is a symlink")
                manifest = _load_manifest(manifest_path)
            except BackupError:
                backups.append(
                    {
                        "id": backup_dir.name,
                        "path": backup_dir,
                        "created": datetime.fromtimestamp(mtime).isoformat(),
                        "categories": ["(invalid backup manifest)"],
                        "file_count": 0,
                        "invalid": True,
                        "sort_key": mtime,
                    }
                )
                continue

            created = manifest["created_at"]
            backups.append(
                {
                    "id": backup_dir.name,
                    "path": backup_dir,
                    "created": created,
                    "categories": manifest.get("categories", []),
                    "file_count": len(manifest.get("files", [])),
                    "sort_key": _parse_created(created).timestamp(),
                }
            )

        backups.sort(key=lambda x: x["sort_key"], reverse=True)
        return backups

    def resolve_backup(self, backup_id: Any) -> Path:
        """Return the directory for backup_id (a single name inside backups/).

        Raises:
            FileNotFoundError: if it isn't a plain name of an existing,
                non-symlink backup directory
        """
        valid_name = (
            isinstance(backup_id, str)
            and backup_id not in ("", ".", "..")
            and "/" not in backup_id
            and "\\" not in backup_id
            and not any(ord(ch) < 32 for ch in backup_id)
        )
        if not valid_name or os.path.islink(self.backup_dir):
            raise FileNotFoundError(f"Backup not found: {backup_id}")
        path = self.backup_dir / backup_id
        if os.path.islink(path) or not path.is_dir():
            raise FileNotFoundError(f"Backup not found: {backup_id}")
        return path

    def restore_backup(
        self,
        backup_id: Optional[str] = None,
        managed_files: Optional[Iterable[str]] = None,
    ) -> Path:
        """Restore from a backup.

        Files are only read from inside the backup directory and only written
        inside ~/.claude: an entry is skipped (and listed in
        ``last_restore_skipped``) if its source is a symlink or is reached
        through one, or if any folder above its destination under ~/.claude is
        a symlink. A destination that is itself a symlink (e.g. a
        dotfiles-linked CLAUDE.md) is written through only when it is a file
        the current manifest installs (``managed_files``, relative to
        ~/.claude); otherwise it is skipped.

        Args:
            backup_id: Backup directory name, or None for most recent valid backup
            managed_files: Relative paths of files the manifest installs

        Returns:
            Path to the restored backup directory

        Raises:
            FileNotFoundError: If backup not found
            BackupError: If the backup manifest is invalid
        """
        if backup_id is None:
            backups = [b for b in self.list_backups() if not b.get("invalid")]
            if not backups:
                raise FileNotFoundError("No backups available")
            backup_path = backups[0]["path"]
        else:
            backup_path = self.resolve_backup(backup_id)

        managed = {fold(p) for p in (managed_files or [])}
        self.last_restore_skipped = []

        # Load manifest to get file list
        manifest_path = backup_path / MANIFEST_NAME
        manifest: dict = {}
        if os.path.islink(manifest_path):
            raise BackupError(f"{manifest_path} is a symlink")
        if manifest_path.exists():
            manifest = _load_manifest(manifest_path)
            files_to_restore = manifest.get("files", [])
        else:
            # Legacy backup - restore all files
            files_to_restore = [
                str(f.relative_to(backup_path))
                for f in backup_path.rglob("*")
                if f.is_file() and f.name != MANIFEST_NAME
            ]

        for rel_path_str in files_to_restore:
            reason = self._restore_file(backup_path, rel_path_str, managed)
            if reason:
                self.last_restore_skipped.append((str(rel_path_str), reason))

        # Move archived (retired) items back where their original path is free
        self.last_archive_restore = None
        archive_dir = self.get_archive_dir(manifest)
        if archive_dir is not None:
            self.last_archive_restore = ArchiveManager(self.claude_dir).restore(
                archive_dir
            )
        elif manifest.get("archive") is not None:
            self.last_archive_restore = {
                "restored": [],
                "conflicts": [],
                "missing": [],
                "failed": [
                    (
                        str(manifest.get("archive")),
                        "archive folder is missing, a symlink, or not inside ~/.claude/archived; nothing moved back",
                    )
                ],
            }

        return backup_path

    def _restore_file(
        self, backup_path: Path, rel_path: Any, managed: set[str]
    ) -> Optional[str]:
        """Copy one file back. Returns a reason if it was skipped, else None."""
        try:
            parts = archive.parse_relative(rel_path)
            src = archive.check_no_symlink_components(backup_path, parts)
            if os.path.islink(src):
                return "backup copy is a symlink"
            if not src.is_file():
                return (
                    None
                    if not os.path.lexists(src)
                    else "backup copy is not a regular file"
                )

            dest = archive.check_no_symlink_components(self.claude_dir, parts)
            if os.path.islink(dest) and fold("/".join(parts)) not in managed:
                return "destination is a symlink and not a file the manifest installs"

            dest.parent.mkdir(parents=True, exist_ok=True)
            # Parents just created must still be real directories
            archive.check_no_symlink_components(self.claude_dir, parts)
            shutil.copy2(src, dest)
        except archive.UnsafePathError as e:
            return str(e)
        except (OSError, ValueError) as e:
            return f"could not restore: {e}"
        return None

    def get_archive_dir(self, manifest_or_id) -> Optional[Path]:
        """Return the archive run linked to a backup, if any and if it is safe.

        Accepts a loaded backup manifest dict or a backup id.
        """
        manifest = manifest_or_id
        if isinstance(manifest_or_id, str):
            try:
                manifest = _load_manifest(
                    self.resolve_backup(manifest_or_id) / MANIFEST_NAME
                )
            except (BackupError, FileNotFoundError):
                return None
        if not isinstance(manifest, dict):
            return None

        # Only accept archived/<run> written by claude-setup, as a real
        # (non-symlink) direct child of the real ~/.claude/archived
        try:
            parts = archive.parse_relative(manifest.get("archive"))
        except archive.UnsafePathError:
            return None
        if len(parts) != 2 or parts[0] != ARCHIVE_DIR_NAME:
            return None
        archives = ArchiveManager(self.claude_dir)
        try:
            return archives.validate_run_dir(archives.archive_root / parts[1])
        except (archive.UnsafePathError, OSError):
            return None

    def clean_old_backups(self, keep: int = 5) -> int:
        """Remove old backups, keeping only the most recent N.

        Args:
            keep: Number of backups to keep

        Returns:
            Number of backups deleted
        """
        backups = self.list_backups()
        to_delete = backups[keep:]

        deleted = 0
        for backup in to_delete:
            backup_path = backup["path"]
            if backup_path.exists():
                shutil.rmtree(backup_path)
                deleted += 1

        return deleted
