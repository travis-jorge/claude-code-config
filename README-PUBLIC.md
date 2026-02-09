# Claude Setup

**A flexible, organization-agnostic CLI tool for managing Claude Code team configuration.**

Perfect for teams who want to standardize their Claude Code setup across developers while keeping control of their configuration.

## ✨ Features

- 🎨 **Interactive Menu** - Navigate all features with arrow keys
- 🔌 **Pluggable Sources** - GitHub repos, zip files, or local directories
- 📦 **Category-based Installation** - Install only what you need
- 💾 **Smart Settings Merge** - Preserve user customizations
- 🔄 **Automatic Backups** - Safe, reversible updates
- 🔌 **Plugin Management** - Auto-detect and install required plugins
- 🎯 **Update Detection** - Know when new config is available
- 🎨 **Rich Terminal UI** - Beautiful, informative output

## 🚀 Quick Start

### For Team Members (Using Existing Config)

Your admin should provide you with either a setup script or source configuration.

**Option 1: Using setup script**
```bash
# Run the script provided by your admin
bash setup-claude.sh
```

**Option 2: Manual setup**
```bash
# 1. Install tool
git clone https://github.com/anthropics/claude-setup.git
cd claude-setup
pip install -e .

# 2. Initialize with your organization's config
claude-setup init --github your-org/claude-config

# 3. Install configuration
claude-setup install --all

# 4. Check plugins
claude-setup plugins
```

### For Administrators (Setting Up for Your Team)

See **[ADMIN-GUIDE.md](ADMIN-GUIDE.md)** for complete instructions.

**TL;DR:**
1. Copy `examples/config-template/` to create your config repo
2. Customize for your team
3. Push to GitHub (or host as zip)
4. Team uses `claude-setup init --github your-org/claude-config`

## 📖 Usage

### Interactive Menu (Recommended)

Simply run without arguments:
```bash
claude-setup
```

Navigate with arrow keys through:
- 📦 Install Configuration
- 📊 Check Installation Status
- 🔌 Manage Plugins
- 💾 View Backups
- ⏮️ Rollback to Backup
- 🔄 Check for Updates

### Command Line

```bash
# Initialize sources
claude-setup init --github your-org/claude-config

# Install everything
claude-setup install --all

# Check status
claude-setup status

# Update to latest
claude-setup update

# Manage plugins
claude-setup plugins

# View backups
claude-setup backups

# Rollback if needed
claude-setup rollback
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
# Set your GitHub personal access token
export GITHUB_TOKEN=ghp_your_token_here

# The init command will automatically detect GITHUB_TOKEN
# and configure sources.json to use it
claude-setup init --github your-org/private-config
```

The token will be stored as `${GITHUB_TOKEN}` in `~/.claude/sources.json` and expanded at runtime. This keeps your token secure and out of config files.

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
      "ref": "main",
      "token": "${GITHUB_TOKEN}"
    },
    {
      "name": "team-overrides",
      "type": "local",
      "path": "~/team-config"
    }
  ]
}
```

**Environment variable expansion:** Use `${VAR_NAME}` or `$VAR_NAME` syntax in any string value. The tool will expand these at runtime using your shell environment.

## 🎓 Examples

### Example 1: Using Tyler Technologies Config

```bash
# Use the example config included in the repo
claude-setup init --local examples/tyler-tech-config
claude-setup install --all
```

### Example 2: Creating Your Own Config

```bash
# 1. Copy template
cp -r examples/config-template/ my-company-config/
cd my-company-config/

# 2. Customize
vim config/core/CLAUDE.md
vim config/core/settings.json

# 3. Push to GitHub
git init
git add .
git commit -m "Initial config"
git remote add origin git@github.com:my-org/claude-config.git
git push -u origin main

# 4. Use it
claude-setup init --github my-org/claude-config
claude-setup install --all
```

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
- GitHub Issues: https://github.com/anthropics/claude-setup/issues
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
