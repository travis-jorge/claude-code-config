# Getting Configuration Updates

## 🔄 For Team Members - How to Receive Updates

### Quick Update

```bash
# One-liner to update everything
cd ~/claude-setup && git pull && claude-setup update
```

---

## 📖 Step-by-Step Update Process

### Option 1: Interactive Menu (Recommended)

```bash
# 1. Pull latest changes from git
cd ~/claude-setup
git pull

# 2. Launch interactive menu
claude-setup

# 3. Select "🔄 Check for Updates"
#    - You'll see what changed
#    - Confirm to install

# 4. Done! Changes are applied
```

### Option 2: Command Line

```bash
# 1. Pull latest changes
cd ~/claude-setup
git pull

# 2. Check if updates are available
claude-setup status

# 3. Install updates
claude-setup update

# Or do it all in one command
cd ~/claude-setup && git pull && claude-setup update
```

---

## 🔍 Checking for Updates

### Method 1: Status Command

```bash
$ claude-setup status

Installation Status:
  Tool Version:
    Installed: 1.0.0
    Available: 1.0.0

  Configuration:
    Installed: 828bdd64df4d  ← Your current config
    Available: 9a3f2e1c8b7d  ← New config available

  Status:
    ⚠ Updates available        ← Updates are ready!
```

### Method 2: Update Check

```bash
$ claude-setup update --check

⚠ Updates are available. Run 'claude-setup update' to install.
```

### Method 3: Interactive Menu

```bash
$ claude-setup

[Select "🔄 Check for Updates"]

# Shows you what changed and offers to install
```

---

## 🎯 Update Scenarios

### Scenario 1: Regular Update (New Rules/Commands)

You'll see:
```
Installation Plan:
┌─────────────────────────────────┬───────────┬──────────┐
│ File                            │ Status    │ Action   │
├─────────────────────────────────┼───────────┼──────────┤
│ ~/.claude/rules/new-rule.md     │ New       │ Copy     │
│ ~/.claude/commands/new-cmd.md   │ New       │ Copy     │
│ ~/.claude/rules/updated-rule.md │ Updated   │ Overwrite│
└─────────────────────────────────┴───────────┴──────────┘
```

**What happens:**
- ✅ New files are added
- ✅ Updated files are overwritten
- ✅ Your files are backed up first
- ✅ Unchanged files are skipped

**Safe to proceed!** Your customizations in `settings.json` are preserved.

### Scenario 2: Settings Update

You'll see:
```
Installation Plan:
┌─────────────────────────────┬────────┬─────────────┐
│ File                        │ Status │ Action      │
├─────────────────────────────┼────────┼─────────────┤
│ ~/.claude/settings.json     │ Merge  │ Smart merge │
└─────────────────────────────┴────────┴─────────────┘
```

**What happens:**
- ✅ Team settings applied (model, statusLine, etc.)
- ✅ Your permissions preserved and merged
- ✅ Your custom plugins kept
- ✅ Your feedbackSurveyState preserved

**Example:**

Before update (your settings):
```json
{
  "model": "sonnet",
  "permissions": {
    "allow": ["Read", "Write"],
    "deny": ["Bash"]
  },
  "enabledPlugins": {
    "my-personal-plugin": true
  }
}
```

After update (merged):
```json
{
  "model": "opusplan",          ← Team standard applied
  "permissions": {
    "allow": ["Bash", "Read", "Write"],  ← Union of both
    "deny": ["Bash"]            ← Your deny preserved
  },
  "enabledPlugins": {
    "my-personal-plugin": true,  ← Your plugin kept
    "team-plugin": true          ← Team plugin added
  }
}
```

### Scenario 3: Plugin Update

You'll see:
```
Plugin Status:
  existing-plugin: ✓ Installed
  new-required-plugin: ✗ Not installed

Missing Plugins:
  • new-required-plugin: Description here

? Install missing plugins now? (Y/n)
```

**After update, check plugins:**
```bash
claude-setup plugins --install
```

---

## 🛡️ Safety Features

### Automatic Backups

Every update creates a backup:
```
~/.claude/backups/claude-setup-2026-02-07-230813/
```

If something goes wrong:
```bash
# View backups
claude-setup backups

# Restore immediately
claude-setup rollback
```

### Dry Run First (Optional)

