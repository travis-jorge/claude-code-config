# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Setup is a pluggable CLI tool for managing Claude Code team configurations. It's designed to be organization-agnostic: the tool is generic and fetches configuration from external sources (GitHub repos, zip files, or local directories).

**Key Architecture Principle**: Clean separation between tool and configuration. This repo contains the tool only; configuration is fetched from sources defined in `~/.claude/sources.json`.

## Development Commands

### Setup
```bash
# Install in editable mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_installer.py

# Run with coverage
pytest --cov=claude_setup --cov-report=html

# Run specific test
pytest tests/test_merge.py::test_merge_fresh_install -v
```

### Running the Tool
```bash
# Run as module (development)
python -m claude_setup

# Run as installed command
claude-setup

# Test with example config
claude-setup init --local examples/config-template
claude-setup install --all --dry-run
```

## Architecture

### Two-Tier System

1. **Tool Layer** (this repo) - Generic installation engine
2. **Config Layer** (external repos) - Organization-specific settings

The tool never contains company-specific configuration. It fetches config from sources at runtime.

### Source System

**Flow**: `sources.json` → `SourceManager` → `LocalSource`/`GitHubSource`/`ZipSource` → cached config → `CategoryRegistry` → `Installer`

**Source Types** (`src/claude_setup/sources.py`):
- `LocalSource` - Copy from filesystem path
- `GitHubSource` - Clone/pull from GitHub (supports private repos with tokens)
- `ZipSource` - Download and extract from HTTP/HTTPS URL

Sources are cached in `~/.claude/sources/` to avoid repeated fetches.

### Core Modules

**`cli.py`** - Typer-based CLI with two modes:
- Interactive menu (questionary-based, runs when no command specified)
- Direct commands (install, status, plugins, update, rollback, backups, init)

**`installer.py`** - Core installation logic:
- Computes installation plan (New/Updated/Unchanged/Merge status for each file)
- Creates automatic backups before changes
- Handles file copying with template resolution and executable flags
- Delegates to merge.py for settings.json smart merge

**`categories.py`** - Configuration structure:
- Loads `manifest.json` from config source
- Defines categories (core, agents, rules, commands, plugins)
- Each category has install_type: merge, overwrite, discover, or check
- File discovery for recursive directories (commands category)

**`merge.py`** - Smart settings.json merging:
- **Union**: `permissions.allow` and `enabledPlugins` (team + user)
- **Preserve**: `permissions.deny`, `permissions.ask`, `feedbackSurveyState`, unknown keys
- **Overwrite**: `model`, `statusLine`, `alwaysThinkingEnabled` (team standard)
- Template resolution: `{{HOME}}` → actual home directory path

**`backup.py`** - Backup/rollback system:
- Timestamped backups: `~/.claude/backups/claude-setup-YYYY-MM-DD-HHMMSS/`
- Supports legacy `backup-*` format
- Stores manifest with categories and file list
- Rollback restores from backup directory

**`version.py`** - Update detection:
- Version stamp: `~/.claude/.claude-setup-version.json`
- SHA256 hash of all config files for change detection
- Compares installed vs available to detect updates

**`plugins.py`** - Plugin management:
- Reads `~/.claude/plugins/installed_plugins.json`
- Compares against `config/plugins/required.json`
- Can invoke `claude plugin install` via subprocess

**`display.py`** - Rich terminal UI:
- Banners, tables, progress bars, panels
- Uses Rich library for formatting

**`init.py`** - Source initialization:
- Checks for sources in order: `~/.claude/sources.json`, `.claude-setup-sources.json`, fallback
- Creates default sources configuration

### Configuration Structure

External config repos should follow this structure:

```
your-org/claude-config/
├── manifest.json          # Required: category definitions
├── core/
│   ├── CLAUDE.md          # Main instructions
│   ├── settings.json      # Team settings (supports {{HOME}} template)
│   └── statusline.sh      # Status line script
├── agents/                # Optional: agent definitions
├── rules/                 # Optional: team rules
├── commands/              # Optional: custom commands
└── plugins/
    └── required.json      # Optional: required plugins list
```

See `examples/config-template/` for a complete template.

### Manifest Schema

`manifest.json` defines installation categories:

```json
{
  "version": "1.0.0",
  "categories": [
    {
      "name": "core",
      "description": "Core configuration files",
      "target_dir": ".claude",
      "install_type": "merge",  // merge|overwrite|discover|check
      "files": [
        {
          "src": "core/settings.json",
          "dest": "settings.json",
          "merge": true,          // Use smart merge
          "executable": false,
          "template": true        // Resolve {{HOME}}
        }
      ]
    }
  ]
}
```

