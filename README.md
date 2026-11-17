# Claude Setup

**A flexible, organization-agnostic CLI tool for managing Claude Code team configuration.**

Perfect for teams who want to standardize their Claude Code setup across developers while keeping control of their configuration.

[![Tests](https://github.com/travis-jorge/claude-code-config/actions/workflows/test.yml/badge.svg)](https://github.com/travis-jorge/claude-code-config/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- ✨ **Beginner-Friendly Wizard** (v3.4.0+) - Intuitive setup with 5 simple options
- 🎨 **Interactive Menu** - Navigate all features with arrow keys
- 🔌 **Pluggable Sources** - GitHub repos, zip files, or local directories
- 📦 **Category-based Installation** - Install only what you need
- 💾 **Smart Settings Merge** - Preserve user customizations
- 🏗️ **Config Bootstrapping** - Generate config repos from existing setups with automatic team/personal settings separation
- 🔄 **Automatic Backups** - Safe, reversible updates
- 🔌 **Plugin Management** - Auto-detect and install required plugins
- 🎯 **Update Detection** - Know when new config is available
- 🎨 **Rich Terminal UI** - Beautiful, informative output
- 🧪 **Automated Testing** (v3.4.0+) - GitHub Actions CI for quality assurance

## 🚀 Quick Start

### For Team Members (Using Existing Config)

Your admin should provide you with either a setup script or source configuration.

**Option 1: Using the Interactive Wizard (Easiest - v3.4.0+)**
```bash
# 1. Install tool
git clone https://github.com/travis-jorge/claude-code-config.git
cd claude-setup
pip install -e .

# 2. Run the beginner-friendly wizard
claude-setup init
# Or just: claude-setup (then choose "Setup Configuration")

# The wizard will guide you through:
# - Using a zip file with pre-made config
# - Cloning a git repository
# - Creating config from scratch
# - Or advanced custom setup

# 3. Install configuration
claude-setup install --all

# 4. Check plugins
claude-setup plugins
```

**Option 2: Direct command (if you know the source)**
```bash
# 1. Install tool
git clone https://github.com/travis-jorge/claude-code-config.git
cd claude-setup
pip install -e .

# 2. Initialize with your organization's config
claude-setup init --github your-org/claude-config
# Or: claude-setup init --local /path/to/config
# Or: claude-setup init --zip https://example.com/config.zip

# 3. Install configuration
claude-setup install --all

# 4. Check plugins
claude-setup plugins
```

### For Administrators (Setting Up for Your Team)

See **[ADMIN-GUIDE.md](ADMIN-GUIDE.md)** for complete instructions.

**Quick Start:**
```bash
# Create a config from your existing setup (recommended)
claude-setup create-config --output ~/my-org-config

# Or start from template
cp -r examples/config-template/ my-org-config/
cd my-org-config/
# Customize...
```

## 📖 Usage

### Interactive Menu (Recommended)

Simply run without arguments:
```bash
claude-setup
```

Navigate with arrow keys through:
- ⚙️ **Setup Configuration** (v3.4.0+) - Beginner-friendly wizard
- 📦 Install Configuration
- 📊 Check Installation Status
- 🔌 Manage Plugins
- 💾 View Backups
- ⏮️ Rollback to Backup
- 🔄 Check for Updates
- 🔧 **Advanced/Admin Tools** (v3.4.0+) - Create config repos for sharing

### Command Line

```bash
# Run beginner-friendly wizard (v3.4.0+)
claude-setup init

# Or initialize sources directly
claude-setup init --github your-org/claude-config
claude-setup init --local /path/to/config
claude-setup init --zip https://example.com/config.zip

# Install everything
claude-setup install --all

# Check status
claude-setup status

# Update to latest (files, then team marketplaces and required plugins)
claude-setup update
claude-setup update --skip-plugins   # files only

# Manage plugins
claude-setup plugins

# View backups
claude-setup backups

# Rollback if needed
claude-setup rollback

# Create a config repo from your ~/.claude setup
claude-setup create-config
```

## 🏗️ Architecture

### Configuration Sources

Claude Setup doesn't include any organization-specific configuration. Instead, it fetches configuration from sources you specify:

```json
{
  "sources": [
    {
      "name": "company-config",
      "type": "github",
      "repo": "your-org/claude-config",
      "ref": "main"
    }
  ]
}
```

**Supported source types:**
- **GitHub**: Public or private repositories
- **Zip**: HTTP/HTTPS URLs to zip files
- **Local**: Local filesystem paths

### Configuration Structure

Your configuration repository should follow this structure:

```
your-org/claude-config/
├── manifest.json          # Category definitions
├── core/
│   ├── CLAUDE.md          # Main instructions
│   ├── settings.json      # Team settings
│   └── statusline.sh      # Status line script
├── agents/                # Agent definitions
├── rules/                 # Team guidelines
├── commands/              # Custom commands
└── plugins/
    └── required.json      # Required plugins
```

See `examples/config-template/` for a complete template.

### Plugins, Marketplaces and Retired Files

A config repo can ship skills and agents as Claude Code plugins from a plugin
marketplace instead of as copied files.

- **`plugins/required.json`** entries may declare the marketplace a plugin comes
  from. If Claude Code doesn't know that marketplace yet, claude-setup runs
  `claude plugin marketplace add <source>` before `claude plugin install <plugin>`.
  `source` is a GitHub `owner/repo`, a git or https URL, or a local path.
  Entries without `marketplace` still work as before.

```json
[
  {
    "name": "team-skills@team-tools",
    "description": "Team skills and agents",
    "marketplace": {"name": "team-tools", "source": "example-org/team-config"}
  },
  {
    "name": "ralph-loop@claude-plugins-official",
    "description": "Entry without a marketplace: the marketplace must already be known"
  }
]
```

- **`extraKnownMarketplaces`** in the team `settings.json` is merged into the
  user's settings by marketplace name: the team entry wins for the same name and
  the user's other marketplaces are kept.
- **`claude-setup update`** installs updated files, then refreshes each team
  marketplace (`claude plugin marketplace update <name>`), installs missing
  required plugins and updates installed ones (`claude plugin update <plugin>`).
  This also runs when the config files are already up to date. Plugin failures
  are reported but don't fail the update. Use `--skip-plugins` to skip them, or
  `claude-setup plugins --update` to run only the plugin steps.
- **`"retired"`** in `manifest.json` lists paths (relative to `~/.claude`) the
  team no longer ships, such as skills that moved into a plugin:

  ```json
  {
    "version": "1.0.0",
    "retired": ["skills/old-skill", "agents/old-agent.md"],
    "categories": [...]
  }
  ```

  `install` and `update` **move** these into an archive folder; nothing is
  deleted (see below). Only paths inside `~/.claude/skills/`,
  `~/.claude/agents/` or `~/.claude/commands/` can be retired, and only when
  none of the folders above them is a symlink. Everything else is refused and
  never touched.

#### The archive folder: `~/.claude/archived/`

When a retired path is still on your machine, claude-setup moves it to:

```
~/.claude/archived/<timestamp>/<original path>
```

For example, `~/.claude/skills/old-skill/` becomes
`~/.claude/archived/2026-01-31-142501/skills/old-skill/`.

- **What gets moved:** only the paths listed under `"retired"` in the team
  manifest that still exist in `~/.claude`. Files, directories and symlinks
  are moved as they are; a symlink stays a symlink and its target is untouched.
- **Why move instead of delete:** if the old copy stayed in `skills/` or
  `agents/`, Claude Code would load it next to the plugin version and you'd
  have duplicates. Moving it avoids that without deleting anything you might
  have changed locally. Claude Code doesn't load anything from `archived/`.
- **Before anything moves:** `claude-setup update` lists each path and its
  destination and asks for confirmation (`--yes` skips the question).
  Answering no cancels the whole update ("Update cancelled; nothing
  changed"): no files are installed, no backup is made and plugins aren't
  touched. Ctrl-C does the same with exit code 130.
  `claude-setup install --dry-run` and `claude-setup update --check` show the
  same list without changing anything.
- **Where it went:** the update summary prints the archive folder, and
  `claude-setup status` lists retired paths still present and earlier archive
  folders.
- **How to get something back:**
  - `claude-setup rollback` moves the items archived by that update back to
    their original paths. If something already exists at the original path it
    is left alone and the conflict is reported; nothing is overwritten.
  - Or move it back by hand, e.g.
    `mv ~/.claude/archived/2026-01-31-142501/skills/old-skill ~/.claude/skills/`.
- **Cleaning up:** once you're happy with the plugin version, it's safe to
  delete `~/.claude/archived/` (or any folder inside it). claude-setup never
  deletes it for you.

## 📚 Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| [README-PUBLIC.md](README-PUBLIC.md) | This file - Overview and quick start | Everyone |
| [ADMIN-GUIDE.md](ADMIN-GUIDE.md) | Complete guide for setting up sources | Administrators |
| [USAGE.md](USAGE.md) | Interactive menu guide | End users |
| [UPDATING.md](UPDATING.md) | How to receive and install updates | End users |
| [MAINTAINING.md](MAINTAINING.md) | How to maintain and distribute updates | Administrators |
| [examples/](examples/) | Templates and examples | Administrators |

## 🔧 Configuration Sources

### GitHub Repository (Recommended)

**Best for:** Version control, team collaboration, easy updates

```bash
claude-setup init --github your-org/claude-config
```

**For private repos:**
```bash
export GITHUB_TOKEN=ghp_your_token_here
claude-setup init --github your-org/private-config
```

### Zip File

**Best for:** Simple distribution, no git required

```bash
claude-setup init --zip https://releases.example.com/claude-config.zip
```

### Local Directory

**Best for:** Development, testing, custom configs

```bash
claude-setup init --local ~/my-claude-config
```

### Multiple Sources

For advanced use cases, edit `~/.claude/sources.json`:

```json
{
  "sources": [
    {
      "name": "company-base",
      "type": "github",
      "repo": "your-org/claude-config-base",
      "ref": "main"
    },
    {
      "name": "team-overrides",
      "type": "local",
      "path": "~/team-config"
    }
  ]
}
```

## 🎓 Examples

### Example 1: Using the Template

```bash
# Use the generic template included in the repo
claude-setup init --local examples/config-template
claude-setup install --all
```

### Example 2: Creating Your Own Config

Administrators can bootstrap a config from their working setup:

```bash
# Generate config from your ~/.claude
claude-setup create-config --output ~/my-org-config

# Review and customize
cd my-org-config
# Edit CLAUDE.md, add team rules, etc.

# Push to GitHub
git remote add origin https://github.com/your-org/claude-config.git
git push -u origin main

# Team members install
claude-setup init --github your-org/claude-config
claude-setup install --all
```

See [ADMIN-GUIDE.md](ADMIN-GUIDE.md#creating-config-from-existing-setup) for detailed instructions.

### Example 3: Enterprise Setup with Zip Distribution

```bash
# Admin: Create and host config
cd my-company-config
zip -r claude-config-v1.0.0.zip config/
aws s3 cp claude-config-v1.0.0.zip s3://my-bucket/releases/

# Team members: Use it
claude-setup init --zip https://my-bucket.s3.amazonaws.com/releases/claude-config-v1.0.0.zip
claude-setup install --all
```

## 🔄 Update Workflow

### For End Users

```bash
# Check for updates
claude-setup status

# Install updates
claude-setup update

# Or interactive
claude-setup  # → Select "Check for Updates"
```

### For Administrators

```bash
# Update config
cd your-org/claude-config
vim config/rules/new-rule.md
git add config/
git commit -m "feat: add new rule"
git push

# Notify team
# "New config available! Run: claude-setup update"
```

The tool automatically detects changes and prompts users to update.

## 🛡️ Security

- ✅ No company-specific config in public repo
- ✅ Support for private GitHub repos with tokens
- ✅ HTTPS-only for zip downloads
- ✅ Local filesystem access for air-gapped environments
- ✅ Automatic backups before all changes
- ✅ Settings merge preserves user customizations

## 🤝 Contributing

This is an open-source project! Contributions welcome.

**Areas for contribution:**
- Additional source types (GitLab, Bitbucket, S3, etc.)
- YAML support for sources.json
- Configuration validation
- Additional template examples
- Documentation improvements

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

[MIT License](LICENSE)

## 🙋 Support

**For tool issues:**
- GitHub Issues: https://github.com/travis-jorge/claude-code-config/issues
- Documentation: README.md, ADMIN-GUIDE.md

**For your organization's config:**
- Contact your administrator
- Check your config repo's README

## 🎉 Success Stories

Organizations using Claude Setup:

- **Tyler Technologies**: Managing Claude Code config for 20+ developers across multiple teams
- **Your Company**: [Submit a PR to add yours!]

## 🚦 Status

- ✅ Production ready
- ✅ 36 passing tests
- ✅ Complete documentation
- ✅ Multi-source support
- ✅ Interactive menu
- ✅ Automatic updates

---

**Made with ❤️ for teams using Claude Code**
