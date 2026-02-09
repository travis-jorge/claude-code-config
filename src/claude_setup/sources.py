"""Configuration source management."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve


def expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR_NAME} and $VAR_NAME syntax.

    Args:
        value: String potentially containing env var references

    Returns:
        String with environment variables expanded

    Raises:
        SourceError: If referenced environment variable is not set
    """
    if not isinstance(value, str):
        return value

    # Pattern to match ${VAR_NAME} or $VAR_NAME
    pattern = r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)'

    def replace_var(match):
        var_name = match.group(1) or match.group(2)
        if var_name not in os.environ:
            raise SourceError(
                f"Environment variable '{var_name}' not set. "
                f"Please set it with: export {var_name}=<value>"
            )
        return os.environ[var_name]

    return re.sub(pattern, replace_var, value)


def expand_config_env_vars(config: dict) -> dict:
    """Recursively expand environment variables in a config dict.

    Args:
        config: Configuration dictionary

    Returns:
        New dictionary with environment variables expanded
    """
    if isinstance(config, dict):
        return {key: expand_config_env_vars(value) for key, value in config.items()}
    elif isinstance(config, list):
        return [expand_config_env_vars(item) for item in config]
    elif isinstance(config, str):
        return expand_env_vars(config)
    else:
        return config


class ConfigSource:
    """Base class for configuration sources."""

    def __init__(self, name: str, config: dict):
        """Initialize source.

        Args:
            name: Source identifier
            config: Source configuration dict
        """
        self.name = name
        self.config = config

    def fetch(self, cache_dir: Path) -> Path:
        """Fetch configuration files to cache directory.

        Args:
            cache_dir: Directory to cache files

        Returns:
            Path to the fetched config directory

        Raises:
            SourceError: If fetch fails
        """
        raise NotImplementedError


class LocalSource(ConfigSource):
    """Local filesystem source."""

    def fetch(self, cache_dir: Path) -> Path:
        """Copy from local path."""
        source_path = Path(self.config["path"]).expanduser()

        if not source_path.exists():
            raise SourceError(f"Local path not found: {source_path}")

        if not source_path.is_dir():
            raise SourceError(f"Path is not a directory: {source_path}")

        dest_path = cache_dir / self.name
        if dest_path.exists():
            shutil.rmtree(dest_path)

        shutil.copytree(source_path, dest_path)
        return dest_path


class GitHubSource(ConfigSource):
    """GitHub repository source."""

    def fetch(self, cache_dir: Path) -> Path:
        """Clone or pull from GitHub."""
        repo = self.config["repo"]
        ref = self.config.get("ref", "main")
        token = self.config.get("token")

        dest_path = cache_dir / self.name

        # Build clone URL with optional token
        if token:
            clone_url = f"https://{token}@github.com/{repo}.git"
        else:
            clone_url = f"https://github.com/{repo}.git"

        try:
            if dest_path.exists():
                # Update existing clone
                subprocess.run(
                    ["git", "-C", str(dest_path), "fetch", "origin"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "-C", str(dest_path), "checkout", ref],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "-C", str(dest_path), "pull", "origin", ref],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            else:
                # Fresh clone
                subprocess.run(
                    ["git", "clone", "-b", ref, clone_url, str(dest_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            # Return path to config subdirectory if specified
            config_subdir = self.config.get("path", ".")
            final_path = dest_path / config_subdir

            if not final_path.exists():
                raise SourceError(
                    f"Config path not found in repo: {config_subdir}"
                )

            return final_path

        except subprocess.CalledProcessError as e:
            raise SourceError(f"Git operation failed: {e.stderr}")


class ZipSource(ConfigSource):
    """Zip file source (HTTP/HTTPS URL)."""

    def fetch(self, cache_dir: Path) -> Path:
        """Download and extract zip file."""
        url = self.config["url"]
        dest_path = cache_dir / self.name

        if dest_path.exists():
            shutil.rmtree(dest_path)

        dest_path.mkdir(parents=True)

        try:
            # Download zip to temp file
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            urlretrieve(url, tmp_path)

            # Extract zip
            with zipfile.ZipFile(tmp_path, "r") as zip_ref:
                zip_ref.extractall(dest_path)

            tmp_path.unlink()

            # If there's a single top-level directory, use it
            items = list(dest_path.iterdir())
            if len(items) == 1 and items[0].is_dir():
                # Move contents up one level
                temp_dir = dest_path.parent / f"{self.name}_temp"
                items[0].rename(temp_dir)
                shutil.rmtree(dest_path)
                temp_dir.rename(dest_path)

            # Return path to config subdirectory if specified
            config_subdir = self.config.get("path", ".")
            final_path = dest_path / config_subdir

            if not final_path.exists():
                raise SourceError(
                    f"Config path not found in zip: {config_subdir}"
                )

            return final_path

        except Exception as e:
            raise SourceError(f"Zip download/extract failed: {e}")


class SourceError(Exception):
    """Raised when source fetch fails."""

    pass


class SourceManager:
    """Manages multiple configuration sources."""

    def __init__(self, cache_dir: Path):
        """Initialize source manager.

        Args:
            cache_dir: Directory for caching sources
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sources: list[ConfigSource] = []

    def load_sources(self, config_file: Path) -> None:
        """Load sources from configuration file.

        Args:
            config_file: Path to sources.json or sources.yaml

        Raises:
            FileNotFoundError: If config file doesn't exist
            SourceError: If config is invalid
        """
        if not config_file.exists():
            raise FileNotFoundError(f"Sources config not found: {config_file}")

        with open(config_file) as f:
            if config_file.suffix == ".json":
                config = json.load(f)
            else:
                # YAML support would require pyyaml dependency
                raise SourceError("Only JSON config supported currently")

        sources_config = config.get("sources", [])

        for idx, source_config in enumerate(sources_config):
            # Expand environment variables in config
            try:
                source_config = expand_config_env_vars(source_config)
            except SourceError as e:
                raise SourceError(f"Failed to expand environment variables: {e}")

            source_type = source_config.get("type")
            source_name = source_config.get("name", f"source-{idx}")

            if source_type == "local":
                self.sources.append(LocalSource(source_name, source_config))
            elif source_type == "github":
                self.sources.append(GitHubSource(source_name, source_config))
            elif source_type == "zip":
                self.sources.append(ZipSource(source_name, source_config))
            else:
                raise SourceError(f"Unknown source type: {source_type}")

    def fetch_all(self) -> list[Path]:
        """Fetch all configured sources.

        Returns:
            List of paths to fetched config directories

        Raises:
            SourceError: If any fetch fails
        """
        paths = []
        for source in self.sources:
            try:
                path = source.fetch(self.cache_dir)
                paths.append(path)
            except SourceError as e:
                raise SourceError(f"Failed to fetch {source.name}: {e}")

        return paths

    def get_primary_source(self) -> Optional[Path]:
        """Get the primary (first) source's config directory.

        Returns:
            Path to primary source config, or None if no sources
        """
        if not self.sources:
            return None

        return self.sources[0].fetch(self.cache_dir)
