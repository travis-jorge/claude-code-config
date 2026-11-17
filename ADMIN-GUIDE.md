# Admin Guide: Setting Up Claude Setup for Your Organization

This guide is for administrators who want to set up `claude-setup` for their team.

## Overview

`claude-setup` is a generic tool that can work with **any** configuration source. You need to:

1. Create your configuration repository
2. Distribute the tool to your team
3. Configure the source location

## Quick Start (5 Minutes)

### Step 1: Create Your Config Repository

**Option A: From your existing setup (Recommended)**

If you already have a configured `~/.claude` setup that you want to share with your team:

```bash
claude-setup create-config --output ~/my-claude-config
```

This will:
- Scan your `~/.claude` directory
- Guide you through selecting what to include
- Separate team settings from personal settings
- Generate a properly structured config repo

**Option B: From template**

If you're starting from scratch:

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

## Creating Config from Existing Setup

The easiest way to create a team config is to use the `create-config` command, which bootstraps a new config repo from your existing `~/.claude` setup.

### Interactive Wizard

Run the wizard to walk through the process:

```bash
claude-setup create-config
```

Or use it from the main menu:

```bash
claude-setup
# Select "🏗️ Create Config Repo"
```

### What the Wizard Does

1. **Backs up your ~/.claude** - Creates a safety backup before any operations
2. **Scans your setup** - Finds all files in your `~/.claude` directory
3. **Classifies files** - Groups files into categories (core, agents, rules, commands)
4. **Separates settings** - Distinguishes team settings from personal settings
5. **Lets you customize** - Choose what to include, edit permissions and plugins
6. **Generates the repo** - Creates a properly structured config repository
7. **Initializes git** - Optionally sets up a git repository

### Settings Classification

The wizard automatically separates **team settings** from **personal settings**:

**Team Settings (included in config):**
- `model` - Default model for the team
- `statusLine` - Team's custom status line
- `alwaysThinkingEnabled` - Team preference for thinking display
- `permissions.allow` - Commands the team can use freely
- `enabledPlugins` - Plugins required for the team

**Personal Settings (excluded from config):**
- `permissions.deny` - User's blocked commands
- `permissions.ask` - User's prompt-on-use commands
- `feedbackSurveyState` - User's survey state
- Custom user preferences

This ensures that team members keep their personal preferences while adopting team standards.

### Command Line Options

```bash
# Generate with specific output directory
claude-setup create-config --output ~/my-team-config

# Preview without creating files
claude-setup create-config --dry-run

# Skip git initialization
claude-setup create-config --no-git

# Non-interactive: include all categories
claude-setup create-config --all --output ~/my-config
```

### After Generation

Once the config repo is created:

1. **Review the generated files** in the output directory
2. **Customize as needed** - Edit CLAUDE.md, add rules, etc.
3. **Commit to git** (if not auto-initialized):
   ```bash
   cd my-claude-config
   git init
   git add .
   git commit -m "Initial team config"
   ```
4. **Push to GitHub** - Share with your team
5. **Team installs** using the source URL

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
- `token` (optional): GitHub PAT for private repos. Use `${GITHUB_TOKEN}` or `$GITHUB_TOKEN` to reference environment variables.

**For private repositories:**
```bash
# Set your GitHub token
export GITHUB_TOKEN=ghp_your_token_here

# Run init - it will automatically detect GITHUB_TOKEN
# and add "token": "${GITHUB_TOKEN}" to sources.json
claude-setup init --github your-org/private-config

# Token is expanded at runtime, keeping it secure
```

**Environment variable expansion:** Any string value in sources.json can reference environment variables using `${VAR_NAME}` or `$VAR_NAME` syntax. The tool expands these at runtime, allowing you to keep secrets out of config files.

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
- [ ] List required plugins in `plugins/required.json` (optionally with their `marketplace`)
- [ ] List removed files under `"retired"` in `manifest.json` when you stop shipping them
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

### Distributing Skills and Agents as Plugins

If your config repo is also a Claude Code plugin marketplace, engineers can get
skills and agents as plugins instead of copied files.

