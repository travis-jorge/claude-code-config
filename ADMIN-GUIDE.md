# Admin Guide: Setting Up Claude Setup for Your Organization

This guide is for administrators who want to set up `claude-setup` for their team.

## Overview

`claude-setup` is a generic tool that can work with **any** configuration source. You need to:

1. Create your configuration repository
2. Distribute the tool to your team
3. Configure the source location

## Quick Start (5 Minutes)

### Step 1: Create Your Config Repository

```bash
# Copy the template
cp -r examples/config-template/ my-claude-config/
cd my-claude-config/

# Customize for your team
vim config/core/CLAUDE.md
vim config/core/settings.json

# Initialize git
git init
git add .
git commit -m "Initial configuration"

# Push to GitHub (or GitLab, Bitbucket, etc.)
git remote add origin git@github.com:your-org/claude-config.git
git push -u origin main
```

### Step 2: Create sources.json

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

### Step 3: Distribute to Team

**Option A: Include sources.json in claude-setup repo**
```bash
# In your fork of claude-setup
cp sources.json .claude-setup-sources.json
git add .claude-setup-sources.json
git commit -m "Add company config source"
git push
```

**Option B: Provide setup script**
```bash
#!/bin/bash
cat > ~/.claude/sources.json << 'EOF'
{
  "sources": [{
    "name": "company-config",
    "type": "github",
    "repo": "your-org/claude-config",
    "ref": "main"
  }]
}
EOF

claude-setup install --all
```

---

## Configuration Sources

### Source Type: GitHub Repository

**Best for**: Teams using GitHub, version-controlled configs, collaborative editing

```json
{
  "name": "my-config",
  "type": "github",
  "repo": "your-org/claude-config",
  "ref": "main",
  "path": "config",
  "token": "${GITHUB_TOKEN}"
}
```

**Fields:**
- `repo` (required): `owner/repository` format
- `ref` (optional): Branch, tag, or commit SHA (default: `main`)
- `path` (optional): Subdirectory in repo containing config (default: `.`)
- `token` (optional): GitHub PAT for private repos (can use env var)

**For private repositories:**
```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### Source Type: Zip File (HTTP/HTTPS)

**Best for**: Simple distribution, no git required, can host anywhere

```json
{
  "name": "my-config",
  "type": "zip",
  "url": "https://releases.example.com/claude-config-v1.0.0.zip",
  "path": "config"
}
```

**Fields:**
- `url` (required): Direct download link to zip file
- `path` (optional): Subdirectory in zip containing config

**Hosting options:**
- GitHub Releases
- AWS S3 with presigned URLs
- Internal file server
- Cloud storage (Google Drive, Dropbox with direct links)

### Source Type: Local Path

**Best for**: Development, testing, custom per-machine configs

```json
{
  "name": "my-config",
  "type": "local",
  "path": "~/company-claude-config"
}
```

**Fields:**
- `path` (required): Absolute or `~` path to config directory

### Multiple Sources (Advanced)

Combine multiple sources for layered configuration:

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
      "type": "github",
      "repo": "your-org/claude-config-backend-team",
      "ref": "main"
    },
    {
      "name": "personal",
      "type": "local",
      "path": "~/.claude-personal"
    }
  ]
}
```

Sources are processed in order. Later sources can override earlier ones.

---

## Creating Your Configuration Repository

### Repository Structure

```
your-org/claude-config/
├── README.md              # Documentation for your team
├── CHANGELOG.md           # Track configuration changes
├── config/                # Configuration files
│   ├── manifest.json      # Required: Category definitions
│   ├── core/
│   │   ├── CLAUDE.md      # Main instructions
│   │   ├── settings.json  # Team settings
│   │   └── statusline.sh  # Status line script
│   ├── agents/            # Agent definitions (optional)
│   ├── rules/             # Team guidelines (optional)
│   ├── commands/          # Custom commands (optional)
│   └── plugins/           # Required plugins list
│       └── required.json
└── .gitignore            # Don't commit secrets!
```

### Customization Checklist

- [ ] Update `CLAUDE.md` with team guidelines
- [ ] Configure `settings.json` with team defaults
- [ ] Add team-specific rules in `rules/`
- [ ] Add custom commands in `commands/`
- [ ] List required plugins in `plugins/required.json`
- [ ] Write clear README for your team
- [ ] Add LICENSE file if open-sourcing

### Template Variables

Use these in your files:
- `{{HOME}}` - User's home directory

Example:
```json
{
  "statusLine": {
    "command": "bash {{HOME}}/.claude/statusline.sh"
  }
}
```

---

## Distribution Methods

### Method 1: Fork and Customize (Easiest)

```bash
# 1. Fork claude-setup repository
# 2. Add your sources.json
cp examples/sources.json .claude-setup-sources.json
vim .claude-setup-sources.json  # Update with your repo

# 3. Commit
git add .claude-setup-sources.json
git commit -m "Add company config source"
git push

# 4. Team members clone your fork
git clone git@github.com:your-org/claude-setup.git
cd claude-setup
pip install -e .
claude-setup install --all
```

### Method 2: Original Tool + External Config

```bash
# Team members use original tool
git clone git@github.com:travis-jorge/claude-code-config.git
cd claude-setup
pip install -e .

# But use your config
cat > ~/.claude/sources.json << 'EOF'
{
  "sources": [{
    "type": "github",
    "repo": "your-org/claude-config",
    "ref": "main"
  }]
}
EOF

claude-setup install --all
```

