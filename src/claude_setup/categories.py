"""Category registry and file management."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FileEntry:
    """Represents a single file to be installed."""

    src: str
    dest: str
    merge: bool = False
    executable: bool = False
    template: bool = False


@dataclass
class Category:
    """Represents an installation category."""

    name: str
    description: str
    target_dir: str
    install_type: str  # "merge", "overwrite", "discover", "check"
    files: list[FileEntry]


class CategoryRegistry:
    """Manages available installation categories."""

    def __init__(self, config_dir: Path):
        """Initialize registry from manifest."""
        self.config_dir = config_dir
        self.manifest_path = config_dir / "manifest.json"
        self.categories: dict[str, Category] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load and parse manifest.json."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")

        with open(self.manifest_path) as f:
            data = json.load(f)

        for cat_data in data["categories"]:
            files = [FileEntry(**f) for f in cat_data.get("files", [])]

            # For 'discover' type, find files dynamically
            if cat_data["install_type"] == "discover":
                files = self._discover_files(cat_data["name"])

            category = Category(
                name=cat_data["name"],
                description=cat_data["description"],
                target_dir=cat_data["target_dir"],
                install_type=cat_data["install_type"],
                files=files,
            )
            self.categories[category.name] = category

    def _discover_files(self, category_name: str) -> list[FileEntry]:
        """Discover files in a category directory recursively."""
        category_path = self.config_dir / category_name
        if not category_path.exists():
            return []

        files = []
        for item in category_path.rglob("*"):
            if item.is_file():
                # Get relative path from category directory
                rel_path = item.relative_to(category_path)
                is_executable = item.suffix == ".sh"

                files.append(
                    FileEntry(
                        src=f"{category_name}/{rel_path}",
                        dest=str(rel_path),
                        merge=False,
                        executable=is_executable,
                        template=False,
                    )
                )

        return files

    def get_all(self) -> list[Category]:
        """Get all categories."""
        return list(self.categories.values())

    def get(self, name: str) -> Optional[Category]:
        """Get a specific category by name."""
        return self.categories.get(name)

    def get_file_count(self, name: str) -> int:
        """Get the number of files in a category."""
        category = self.get(name)
        return len(category.files) if category else 0

    def get_by_names(self, names: list[str]) -> list[Category]:
        """Get multiple categories by name."""
        return [self.categories[name] for name in names if name in self.categories]