**1. Declare the marketplace on required plugins** (`plugins/required.json`):

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

| Field | Required | Meaning |
|-------|----------|---------|
| `name` | yes | Plugin id, normally `plugin@marketplace` |
| `description` | yes | Shown by `claude-setup plugins` |
| `marketplace.name` | with `marketplace` | Marketplace name. Must equal the `name` in that marketplace's own `.claude-plugin/marketplace.json` (that is what Claude Code records in `known_marketplaces.json`; otherwise every run tries to add it again) and should match the `@` suffix (a mismatch is warned about) |
| `marketplace.source` | with `marketplace` | Passed to `claude plugin marketplace add`: GitHub `owner/repo`, git/https URL, or path. A path starting with `./` or `../` is resolved against the config repo; use an absolute path otherwise (a bare `owner/repo` is always GitHub) |

Before installing a plugin, claude-setup reads
`~/.claude/plugins/known_marketplaces.json`. If the marketplace isn't listed
(or the file is missing or unreadable), it runs
`claude plugin marketplace add <source>`, then `claude plugin install <name>`.
Entries without `marketplace` behave exactly as before.

**2. Optionally declare it in team settings.** `extraKnownMarketplaces` in
`core/settings.json` is merged into each user's settings keyed by marketplace
name. The team entry wins for the same name; the user's own marketplaces are kept.

```json
{
  "extraKnownMarketplaces": {
    "team-tools": {"source": {"source": "github", "repo": "example-org/team-config"}}
  }
}
```

**3. What `claude-setup update` does:**

1. Updates config files (when the config changed, or when retired paths are
   still present), moving retired paths into `~/.claude/archived/` after
   confirmation
