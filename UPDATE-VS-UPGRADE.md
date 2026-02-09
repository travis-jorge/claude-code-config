# Update vs Upgrade

`claude-setup` has two different update mechanisms for two different things:

## `claude-setup upgrade` - Update the Tool

**What it updates**: The Python tool itself (core functionality)

**When to use**:
- New features added to the tool (like environment variable expansion)
- Bug fixes in the tool code
- New commands or CLI improvements

**What it does**:
1. Checks if you're behind the remote repository
2. Runs `git pull` to get latest code
3. Reinstalls the package with `pip install -e .`
4. Shows new version

**Example**:
```bash
# Check if tool upgrade is available
claude-setup upgrade --check

# Upgrade the tool
claude-setup upgrade
```

**User experience**: One command, automatic!

---

## `claude-setup update` - Update the Config

**What it updates**: Your team's configuration (CLAUDE.md, rules, settings, etc.)

**When to use**:
- Your admin updated team instructions
- New rules or agents added
- Settings or plugins changed

**What it does**:
1. Re-fetches config from your source (GitHub/zip/local)
2. Computes what changed (new/updated files)
3. Backs up existing config
4. Installs updated config files

**Example**:
```bash
# Check if config updates are available
claude-setup update --check

# Update config
claude-setup update
```

**User experience**: One command, automatic!

---

## Quick Reference

| Command | Updates | Source | Requires |
|---------|---------|--------|----------|
| `upgrade` | Tool code | Git repo where tool was installed | Git installation |
| `update` | Team config | Configured in `~/.claude/sources.json` | Valid source |

## Both Together

Typical update workflow when both are available:

```bash
# 1. Upgrade the tool first (new features)
claude-setup upgrade

# 2. Then update config (may use new features)
claude-setup update
```

## In the Interactive Menu

```
What would you like to do?
  📦 Install Configuration
  📊 Check Installation Status
  🔌 Manage Plugins
  💾 View Backups
  ⏮️  Rollback to Backup
  🔄 Check for Config Updates    ← Updates config from source
  ⬆️  Upgrade Tool               ← Upgrades tool code
  🚪 Exit
```

## For Admins

**Tool updates** (upgrade):
- Merge PRs to main branch
- Create GitHub releases with version tags
- Users run `claude-setup upgrade`

**Config updates** (update):
- Push changes to your config repo
- Users run `claude-setup update`
- Happens automatically via their configured source

## Architecture Diagram

```
claude-setup (Tool)                  Your Config Repo
┌──────────────────┐                ┌─────────────────┐
│  cli.py          │                │  CLAUDE.md      │
│  installer.py    │   Fetches      │  settings.json  │
│  sources.py      │ ────────────>  │  rules/*.md     │
│  ...             │                │  agents/*.md    │
└──────────────────┘                └─────────────────┘
       ▲                                     ▲
       │                                     │
   upgrade                               update
       │                                     │
    git pull                          git pull / fetch
    pip install                       (from source)
```

## Non-Git Installations

If installed via `pip install claude-setup` (not git clone):

```bash
# Upgrade tool
pip install --upgrade claude-setup

# Update config (same as before)
claude-setup update
```

The `upgrade` command will detect non-git installations and guide the user.