```bash
# See what would change without applying it
git pull
claude-setup install --all --dry-run
```

### Smart Merge

Settings are **merged**, not overwritten:
- Team standards applied to core settings
- Your customizations preserved
- No data loss

---

## ❓ Common Questions

### Q: Will I lose my customizations?

**A:** No! Settings are intelligently merged:
- Your `permissions.deny` and `permissions.ask` are preserved
- Your personal plugins are kept
- Your `feedbackSurveyState` is preserved
- Only team standards (model, statusLine) are overwritten

### Q: What if the update breaks something?

**A:** Easy rollback:
```bash
claude-setup rollback
```

This restores your previous state immediately.

### Q: How often should I update?

**A:**
- Check weekly: `claude-setup status`
- Update when you see: "⚠ Updates available"
- Or when notified in Slack/Teams

### Q: Can I skip an update?

**A:** Yes! Updates are optional. But you might miss:
- New team rules and best practices
- Bug fixes
- New commands and capabilities

### Q: Do I need to restart Claude Code?

**A:** Usually yes, especially for:
- Settings changes
- New plugins
- New commands

Just close and reopen your terminal or IDE.

### Q: What if git pull fails?

**A:** Common issues:

```bash
# Conflict in config files
git pull
# Error: Your local changes would be overwritten

# Solution: Stash or commit your changes
git stash
git pull
git stash pop
```

Or:
```bash
# Reset to remote version
git fetch origin
git reset --hard origin/master
```

**Note:** This discards your local changes to the `claude-setup` repo. Your actual `~/.claude/` config is safe.

---

## 🔔 Update Notification Examples

When you see messages like this in Slack:

### Example 1: Minor Update
```
📦 Claude Config Update Available

What changed:
• Updated AWS access rules
• Fixed typo in agent-usage.md

To update: git pull && claude-setup update
```

**Action:** Update when convenient.

### Example 2: Important Update
```
🚨 Important: Claude Config Update

What changed:
• New security guidelines (required)
• Updated Terraform best practices
• New plugin required: security-scanner

To update: git pull && claude-setup update
Then run: claude-setup plugins --install
```

**Action:** Update today.

### Example 3: Breaking Change
```
⚠️ BREAKING: Claude Config Update v2.0.0

What changed:
• New settings.json format
• Removed deprecated commands
• Migration required

Instructions:
1. Backup your settings: cp ~/.claude/settings.json ~/settings-backup.json
2. Update: git pull && claude-setup update
3. Verify: claude-setup status
4. Report issues in #claude-code channel
```

**Action:** Follow instructions carefully.

---

## 🎯 Update Command Cheat Sheet

```bash
# Check for updates
claude-setup status
claude-setup update --check

# Preview updates
git pull
claude-setup install --all --dry-run

# Install updates
claude-setup update

# Or interactive
claude-setup
→ "🔄 Check for Updates"

# Full update command
cd ~/claude-setup && git pull && claude-setup update

# Check plugins after update
claude-setup plugins
claude-setup plugins --install

# Rollback if needed
claude-setup rollback

# See what's in latest backup
claude-setup backups
```

---

## 🚀 Best Practices

1. **Update regularly** - Check weekly or when notified
2. **Read the changelog** - Know what's changing
3. **Use dry-run if unsure** - Preview changes first
4. **Trust the backups** - They're automatic and reliable
5. **Report issues** - If something breaks, speak up!

---

## 🆘 Troubleshooting

### Update shows no changes but should

```bash
# Force reinstall
claude-setup install --all --force
```

### Settings not merging correctly

```bash
# Check what's in the backup
ls ~/.claude/backups/
cat ~/.claude/backups/claude-setup-*/settings.json

# Rollback and try again
claude-setup rollback
git pull
claude-setup update
```

### Plugins won't install

```bash
# Manual install
claude plugin install plugin-name@source

# Or check for errors
claude-setup plugins --install
```

### Update fails mid-installation

```bash
# Rollback to last known good state
claude-setup rollback

# Then try again
claude-setup update
```

---

## 📞 Getting Help

If updates aren't working:

1. Check `claude-setup status` output
2. Try `claude-setup rollback`
3. Check `~/.claude/backups/` exist
4. Ask in #claude-code Slack channel
5. Contact platform team

Remember: Updates are **safe** and **reversible**. The tool creates backups automatically before any changes!