2. Refreshes each marketplace declared in `required.json`
   (`claude plugin marketplace update <name>`, or `add` if it isn't known yet)
3. Installs missing required plugins (`claude plugin install <plugin>`)
4. Updates required plugins that were already installed (`claude plugin update <plugin>`)

Steps 2-4 run even when the config files are already up to date, and only when
the `plugins` category is installed. Failures are reported and don't fail the
update. `--skip-plugins` skips them; `claude-setup plugins --update` runs only
them. claude-setup never passes `-y`, so a plugin that needs a
marketplace-declared command to be confirmed has to be installed by hand.
Git is run with `GIT_TERMINAL_PROMPT=0`, plus `GIT_SSH_COMMAND="ssh -o
BatchMode=yes"` when you have no SSH override of your own (`GIT_SSH_COMMAND`,
`GIT_SSH` or `git config core.sshCommand`), so a private marketplace that
needs credentials fails instead of hanging. Each `claude` call runs in its own
process group, which is killed on timeout or Ctrl-C; after one marketplace
operation times out, the remaining marketplace steps are skipped. Plugin names and marketplace
names/sources starting with `-` are rejected.

**4. Retire the copied files.** When a skill or agent moves into a plugin, list
the old path in `manifest.json` so the copied version is moved out of the way
on engineers' machines (otherwise Claude Code loads both):

```json
{
  "version": "1.0.0",
  "retired": ["skills/old-skill", "agents/old-agent.md"],
  "categories": [...]
}
```

- Paths are relative to `~/.claude` and may be files, directories or symlinks.
- Nothing is deleted. `install` and `update` **move** each path (a rename, so
  a symlink is moved as a symlink) to
  `~/.claude/archived/<timestamp>/<original path>`. If that name is taken, a
  `-1`, `-2`, ... suffix is added instead of overwriting. Claude Code doesn't
  load anything from `archived/`.
- `update` lists each path with its destination and asks before moving
  (`--yes` / `-y` / `--force` skips the question). Declining (or EOF)
  cancels the whole update with exit code 0 and "Update cancelled; nothing
  changed": no install, backup, settings merge, version stamp or plugin
  steps. Ctrl-C does the same with exit code 130. `install --dry-run` shows
  them with status `Archive`;
  `update --check` and `status` list retired paths still present, and `status`
  also lists earlier archive folders.
- Rollback: each archive folder has an `archive-manifest.json` journal. Each
  item is recorded as `pending` before it is moved and `done` after, and the
  file is replaced atomically and never written through a symlink. The backup
  taken by the same install records the archive folder (`"archive"` in its
  `backup-manifest.json`). `claude-setup rollback` uses that to move items back
  to their original paths, skipping (and reporting) any path that already
  exists, and copes with runs interrupted part-way (items never moved are
  reported as missing). It only accepts a real (non-symlink) folder directly
  inside a real `~/.claude/archived/`, and validates every item: the original
  must pass the same rules as retiring, and the archived path must stay inside
  the run folder with no symlinked component except the item itself.
  Malformed entries are reported and skipped. Engineers can also move items
  back by hand, or delete `~/.claude/archived/` once they're happy.
- Allowlist (fixed): an entry must be strictly inside `skills/`, `agents/` or
  `commands/`, matched exactly (case-sensitive, after NFC normalisation), so
  `SKILLS/x` is refused. Manifest categories do not extend this list. Everything else is
  refused and never touched, including `rules/`, `projects/`, `plugins/`,
  `todos/`, `settings*.json`, `history.jsonl`, credentials, `archived/`,
  `backups/`, `sources/` and the allowlisted directories themselves.
- Symlinks: refused if any existing folder between `~/.claude` and the item is
  a symlink, including `skills/`, `agents/` or `commands/` themselves (for
  example a dotfiles-managed `skills/` symlink). Only the item itself may be a
  symlink; it is moved as a link. Archiving is refused if
  `~/.claude/archived` is a symlink.
- Also refused: absolute paths, backslashes, anything containing `..` or
  control characters, paths resolving outside the allowlisted folder, the
  config source directory, any `local` source path in `sources.json`, and any
  path that is or contains a file the manifest installs. Path parts may not
  start or end with whitespace. Overlap and protection checks ignore letter
  case and Unicode normalisation (NFC/NFD), so they only ever refuse more. When one entry is inside
  another (`skills/x` and `skills/x/y`), only the outer one is moved. If any
  manifest file entry is malformed (e.g. `"dest": null`), all retired entries
  are refused and `install`/`update` stop with an error.
- Backups and rollback: backups made in the same second get a `-1`, `-2`, ...
  suffix instead of sharing a folder. `rollback <id>` only accepts the plain
  name of an existing backup folder. A `backup-manifest.json` that isn't valid
  (bad JSON, too deeply nested, `created_at` not an ISO timestamp,
  `categories` not a list of strings) marks the backup invalid; it is listed
  but never picked as "most recent". Restore only reads files inside the
  backup folder (no symlinks) and only writes inside `~/.claude`: a file whose
  destination is under a symlinked folder is skipped and reported. If the
  destination itself is a symlink (for example a dotfiles-linked
  `CLAUDE.md`), it is written through only when it's a file the current
  manifest installs; otherwise it is skipped.
- Residual risk: a move checks that the destination is free and then
  renames, so another process creating that path in between could be
  overwritten. An interrupted run can leave a hidden
  `.archive-manifest.json.*.tmp` file in the archive folder, which is safe to
  delete.

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

### 1. Create the config repo from your setup

```bash
# Use your existing configured ~/.claude
claude-setup create-config --output ~/acme-claude-config

cd acme-claude-config
```

### 2. Customize for your organization

Edit the generated files:
```bash
# Customize CLAUDE.md with company standards
cat >> config/core/CLAUDE.md << 'EOF'

## Acme Corp Coding Standards
- Use TypeScript for all new projects
- Follow ESLint rules
- Write tests for all features

## Security
- Never commit API keys
- Use vault for secrets
- Follow least-privilege access
EOF
```

### 3. Commit and push

```bash
git add .
git commit -m "Initial Acme Corp config"

# Create GitHub repo and push
gh repo create acme-corp/claude-config --private
git remote add origin git@github.com:acme-corp/claude-config.git
git push -u origin main
```

### 4. Create setup script for team

```bash
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
