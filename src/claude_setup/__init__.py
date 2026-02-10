"""Claude Setup - Interactive CLI installer for Claude Code team configuration."""

try:
    from importlib.metadata import version
    __version__ = version("claude-setup")
except Exception:
    # Fallback for development/editable installs
    __version__ = "0.0.0.dev"

