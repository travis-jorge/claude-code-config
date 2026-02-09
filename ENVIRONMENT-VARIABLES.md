# Environment Variable Expansion

## Overview

The `claude-setup` tool supports environment variable expansion in `sources.json`, allowing you to reference sensitive values like GitHub tokens from your shell environment instead of storing them in plaintext files.

## Syntax

Use either format to reference environment variables:
- `${VAR_NAME}` - Shell-style (recommended)
- `$VAR_NAME` - Simple format

## Use Cases

### GitHub Private Repositories

The most common use case is authenticating to private GitHub repositories:

```json
{
  "sources": [
    {
      "name": "company-config",
      "type": "github",
      "repo": "your-org/private-config",
      "ref": "main",
      "token": "${GITHUB_TOKEN}"
    }
  ]
}
```

Then set your token in the environment:
```bash
export GITHUB_TOKEN=ghp_your_personal_access_token
```

### Automatic Detection

The `init` command automatically detects `GITHUB_TOKEN` in your environment:

```bash
export GITHUB_TOKEN=ghp_your_token

# This will create sources.json with "token": "${GITHUB_TOKEN}"
claude-setup init --github your-org/private-config
```

### Any Configuration Value

Environment variables work in any string value, not just tokens:

```json
{
  "sources": [
    {
      "name": "dynamic-config",
      "type": "github",
      "repo": "${ORG_NAME}/claude-config",
      "ref": "${CONFIG_BRANCH}",
      "token": "${GITHUB_TOKEN}"
    },
    {
      "name": "local-config",
      "type": "local",
      "path": "${HOME}/my-config"
    }
  ]
}
```

## Error Handling

If a referenced environment variable is not set, you'll get a clear error:

```
✗ Error: Initialization failed: Failed to expand environment variables:
Environment variable 'GITHUB_TOKEN' not set. Please set it with: export GITHUB_TOKEN=<value>
```

## Security Benefits

1. **No plaintext secrets**: Tokens stay in environment, not in files
2. **Safe to commit**: Your `~/.claude/sources.json` can be safely shared or backed up to dotfiles repos
3. **Shell integration**: Works with existing secret management (1Password CLI, AWS SSM, etc.)
4. **Standard practice**: Follows 12-factor app methodology

## Examples

### Using with 1Password CLI

```bash
# Fetch token from 1Password and set in environment
export GITHUB_TOKEN=$(op read "op://Private/GitHub Token/credential")

# Now run claude-setup
claude-setup status
```

### Using with direnv

Create `.envrc` in your home directory:
```bash
# .envrc
export GITHUB_TOKEN=ghp_your_token_here
```

Then:
```bash
direnv allow ~
claude-setup status
```

### CI/CD Integration

In GitHub Actions:
```yaml
- name: Run claude-setup
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    claude-setup install --all
```

## Implementation Details

- Expansion happens when `sources.json` is loaded
- Uses regex pattern matching: `\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)`
- Recursive expansion through nested dicts and lists
- Original `sources.json` file is never modified
- Expansion is performed in-memory at runtime

## Testing

Run tests to verify environment variable expansion:
```bash
pytest tests/test_env_vars.py -v
```

Test coverage includes:
- Simple variable expansion
- Variables in strings
- Multiple variables
- Missing variable errors
- Nested dict/list expansion
- Non-string value handling

## Migration from Plaintext Tokens

If you have a plaintext token in your `sources.json`:

1. Note your token value
2. Set it as an environment variable:
   ```bash
   export GITHUB_TOKEN=ghp_your_token
   # Add to ~/.bashrc or ~/.zshrc to persist
   ```
3. Edit `~/.claude/sources.json` and replace:
   ```json
   "token": "ghp_hardcoded_token"
   ```
   with:
   ```json
   "token": "${GITHUB_TOKEN}"
   ```
4. Test it works:
   ```bash
   claude-setup status
   ```

## Troubleshooting

**Problem:** "Environment variable 'GITHUB_TOKEN' not set"

**Solution:** Export the variable in your shell:
```bash
export GITHUB_TOKEN=ghp_your_token
```

Make it permanent by adding to `~/.bashrc`, `~/.zshrc`, or `~/.profile`.

---

**Problem:** Token works in terminal but not in cron jobs

**Solution:** Cron doesn't load your shell profile. Set environment in crontab:
```cron
GITHUB_TOKEN=ghp_your_token
0 * * * * claude-setup update
```

---

**Problem:** Want to use different tokens for different repos

**Solution:** Create multiple environment variables:
```json
{
  "sources": [
    {
      "name": "public-config",
      "type": "github",
      "repo": "public-org/config",
      "token": "${PUBLIC_GITHUB_TOKEN}"
    },
    {
      "name": "private-config",
      "type": "github",
      "repo": "private-org/config",
      "token": "${PRIVATE_GITHUB_TOKEN}"
    }
  ]
}
```
