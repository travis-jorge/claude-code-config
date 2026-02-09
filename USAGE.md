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
```

## 🎨 Interactive vs CLI

| Task | Interactive Menu | CLI Command |
|------|------------------|-------------|
| Browse options | ✅ Best | ❌ Must know command |
| Quick status | ⚠️ 2 clicks | ✅ `claude-setup status` |
| Scripting/Automation | ❌ Not suitable | ✅ Use flags |
| First-time users | ✅ Self-explanatory | ⚠️ Need docs |
| Power users | ⚠️ Extra clicks | ✅ Direct commands |

**Recommendation**:
- Use **Interactive Menu** for exploration and safety
- Use **CLI flags** for speed and automation
