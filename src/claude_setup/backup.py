"""Backup and rollback functionality."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class BackupManager:
    """Manages configuration backups."""

    def __init__(self, claude_dir: Path):
        """Initialize backup manager."""
        self.claude_dir = claude_dir
        self.backup_dir = claude_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, files: list[Path], categories: list[str]) -> Path:
        """Create a timestamped backup of specified files.

        Args:
            files: List of file paths to backup
            categories: List of category names being backed up

        Returns:
            Path to the created backup directory
        """
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        backup_name = f"claude-setup-{timestamp}"
        backup_path = self.backup_dir / backup_name
        backup_path.mkdir(parents=True, exist_ok=True)

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

        manifest_path = backup_path / "backup-manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return backup_path

    def list_backups(self) -> list[dict]:
        """List all available backups, sorted by creation time (newest first).

        Returns:
            List of backup info dictionaries
        """
        backups = []

        # Support both new 'claude-setup-*' and legacy 'backup-*' prefixes
        for backup_dir in self.backup_dir.glob("*"):
            if not backup_dir.is_dir():
                continue

            # Only include directories with valid backup prefixes
            if not (backup_dir.name.startswith("claude-setup-") or backup_dir.name.startswith("backup-")):
                continue

            manifest_path = backup_dir / "backup-manifest.json"
            if not manifest_path.exists():
                # Legacy backup without manifest
                backups.append({
                    "id": backup_dir.name,
                    "path": backup_dir,
                    "created": backup_dir.stat().st_mtime,
                    "categories": [],
                    "file_count": sum(1 for _ in backup_dir.rglob("*") if _.is_file()),
                })
                continue

            # Load manifest
            with open(manifest_path) as f:
                manifest = json.load(f)

            backups.append({
                "id": backup_dir.name,
                "path": backup_dir,
                "created": manifest.get("created_at", "Unknown"),
                "categories": manifest.get("categories", []),
                "file_count": len(manifest.get("files", [])),
            })

        # Sort by creation time, newest first
        backups.sort(key=lambda x: x["created"], reverse=True)
        return backups

    def restore_backup(self, backup_id: Optional[str] = None) -> Path:
        """Restore from a backup.

        Args:
            backup_id: Backup directory name, or None for most recent

        Returns:
            Path to the restored backup directory

        Raises:
            FileNotFoundError: If backup not found
        """
        if backup_id is None:
            # Get most recent backup
            backups = self.list_backups()
            if not backups:
                raise FileNotFoundError("No backups available")
            backup_path = backups[0]["path"]
        else:
            backup_path = self.backup_dir / backup_id
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup not found: {backup_id}")

        # Load manifest to get file list
        manifest_path = backup_path / "backup-manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            files_to_restore = manifest.get("files", [])
        else:
            # Legacy backup - restore all files
            files_to_restore = [
                str(f.relative_to(backup_path))
                for f in backup_path.rglob("*")
                if f.is_file() and f.name != "backup-manifest.json"
            ]

        # Restore each file
        for rel_path_str in files_to_restore:
            src_path = backup_path / rel_path_str
            if not src_path.exists():
                continue

            dest_path = self.claude_dir / rel_path_str
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src_path, dest_path)

        return backup_path

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
