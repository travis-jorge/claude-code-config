# Configuration Examples

## config-template/

Generic template for any organization. **Start here** to create your own configuration.

### Structure

```
config-template/
├── manifest.json          # Category definitions
├── core/                  # Core configuration
│   ├── CLAUDE.md          # Main instructions
│   ├── settings.json      # Team settings
│   └── statusline.sh      # Status line script
├── agents/                # Agent definitions
├── rules/                 # Team rules (always-loaded)
├── skills/                # Reusable slash-command skills
│   └── claude-rules-link/ # Example: link path-scoped shared rules
├── commands/              # Custom commands
└── plugins/               # Required plugins
    └── required.json
```

### Usage

1. **Copy the template:**
   ```bash
   cp -r examples/config-template my-company-config
   cd my-company-config
   ```

2. **Customize for your organization:**
   ```bash
   # Edit core files
   vim core/CLAUDE.md
   vim core/settings.json

   # Add your team-specific content
   # - Add agents in agents/
   # - Add always-loaded rules in rules/
   # - Add path-scoped shared rules in ~/.claude/shared-rules/ (see below)
   # - Add skills in skills/
   # - Add commands in commands/
   # - List required plugins in plugins/required.json
   ```

3. **Publish your configuration:**

   **Option A: GitHub (Recommended)**
   ```bash
   git init
   git add .
   git commit -m "Initial company Claude configuration"
   git remote add origin git@github.com:your-org/claude-config.git
   git push -u origin main
   ```

   **Option B: Zip File**
   ```bash
   zip -r claude-config.zip .
   # Upload to accessible HTTPS URL
   ```

   **Option C: Network Share**
   ```bash
   cp -r . /mnt/shared/claude-config
   ```

4. **Team members install:**
   ```bash
   # GitHub
   claude-setup init --github your-org/claude-config

   # Zip
   claude-setup init --zip https://files.yourcompany.com/claude-config.zip

   # Local
   claude-setup init --local /mnt/shared/claude-config

   # Install
   claude-setup install --all
   ```

---

## Path-Scoped Shared Rules

Always-loaded rules in `~/.claude/rules/` add tokens to every session, even when irrelevant. For large rule sets (Terraform conventions, security standards, cloud provider patterns), this overhead compounds quickly.

**The pattern:** put rules in `~/.claude/shared-rules/` with `paths:` frontmatter, then symlink them into each project. They only load when Claude reads a file matching the pattern.

```markdown
---
paths:
  - "**/*.tf"
  - "**/*.tfvars"
---

# Terraform Standards
...only loads when Claude opens a .tf file...
```

**To set this up in a project**, use the included `claude-rules-link` skill:

```
/claude-rules-link
```

This creates `.claude/rules/shared → ~/.claude/shared-rules` and adds it to `.gitignore` (the symlink is machine-local and must be re-created per checkout). See `skills/claude-rules-link/` for the full implementation.

**Benefits:**
- Zero cost when not working on matching files
- Rules stay in one place (`~/.claude/shared-rules/`) and apply to all repos that run the skill
- Teammates pick up rule updates automatically without re-installing anything

---

## Example Source Configurations

See `sources-*.json` files for example source configurations:

- **sources-github.json** - GitHub repository source
- **sources-zip.json** - Zip file from URL
- **sources-local.json** - Local filesystem path
- **sources-multi.json** - Multiple sources combined

## Real-World Examples

Looking for real-world examples? Check out these public configurations:

- Submit a PR to add your organization's public config example here!

## Need Help?

See the [ADMIN-GUIDE.md](../ADMIN-GUIDE.md) for complete setup instructions.