### Method 3: Setup Script (Automated)

```bash
#!/bin/bash
# setup-claude.sh - Distribute this to your team

set -e

echo "Installing claude-setup..."
git clone https://github.com/travis-jorge/claude-code-config.git ~/claude-setup
cd ~/claude-setup
pip install -e .

echo "Configuring company settings..."
mkdir -p ~/.claude
cat > ~/.claude/sources.json << 'EOF'
{
  "sources": [{
    "name": "company-config",
    "type": "github",
    "repo": "your-org/claude-config",
    "ref": "main"
  }]
}
EOF

echo "Installing configuration..."
claude-setup install --all

echo "Checking plugins..."
claude-setup plugins

echo "✅ Setup complete!"
echo "Run 'claude-setup' to access the interactive menu"
```

---

## Managing Updates

### For Administrators (Pushing Updates)

```bash
# 1. Update config files
cd your-org/claude-config
vim config/rules/new-rule.md

# 2. Test locally
claude-setup install --dry-run

# 3. Version and commit
git add config/
git commit -m "feat: add new security guidelines"
git tag v1.1.0
git push origin main --tags

# 4. Notify team
# Post in Slack: "New config available! Run: claude-setup update"
```

### For Team Members (Getting Updates)

```bash
# One command to update everything
claude-setup update

# Or interactive
claude-setup  # Select "Check for Updates"
```

The tool automatically:
- Detects config changes (hash-based)
- Downloads new config
- Creates backup before applying
- Merges settings intelligently
- Shows what changed

---

## Security Best Practices

### Never Commit Secrets

```bash
# .gitignore
*.key
*.pem
secrets.json
.env
*.token
```

### Use Environment Variables

For private repos:
```bash
# In sources.json
{
  "token": "${GITHUB_TOKEN}"
}

# Set in environment
export GITHUB_TOKEN=ghp_xxx
```

### Access Control

**GitHub:**
- Use private repositories for sensitive configs
- Grant read-only access to team members
- Use deploy keys or GitHub Apps for CI/CD

**Zip hosting:**
- Use presigned URLs with expiration
- Implement authentication if hosting internally
- Use HTTPS only

### Audit Trail

```bash
# Track who changed what
git log --all --oneline --graph
git blame config/core/settings.json
```

---

## Advanced Configuration

### Per-Environment Configs

```json
{
  "sources": [
    {
      "name": "base",
      "type": "github",
      "repo": "your-org/claude-config-base",
      "ref": "main"
    },
    {
      "name": "prod",
      "type": "github",
      "repo": "your-org/claude-config-prod",
      "ref": "main"
    }
  ]
}
```

### Version Pinning

Use tags instead of branches:
```json
{
  "ref": "v1.0.0"  // Instead of "main"
}
```

### Custom Manifest

You can have different category structures:
```json
{
  "categories": [
    {
      "name": "engineering",
      "description": "Engineering team configs",
      "target_dir": ".claude/engineering",
      "install_type": "overwrite",
      "files": [...]
    }
  ]
}
```

---

## Troubleshooting

### Source fetch fails

```bash
# Check sources config
cat ~/.claude/sources.json

# Manually test git clone
git clone https://github.com/your-org/claude-config /tmp/test

# Check permissions
ls -la ~/.claude/sources/
```

### Private repo authentication

```bash
# Option 1: HTTPS with token
export GITHUB_TOKEN=ghp_xxx

# Option 2: SSH (configure in sources)
{
  "type": "github",
  "repo": "your-org/claude-config",
  "ssh": true  // Uses git@github.com:
}
```

### Cache issues

```bash
# Clear cache and re-fetch
rm -rf ~/.claude/sources/
claude-setup install --all
```

---

## Example: Complete Setup for Acme Corp

```bash
# 1. Create config repo
gh repo create acme-corp/claude-config --private
git clone git@github.com:acme-corp/claude-config.git
cd claude-config

# 2. Copy template
cp -r /path/to/claude-setup/examples/config-template/* .

# 3. Customize
cat > config/core/CLAUDE.md << 'EOF'
# Acme Corp Claude Code Configuration

## Coding Standards
- Use TypeScript for all new projects
- Follow ESLint rules
- Write tests for all features

## Security
- Never commit API keys
- Use vault for secrets
- Follow least-privilege access
EOF

# 4. Commit and push
git add .
git commit -m "Initial Acme Corp config"
git push

# 5. Create setup script for team
cat > setup.sh << 'EOF'
#!/bin/bash
git clone https://github.com/travis-jorge/claude-code-config.git ~/claude-setup
cd ~/claude-setup
pip install -e .

mkdir -p ~/.claude
cat > ~/.claude/sources.json << 'SOURCES'
{
  "sources": [{
    "name": "acme-config",
    "type": "github",
    "repo": "acme-corp/claude-config",
    "ref": "main",
    "token": "${GITHUB_TOKEN}"
  }]
}
SOURCES

claude-setup install --all
echo "✅ Acme Corp Claude setup complete!"
EOF

chmod +x setup.sh

# 6. Distribute
# Email setup.sh to team or host on internal wiki
```

---

## Support

For questions about:
- **Tool issues**: GitHub Issues on claude-setup repo
- **Config structure**: This guide and examples/
- **Your team's config**: Contact your admin

For feature requests or bugs in claude-setup:
https://github.com/travis-jorge/claude-code-config/issues
