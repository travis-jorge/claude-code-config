"""CLI tests for update/status/plugins with plugin sync and retired paths.

claude_dir and config_dir are redirected to tmp paths and every subprocess call
is mocked, so nothing touches the real ~/.claude or runs the claude CLI.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from claude_setup import cli

RUN = "claude_setup.plugins._execute"

TEAM_PLUGIN = {
    "name": "team-skills@team-tools",
    "description": "Team skills",
    "marketplace": {"name": "team-tools", "source": "example-org/team-config"},
}


@pytest.fixture
def env(mock_config_dir, mock_claude_dir):
    """Point the CLI at tmp dirs, add a plugins category and a marketplace plugin."""
    manifest_path = mock_config_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["categories"].append(
        {
            "name": "plugins",
            "description": "Required plugins",
            "target_dir": ".claude/plugins",
            "install_type": "check",
            "files": [],
        }
    )
    manifest_path.write_text(json.dumps(manifest))
    (mock_config_dir / "plugins" / "required.json").write_text(
        json.dumps([TEAM_PLUGIN])
    )

    with (
        patch.object(cli, "get_config_dir", return_value=mock_config_dir),
        patch.object(cli, "get_claude_dir", return_value=mock_claude_dir),
    ):
        yield mock_config_dir, mock_claude_dir


def argv_list(mock_run):
    return [c.args[0] for c in mock_run.call_args_list]


def stamp(claude_dir, categories, config_hash="stale"):
    (claude_dir / ".claude-setup-version.json").write_text(
        json.dumps(
            {"tool_version": "x", "config_hash": config_hash, "categories": categories}
        )
    )


def run(args):
    return CliRunner().invoke(cli.app, args)


def test_update_installs_files_then_syncs_plugins(env):
    config_dir, claude_dir = env
    stamp(claude_dir, ["core", "plugins"])

    with patch(
        RUN, return_value=MagicMock(returncode=0, stdout="ok", stderr="")
    ) as mock_run:
        result = run(["update"])

    assert result.exit_code == 0, result.output
    assert (claude_dir / "CLAUDE.md").exists()
    assert argv_list(mock_run) == [
        ["claude", "plugin", "marketplace", "add", "example-org/team-config"],
        ["claude", "plugin", "install", "team-skills@team-tools"],
    ]


def test_update_plugin_failure_is_not_fatal(env):
    config_dir, claude_dir = env
    stamp(claude_dir, ["core", "plugins"])

    with patch(
        RUN, return_value=MagicMock(returncode=1, stdout="", stderr="network down")
    ):
        result = run(["update"])

    assert result.exit_code == 0, result.output
    assert (claude_dir / "CLAUDE.md").exists()
    assert "network down" in result.output


def test_update_cli_missing_is_not_fatal(env):
    config_dir, claude_dir = env
    stamp(claude_dir, ["core", "plugins"])

    with patch(RUN, side_effect=FileNotFoundError()):
        result = run(["update"])

    assert result.exit_code == 0, result.output
    assert "not found" in result.output


def test_update_skip_plugins(env):
    config_dir, claude_dir = env
    stamp(claude_dir, ["core", "plugins"])

    with patch(RUN) as mock_run:
        result = run(["update", "--skip-plugins"])

    assert result.exit_code == 0, result.output
    mock_run.assert_not_called()
    assert (claude_dir / "CLAUDE.md").exists()


def test_update_up_to_date_still_syncs_plugins(env):
    config_dir, claude_dir = env
    current = cli.VersionManager(claude_dir, config_dir).get_available()["config_hash"]
    stamp(claude_dir, ["core", "plugins"], config_hash=current)
    (claude_dir / "plugins").mkdir()
    (claude_dir / "plugins" / "known_marketplaces.json").write_text(
        json.dumps({"team-tools": {}})
    )
    (claude_dir / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"team-skills@team-tools": []}})
    )

    with patch(
        RUN, return_value=MagicMock(returncode=0, stdout="ok", stderr="")
    ) as mock_run:
        result = run(["update"])

    assert result.exit_code == 0, result.output
    assert "already up to date" in result.output
    assert argv_list(mock_run) == [
        ["claude", "plugin", "marketplace", "update", "team-tools"],
        ["claude", "plugin", "update", "team-skills@team-tools"],
    ]


def test_update_check_runs_no_plugin_steps(env):
    config_dir, claude_dir = env
    stamp(claude_dir, ["core", "plugins"])

    with patch(RUN) as mock_run:
        result = run(["update", "--check"])

    assert result.exit_code == 0
    mock_run.assert_not_called()


def test_update_without_plugins_category_skips_sync(env):
    config_dir, claude_dir = env
    stamp(claude_dir, ["core"])

    with patch(RUN) as mock_run:
        result = run(["update"])

    assert result.exit_code == 0, result.output
    mock_run.assert_not_called()


def test_plugins_update_flag(env):
    with patch(
        RUN, return_value=MagicMock(returncode=0, stdout="ok", stderr="")
    ) as mock_run:
        result = run(["plugins", "--update"])

    assert result.exit_code == 0, result.output
    assert ["claude", "plugin", "install", "team-skills@team-tools"] in argv_list(
        mock_run
    )


def test_missing_required_json_is_tolerated(env):
    config_dir, claude_dir = env
    (config_dir / "plugins" / "required.json").unlink()

    with patch(RUN) as mock_run:
        result = run(["plugins"])

    assert result.exit_code == 0, result.output
    mock_run.assert_not_called()


def set_retired(config_dir, retired):
    manifest_path = config_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["retired"] = retired
    manifest_path.write_text(json.dumps(manifest))


def make_old_agent(claude_dir, text="old"):
    (claude_dir / "agents").mkdir(exist_ok=True)
    (claude_dir / "agents" / "old.md").write_text(text)


def archived_copies(claude_dir):
    return sorted((claude_dir / "archived").glob("*/agents/old.md"))


def wide(args, input=None):
    return CliRunner().invoke(cli.app, args, env={"COLUMNS": "300"}, input=input)


def test_update_shows_archive_list_and_archives_on_yes(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md"])
    make_old_agent(claude_dir)
    stamp(claude_dir, ["core"])

    result = wide(["update", "--skip-plugins"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "Retired paths to archive" in result.output
    assert "archived" in result.output
    assert not (claude_dir / "agents" / "old.md").exists()
    copies = archived_copies(claude_dir)
    assert len(copies) == 1 and copies[0].read_text() == "old"
    assert "Retired paths moved to" in result.output
    assert "delete this folder once you're happy" in result.output


def snapshot(directory):
    return sorted(
        (str(p.relative_to(directory)), p.read_bytes() if p.is_file() else None)
        for p in directory.rglob("*")
    )


@pytest.mark.parametrize("answer", ["n\n", ""], ids=["no", "eof"])
def test_update_decline_cancels_whole_update(env, answer):
    """H1: declining the archive prompt changes nothing at all (no install, backup, merge, stamp)."""
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md"])
    make_old_agent(claude_dir)
    stamp(claude_dir, ["core"])
    before = snapshot(claude_dir)

    with patch(RUN) as mock_run:
        result = wide(["update"], input=answer)

    assert result.exit_code == 0, result.output
    assert "Update cancelled; nothing changed" in result.output
    # BackupManager always ensures an (empty) backups/ folder exists; nothing else may change
    assert [e for e in snapshot(claude_dir) if e[0] != "backups"] == before
    assert list((claude_dir / "backups").iterdir()) == []
    assert not (claude_dir / "CLAUDE.md").exists()
    mock_run.assert_not_called()


@pytest.mark.parametrize("flag", ["--yes", "-y", "--force"])
def test_update_yes_skips_prompt(env, flag):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md"])
    make_old_agent(claude_dir)
    stamp(claude_dir, ["core"])

    result = wide(["update", "--skip-plugins", flag])

    assert result.exit_code == 0, result.output
    assert not (claude_dir / "agents" / "old.md").exists()
    assert len(archived_copies(claude_dir)) == 1


def test_update_up_to_date_but_retired_present_reinstalls(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md"])
    current = cli.VersionManager(claude_dir, config_dir).get_available()["config_hash"]
    stamp(claude_dir, ["core"], config_hash=current)
    make_old_agent(claude_dir, "re-created later")

    result = wide(["update", "--skip-plugins", "--yes"])

    assert result.exit_code == 0, result.output
    assert "retired path(s) still present" in result.output
    assert not (claude_dir / "agents" / "old.md").exists()


def test_update_check_reports_retired(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md"])
    make_old_agent(claude_dir)
    stamp(claude_dir, ["core"])

    with patch(RUN) as mock_run:
        result = wide(["update", "--check"])

    assert result.exit_code == 0, result.output
    assert "retired path(s) still present" in result.output
    assert "old.md" in result.output
    assert (claude_dir / "agents" / "old.md").exists()
    mock_run.assert_not_called()


def test_status_lists_retired_and_archives(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md", "agents/gone.md"])
    make_old_agent(claude_dir)
    (claude_dir / "archived" / "2026-01-01-000000").mkdir(parents=True)

    result = wide(["status"])

    assert result.exit_code == 0, result.output
    assert "Retired Paths Still Present" in result.output
    assert "old.md" in result.output
    assert "gone.md" not in result.output
    assert "Archived Retired Paths" in result.output
    assert "2026-01-01-000000" in result.output


def test_status_survives_nul_byte_entry(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["skills/a\x00b"])

    result = wide(["status"])

    assert result.exit_code == 0, result.output


def test_install_dry_run_lists_archive(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md"])
    make_old_agent(claude_dir)

    result = wide(["install", "--all", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Archive" in result.output
    assert "Move to" in result.output
    assert (claude_dir / "agents" / "old.md").exists()
    assert not (claude_dir / "archived").exists()


def test_rollback_moves_archived_back_and_reports_conflicts(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md", "skills/old-skill"])
    make_old_agent(claude_dir)
    (claude_dir / "skills" / "old-skill").mkdir(parents=True)
    (claude_dir / "skills" / "old-skill" / "SKILL.md").write_text("skill")
    stamp(claude_dir, ["core"])
    assert wide(["update", "--skip-plugins", "--yes"]).exit_code == 0
    (claude_dir / "skills" / "old-skill").mkdir()  # user re-created it

    result = wide(["rollback", "--force"])

    assert result.exit_code == 0, result.output
    assert (claude_dir / "agents" / "old.md").read_text() == "old"
    assert "Moved back from archive" in result.output
    assert "already exists" in result.output
    assert len(list((claude_dir / "archived").glob("*/skills/old-skill/SKILL.md"))) == 1


def test_rollback_dry_run_mentions_archive(env):
    config_dir, claude_dir = env
    set_retired(config_dir, ["agents/old.md"])
    make_old_agent(claude_dir)
    stamp(claude_dir, ["core"])
    assert wide(["update", "--skip-plugins", "--yes"]).exit_code == 0

    result = wide(["rollback", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "Would move archived retired paths back" in result.output
    assert not (claude_dir / "agents" / "old.md").exists()
