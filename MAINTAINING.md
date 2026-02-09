# Maintaining Claude Setup

## 🔧 How to Provide Configuration Updates

### Quick Reference

```bash
# 1. Update configuration files
vim config/rules/new-rule.md

# 2. Test locally
claude-setup install --all --dry-run

# 3. Commit and push
git add -A
git commit -m "feat: add new team rule for XYZ"
git push origin master

# 4. Notify team
# Post in Slack: "New config available! Run: git pull && claude-setup update"
```

---

## 📝 Step-by-Step Update Process

### Step 1: Identify What Needs Updating

Configuration is organized in `config/` directory:

```
config/
├── core/              # Core configuration
│   ├── CLAUDE.md      # Main instructions
│   ├── settings.json  # Team settings (with {{HOME}} template)
│   └── statusline.sh  # Status line script
│
├── agents/            # Agent definitions
│   ├── aws-agent.md
│   ├── code-reviewer-agent.md
│   ├── general-agent.md
│   └── project-manager-agent.md
│
├── rules/             # Team rules and guidelines
│   ├── agent-usage.md
│   ├── aws-access.md
│   └── ... (10 files)
│
├── commands/          # Custom commands
│   ├── *.md           # Command definitions
│   ├── *.sh           # Shell scripts
│   └── .github/       # GitHub workflows
│
└── plugins/
    └── required.json  # Required plugins list
```

### Step 2: Update Configuration Files

#### Example: Add a New Rule

```bash
# Create new rule file
vim config/rules/kubernetes.md
```

```markdown
# Kubernetes Management Rules

## When to Use EKS vs Local Kubernetes

- Use EKS for: Production workloads, team collaboration
- Use Local (minikube): Local development, testing

## Required Tools

- kubectl version 1.28+
- aws-iam-authenticator
- helm 3.x

## Best Practices

1. Always use namespaces
2. Label all resources
3. Use secrets for sensitive data
```

#### Example: Update Existing Rule

```bash
# Edit existing rule
vim config/rules/aws-access.md

# Add new AWS profile
```

#### Example: Add a New Command

```bash
# Create new command
vim config/commands/k8s-deploy.md
```

```markdown
<command-name>k8s-deploy</command-name>

# Kubernetes Deployment Helper

Deploy application to Kubernetes cluster.

## Usage

When user requests Kubernetes deployment, follow these steps:

1. Verify cluster connection
2. Apply manifests in correct order
3. Wait for rollout completion
4. Verify deployment health
```

#### Example: Update Core Settings

```bash
# Edit team settings
vim config/core/settings.json
```

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash",
      "Read",
      "Glob",
      "Grep",
      "LS"
    ]
  },
  "model": "opusplan",
  "statusLine": {
    "type": "command",
    "command": "bash {{HOME}}/.claude/statusline.sh"
  },
  "enabledPlugins": {
    "ralph-loop@claude-plugins-official": true,
    "security-guidance@claude-plugins-official": true,
    "code-review@claude-plugins-official": true,
    "terraform-skill@antonbabenko": true,
    "new-plugin@example": true  // ← Add new plugin
  },
  "alwaysThinkingEnabled": true
}
```

**Important**: Keep the `{{HOME}}` template variable in paths!

#### Example: Add Required Plugin

```bash
# Update plugin requirements
vim config/plugins/required.json
```

```json
[
  {
    "name": "ralph-loop@claude-plugins-official",
    "description": "Ralph Loop automation plugin"
  },
  {
    "name": "new-plugin@example",
    "description": "New required plugin"
  }
]
```

### Step 3: Update manifest.json (if needed)

**Only needed if you're adding a NEW category or changing file structure.**

```bash
vim config/manifest.json
```

Most updates don't require manifest changes because:
- ✅ Adding files to existing categories: **Auto-discovered**
- ✅ Updating existing files: **Auto-detected**
- ❌ Creating new category: **Must update manifest**

### Step 4: Test Locally

```bash
# Preview what would change
claude-setup install --all --dry-run

# Check that files are detected
claude-setup status

# Actually test the install in a test directory (optional)
claude-setup install --all --target /tmp/test-claude
```

### Step 5: Commit Changes

```bash
# Check what changed
git status
git diff

# Add changes
git add config/

# Commit with clear message
git commit -m "feat: add Kubernetes management rules and best practices"

# Or for updates
git commit -m "fix: update AWS access rules with new profile information"

# Or for new commands
git commit -m "feat: add k8s-deploy command for Kubernetes deployments"
```

**Commit message patterns:**
- `feat: <description>` - New feature/rule/command
- `fix: <description>` - Bug fix or correction
- `docs: <description>` - Documentation update
- `chore: <description>` - Maintenance task

### Step 6: Push to Repository

```bash
# Push to master (or main)
git push origin master

# Or create a PR for team review
git checkout -b feat/kubernetes-rules
git push origin feat/kubernetes-rules
# Then create PR in GitHub
```

### Step 7: Notify Team

**Slack/Teams message:**
```
📦 New Claude Code configuration available!

What changed:
• Added Kubernetes management rules
• Updated AWS access profiles

To update:
cd ~/claude-setup && git pull && claude-setup update