**Install types**:
- `merge` - Smart merge (only for settings.json)
- `overwrite` - Replace existing files
- `discover` - Recursively find all files in directory
- `check` - Validation only (used for plugins)

### Interactive Menu Flow

When run without arguments, `cli.py` launches `interactive_menu()`:
1. Shows main menu (questionary.select)
2. User selects action → calls `interactive_install()`, `interactive_plugins()`, etc.
3. Each function handles its workflow with prompts
4. Returns to main menu with `press_any_key_to_continue()`
5. `console.clear()` between iterations

### Installation Flow

1. `cli.py:install()` → gets managers via `initialize_managers()`
2. Category selection (interactive checkbox or --all flag)
3. `Installer.compute_plan()` → diffs source vs target, classifies files
4. Display plan with `show_install_plan()`
5. User confirms → `Installer.install()`
6. `BackupManager.create_backup()` if files will change
7. For each category:
   - Regular files: `install_file()` → copy + chmod + template resolution
   - Settings: `_merge_settings_file()` → smart merge
8. `VersionManager.write_stamp()` with categories and config hash
9. Display summary with `show_summary()`

### Testing Architecture

Tests use `conftest.py` fixtures:
- `temp_dir` - Isolated temp directory
- `mock_config_dir` - Fake config/ structure with manifest
- `mock_claude_dir` - Fake ~/.claude/ directory
- `existing_settings` - Sample settings.json

**Test categories**:
- `test_merge.py` - Settings merge logic (union, preserve, overwrite rules)
- `test_backup.py` - Backup creation, listing, restoration, cleanup
- `test_installer.py` - Installation flow, dry-run, file copying, template resolution
- `test_categories.py` - Manifest loading, file discovery

### Template Variable System

Files with `template: true` get variable resolution:
- `{{HOME}}` → `Path.home()` (user's home directory)

Applied in:
- `Installer._apply_templates()` for regular files
- `merge.resolve_templates()` for settings.json

Used in `settings.json` for statusLine command paths.

## Important Implementation Details

### Home Directory Resolution for Tests

The installer must use `self.target_dir` instead of `Path.home()` to support test isolation. Tests pass a mock `~/.claude` directory.

Key pattern in `installer.py`:
```python
# Use target_dir parent as home for tests
home_dir = self.target_dir.parent if self.target_dir.name == ".claude" else Path.home()
```

### Category Target Resolution

Categories have `target_dir` field (e.g., ".claude", ".claude/agents"). Installer must handle both:
- Base dir: `.claude` → use `self.target_dir` directly
- Subdirs: `.claude/agents` → use `self.target_dir.parent / category.target_dir`

### Backup Timestamp Handling

Backups support both:
- New format: ISO timestamp string in manifest
- Legacy format: filesystem mtime (float timestamp)

Display must handle both types in `show_backup_list()`.

### Settings Merge Algorithm

Critical that merge preserves user customizations while applying team standards:
1. Start with target (user) settings to preserve unknown keys
2. Union `permissions.allow` (sorted)
3. Keep user's `permissions.deny` and `permissions.ask`
4. Union `enabledPlugins` (team plugins overwrite user values for same key)
5. Overwrite `model`, `statusLine`, `alwaysThinkingEnabled`
6. Keep `feedbackSurveyState`

### Source Caching

Sources are fetched once and cached in `~/.claude/sources/`:
- `LocalSource` - copied to cache
- `GitHubSource` - cloned to cache (subsequent fetches use git pull)
- `ZipSource` - extracted to cache

Cache persists across runs for performance.

## Creating Organization Configs

Admins creating their own config should:
1. Copy `examples/config-template/` as starting point
2. Customize `core/CLAUDE.md` and `core/settings.json`
3. Add team-specific rules in `rules/`
4. Add custom commands in `commands/`
5. List required plugins in `plugins/required.json`
6. Push to GitHub or host as zip
7. Team members run: `claude-setup init --github your-org/claude-config`

See `ADMIN-GUIDE.md` for complete setup instructions.

## Version 2.0 Migration

This is v2.0 with the source-based architecture. v1.x bundled config in the repo.

**Breaking change**: Configuration must be fetched from sources (not bundled).

**Migration path**: Run `claude-setup init` to configure sources, then `claude-setup install`.

A generic configuration template is provided in `examples/config-template/` and can be used for testing:
```bash
claude-setup init --local examples/config-template
```
