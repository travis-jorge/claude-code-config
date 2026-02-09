# Configuration Template

This is a template structure for creating your own Claude Code configuration repository.

## Structure

```
config/
├── manifest.json          # Required: Defines categories and file mappings
├── core/                  # Core configuration
│   ├── CLAUDE.md          # Main instructions file
│   ├── settings.json      # Team settings (with {{HOME}} template support)
│   └── statusline.sh      # Status line script
├── agents/                # Optional: Agent definitions
├── rules/                 # Optional: Team rules and guidelines
├── commands/              # Optional: Custom commands
└── plugins/               # Optional: Required plugins list
    └── required.json
```

## Getting Started

1. **Copy this template** to create your own config repository
2. **Customize** the files for your team:
   - Edit `core/CLAUDE.md` with your guidelines
   - Update `core/settings.json` with your team settings
   - Add rules in `rules/` directory
   - Add custom commands in `commands/` directory
3. **Create a GitHub repository** (public or private)
4. **Configure sources.json** to point to your repo
5. **Distribute** to your team

## Using This Template

### Option 1: GitHub Repository (Recommended)

```bash
# 1. Create repo from this template
# 2. Customize files
git add .
git commit -m "Initial config"
git push

# 3. Team members configure sources.json:
{
  "sources": [
    {
      "name": "company-config",
      "type": "github",
      "repo": "your-org/claude-config",
      "ref": "main",
      "path": "."
    }
  ]
}

# 4. Install
claude-setup init --source sources.json
claude-setup install --all
```

### Option 2: Zip File Distribution

```bash
# 1. Create zip
zip -r claude-config.zip config/

# 2. Host on web server or cloud storage
# 3. Team members configure:
{
  "sources": [
    {
      "name": "company-config",
      "type": "zip",
      "url": "https://example.com/claude-config.zip"
    }
  ]
}
```

### Option 3: Local Development

```bash
# For testing or local customization
{
  "sources": [
    {
      "name": "local-config",
      "type": "local",
      "path": "~/my-claude-config"
    }
  ]
}
```

## Manifest.json Structure

The `manifest.json` file defines your configuration categories:

```json
{
  "version": "1.0.0",
  "categories": [
    {
      "name": "core",
      "description": "Core configuration files",
      "target_dir": ".claude",
      "install_type": "merge",
      "files": [...]
    }
  ]
}
```

### Install Types

- **merge**: Smart merge (for settings.json)
- **overwrite**: Replace existing files
- **discover**: Auto-discover files in directory
- **check**: Validation only (for plugins)

### File Entry Fields

```json
{
  "src": "core/file.md",      // Source path in config repo
  "dest": "file.md",          // Destination in ~/.claude
  "merge": false,             // Smart merge vs overwrite
  "executable": false,        // Set executable bit
  "template": false           // Resolve {{HOME}} and other variables
}
```

## Template Variables

Use these in your configuration files:

- `{{HOME}}` - User's home directory

Example in `settings.json`:
```json
{
  "statusLine": {
    "command": "bash {{HOME}}/.claude/statusline.sh"
  }
}
```

## Best Practices

1. **Version your config**: Use git tags for releases
2. **Document changes**: Maintain a CHANGELOG.md
3. **Test updates**: Use `--dry-run` before applying
4. **Start minimal**: Add categories as needed
5. **Use comments**: JSON doesn't support comments, but add README files
6. **Secure secrets**: Never commit tokens or passwords

## Example Repositories

Looking for real-world examples? Check these out:
- Submit a PR to add your organization's public config example here!

## Support

For help with claude-setup tool:
- GitHub Issues: https://github.com/your-org/claude-setup/issues
- Documentation: README.md
