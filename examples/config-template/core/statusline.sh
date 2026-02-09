#!/bin/bash
# Status line script for Claude Code
# Customize this to show relevant information

# Example: Show git branch and status
if git rev-parse --git-dir > /dev/null 2>&1; then
    branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
    echo "git:$branch"
else
    echo "no-repo"
fi