Or interactively:
claude-setup → Check for Updates
```

---

## 🔍 How Update Detection Works

The tool uses **content-based hashing**:

1. When you change ANY file in `config/`, the hash changes
2. Team members' installed hash no longer matches
3. `claude-setup status` shows "⚠ Updates available"
4. `claude-setup update` installs the new config

**Example:**

```bash
# Maintainer changes config/rules/aws-access.md
# Config hash changes from: 828bdd64df4d → 9a3f2e1c8b7d

# Team member runs:
$ claude-setup status

Installation Status:
  Installed: 828bdd64df4d  ← Old hash
  Available: 9a3f2e1c8b7d  ← New hash
  Status: ⚠ Updates available
```

---

## 📋 Common Update Scenarios

### Scenario 1: Add a New Team Rule

```bash
# 1. Create the rule file
cat > config/rules/new-rule.md << 'EOF'
# New Rule Title

Content here...
EOF

# 2. Test
claude-setup install --category rules --dry-run

# 3. Commit and push
git add config/rules/new-rule.md
git commit -m "feat: add new team rule for XYZ"
git push

# 4. Notify team
```

### Scenario 2: Update Team Settings

```bash
# 1. Edit settings
vim config/core/settings.json

# 2. Test locally first
cp ~/.claude/settings.json ~/.claude/settings.json.backup
claude-setup install --category core

# 3. Verify your settings still work
# Check Claude Code still starts properly

# 4. If good, commit
git add config/core/settings.json
git commit -m "feat: add new plugin to team settings"
git push

# 5. Notify team with warning
# "⚠️ Settings update - will merge with your existing settings"
```

### Scenario 3: Add a New Command

```bash
# 1. Create command file
vim config/commands/new-command.md

# 2. Test it works
claude-setup install --category commands
# Test the new command in Claude Code

# 3. Commit
git add config/commands/new-command.md
git commit -m "feat: add new-command for doing XYZ"
git push
```

### Scenario 4: Update Agent Definition

```bash
# 1. Edit agent
vim config/agents/aws-agent.md

# 2. Test
claude-setup install --category agents --dry-run

# 3. Commit
git add config/agents/aws-agent.md
git commit -m "fix: update aws-agent with new tool instructions"
git push
```

### Scenario 5: Bulk Update (Multiple Categories)

```bash
# 1. Make all your changes
vim config/rules/rule1.md
vim config/rules/rule2.md
vim config/commands/cmd1.md
vim config/agents/agent1.md

# 2. Test everything
claude-setup install --all --dry-run

# 3. Commit all at once
git add config/
git commit -m "feat: major update with new rules, commands, and agent improvements"
git push

# 4. Notify with detailed changelog
```

---

## 🧪 Testing Updates Before Distribution

### Test Plan

1. **Dry Run Test**
   ```bash
   claude-setup install --all --dry-run
   ```
   Verify correct files are marked as "Updated"

2. **Fresh Install Test** (optional but recommended)
   ```bash
   # Test on a clean directory
   rm -rf /tmp/test-claude
   mkdir -p /tmp/test-claude
   # Manually copy files or use install with --target
   ```

3. **Update Test**
   ```bash
   # Install current version first
   git checkout HEAD~1
   claude-setup install --all

   # Then update to new version
   git checkout master
   claude-setup status  # Should show updates available
   claude-setup update
   ```

4. **Settings Merge Test**
   ```bash
   # Ensure settings merge preserves user customizations
   # Check that your test customizations survive the update
   ```

---

## 📊 Version Tracking

The tool automatically tracks:
- Tool version: `1.0.0` (in `src/claude_setup/__init__.py`)
- Config hash: `828bdd64df4d` (computed from all files)
- Install date: `2026-02-07T23:08:13`
- Categories: `['core', 'agents', 'rules', 'commands']`

This is stored in `~/.claude/.claude-setup-version.json` on each user's machine.

---

## 🚨 Breaking Changes

If you make **breaking changes**, increment the version and communicate clearly:

```bash
# 1. Update version
vim src/claude_setup/__init__.py
# Change: __version__ = "1.1.0"

# 2. Update changelog
vim CHANGELOG.md

# 3. Commit
git commit -m "feat!: breaking change - new settings format"

# 4. Notify team with BREAKING CHANGE label
```

**What counts as breaking:**
- Removing configuration files
- Changing settings.json schema
- Removing required plugins
- Renaming categories

**Not breaking:**
- Adding new files
- Updating existing files
- Adding new plugins
- Adding new rules/commands

---

## 📝 Update Checklist

Before pushing updates:

- [ ] Test locally with `--dry-run`
- [ ] Verify settings merge preserves user customizations
- [ ] Check that no secrets/credentials are in config files
- [ ] Write clear commit message
- [ ] Update CHANGELOG.md if significant change
- [ ] Notify team with clear instructions
- [ ] Monitor Slack for questions after rollout

---

## 🎯 Quick Command Reference

```bash
# Test your changes
claude-setup install --all --dry-run
claude-setup status

# Commit pattern
git add config/
git commit -m "feat: description"
git push

# Team update command
git pull && claude-setup update
```

That's it! The tool handles version tracking, hash comparison, and update detection automatically. You just need to:
1. Update files in `config/`
2. Commit and push
3. Tell team to run `git pull && claude-setup update`
