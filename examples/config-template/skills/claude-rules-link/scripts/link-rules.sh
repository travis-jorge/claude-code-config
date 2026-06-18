#!/usr/bin/env bash
#
# link-rules.sh — Symlink the user's shared, path-scoped Claude rules into a
# project so they lazy-load (via `paths:` frontmatter) instead of loading from
# the global ~/.claude/rules/ directory on every session.
#
# Usage: link-rules.sh [PROJECT_DIR]   (defaults to the current directory)
#
set -euo pipefail

SHARED_RULES="$HOME/.claude/shared-rules"
LINK_NAME="shared"
IGNORE_ENTRY=".claude/rules/shared"

PROJECT_DIR="${1:-$PWD}"

if [ ! -d "$SHARED_RULES" ]; then
  echo "ERROR: shared rules directory not found at $SHARED_RULES" >&2
  echo "       Nothing to link. Create ~/.claude/shared-rules/ and populate it with path-scoped rules first." >&2
  exit 1
fi

if [ ! -d "$PROJECT_DIR" ]; then
  echo "ERROR: project directory not found: $PROJECT_DIR" >&2
  exit 1
fi
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"

RULES_DIR="$PROJECT_DIR/.claude/rules"
LINK_PATH="$RULES_DIR/$LINK_NAME"

mkdir -p "$RULES_DIR"

# Create or repair the symlink (idempotent; never clobber a real file/dir)
if [ -L "$LINK_PATH" ]; then
  current="$(readlink "$LINK_PATH")"
  if [ "$current" = "$SHARED_RULES" ]; then
    echo "OK: symlink already correct -> $SHARED_RULES"
  else
    ln -sfn "$SHARED_RULES" "$LINK_PATH"
    echo "FIXED: repointed symlink (was $current) -> $SHARED_RULES"
  fi
elif [ -e "$LINK_PATH" ]; then
  echo "ERROR: $LINK_PATH exists and is not a symlink. Refusing to clobber." >&2
  exit 1
else
  ln -s "$SHARED_RULES" "$LINK_PATH"
  echo "LINKED: $LINK_PATH -> $SHARED_RULES"
fi

# The symlink points at a machine-local path, so gitignore it to keep it out of
# version control (it would dangle on a teammate's checkout otherwise).
if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  GITIGNORE="$PROJECT_DIR/.gitignore"
  if [ -f "$GITIGNORE" ] && grep -qxF "$IGNORE_ENTRY" "$GITIGNORE"; then
    echo "OK: .gitignore already ignores $IGNORE_ENTRY"
  else
    printf '%s\n' "$IGNORE_ENTRY" >> "$GITIGNORE"
    echo "GITIGNORE: added $IGNORE_ENTRY"
  fi
else
  echo "NOTE: not a git repository; skipped .gitignore update"
fi

echo ""
echo "Done. Path-scoped shared rules are now linked into this project."
echo "They will load only when Claude reads files matching each rule's paths: frontmatter."
