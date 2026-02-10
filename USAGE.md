# Claude Setup - Interactive Menu Usage

## 🎨 Interactive Menu (NEW!)

Simply run `claude-setup` with no arguments to launch the interactive menu:

```bash
claude-setup
```

You'll see a beautiful menu like this:

```
╭──────────────────────────────────────────────────────────────────╮
│                                                                  │
│  Claude Setup                                                    │
│  Interactive CLI installer for Claude Code team configuration    │
│  Version 1.0.0                                                   │
│                                                                  │
╰──────────────────────────────────────────────────────────────────╯

? What would you like to do?
❯ 📦 Install Configuration
  📊 Check Installation Status
  🔌 Manage Plugins
  💾 View Backups
  ⏮️  Rollback to Backup
  🔄 Check for Updates
  🚪 Exit
```

## 🎯 Menu Options Explained

### 📦 Install Configuration
Navigate through:
1. **Select categories (recommended)** - Pick exactly what you want
2. **Install everything** - Install all categories at once
3. **Preview changes only** - Dry run to see what would happen
4. **Back to menu** - Return without installing

### 📊 Check Installation Status
- Shows current installation status
- Displays version information
- Tells you if updates are available

### 🔌 Manage Plugins
- Lists all required plugins with status (✓ Installed / ✗ Not installed)
- Option to auto-install missing plugins
- Shows manual install commands

### 💾 View Backups
Choose from:
- **List all backups** - See all available backups with timestamps
- **Clean old backups** - Remove old backups, keep N recent ones

### ⏮️ Rollback to Backup
- Shows all available backups
- Select which backup to restore
- Confirms before restoring

### 🔄 Check for Updates
- Checks if new configuration is available
- Shows what changed
- Option to install updates immediately

### 🏗️ Create Config Repo

Generates a new config repository from your current `~/.claude` setup. This is useful for administrators who want to create a team config based on their working environment.

**What it does:**
- Scans your `~/.claude` directory
- Classifies files into categories (core, agents, rules, commands)
- Separates team settings from personal settings
- Lets you choose what to include
- Generates a properly structured config repo

**When to use:**
- You have a working `~/.claude` setup to share with your team
- You want to create a team config without manually copying files
- You need to bootstrap a new config repository

**Interactive flow:**
1. Backs up `~/.claude` for safety
2. Shows discovered files grouped by category
3. Lets you select which categories to include
4. Lets you edit permissions and plugins
5. Previews the config structure
6. Generates the repository
7. Shows next steps for distribution

See [Creating Config from Existing Setup](ADMIN-GUIDE.md#creating-config-from-existing-setup) for detailed walkthrough.

### 🚪 Exit
Returns to terminal

## 🎮 Navigation

- **Arrow Keys** ↑↓ - Navigate through options
- **Enter** ⏎ - Select option
- **Space** ␣ - Toggle checkboxes (in multi-select)
- **Ctrl+C** - Exit at any time

After each action, you'll return to the main menu automatically!

## 💡 Best Practices

1. **First time?** Use "📦 Install Configuration" → "Preview changes only"
2. **Want control?** Use "Select categories" to pick exactly what you need
3. **After git pull?** Use "🔄 Check for Updates"
4. **Something broke?** Use "⏮️ Rollback to Backup"

## 🚀 Still Want CLI Flags?

All the original commands still work:

```bash
claude-setup install --all          # Direct install
claude-setup status                 # Quick status check
claude-setup plugins                # Plugin info
claude-setup backups                # List backups
claude-setup rollback               # Rollback
claude-setup update                 # Update
claude-setup create-config          # Create config repo from ~/.claude
```

## 🎨 Interactive vs CLI

| Task | Interactive Menu | CLI Command |
|------|------------------|-------------|
| Browse options | ✅ Best | ❌ Must know command |
| Quick status | ⚠️ 2 clicks | ✅ `claude-setup status` |
| Scripting/Automation | ❌ Not suitable | ✅ Use flags |
| First-time users | ✅ Self-explanatory | ⚠️ Need docs |
| Power users | ⚠️ Extra clicks | ✅ Direct commands |
| Create Config Repo | `create-config` menu option | `claude-setup create-config --output ~/my-config` |

**Recommendation**:
- Use **Interactive Menu** for exploration and safety
- Use **CLI flags** for speed and automation
