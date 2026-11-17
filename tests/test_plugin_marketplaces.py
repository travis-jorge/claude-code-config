"""Tests for marketplace-aware plugin management (all subprocess calls mocked)."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

import claude_setup.plugins as plugins_module
from claude_setup.plugins import CLI_NOT_FOUND, PluginManager

# The real implementations, captured before the autouse safety-net fixture patches them
REAL_EXECUTE = plugins_module._execute
REAL_GIT_SSH_CONFIGURED = plugins_module._git_ssh_configured

RUN = "claude_setup.plugins._execute"

TEAM_PLUGIN = {
    "name": "team-skills@team-tools",
    "description": "Team skills",
    "marketplace": {"name": "team-tools", "source": "example-org/team-config"},
}
LEGACY_PLUGIN = {
    "name": "ralph-loop@claude-plugins-official",
    "description": "Legacy entry",
}


@pytest.fixture
def claude_dir(tmp_path):
    d = tmp_path / ".claude"
    (d / "plugins").mkdir(parents=True)
    return d


def write_installed(claude_dir, names):
    (claude_dir / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {n: [{"scope": "user"}] for n in names}})
    )


def write_known(claude_dir, content):
    path = claude_dir / "plugins" / "known_marketplaces.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content))


def ok(stdout="ok"):
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def fail(stderr="boom"):
    return MagicMock(returncode=1, stdout="", stderr=stderr)


def commands(mock_run):
    """Return the argv lists passed to subprocess.run."""
    return [c.args[0] for c in mock_run.call_args_list]


class TestKnownMarketplaces:
    def test_missing_file(self, claude_dir):
        assert PluginManager(claude_dir, []).get_known_marketplaces() == set()

    def test_dict_keyed_by_name(self, claude_dir):
        write_known(
            claude_dir,
            {
                "team-tools": {
                    "source": {"source": "github", "repo": "example-org/team-config"}
                }
            },
        )
        assert PluginManager(claude_dir, []).get_known_marketplaces() == {"team-tools"}

    @pytest.mark.parametrize("content", ["{not json", "", "null", "42", '"string"'])
    def test_invalid_or_odd_content(self, claude_dir, content):
        write_known(claude_dir, content)
        assert PluginManager(claude_dir, []).get_known_marketplaces() == set()

    def test_list_of_named_objects_tolerated(self, claude_dir):
        write_known(claude_dir, [{"name": "a"}, {"nope": 1}, "junk"])
        assert PluginManager(claude_dir, []).get_known_marketplaces() == {"a"}

    def test_directory_instead_of_file(self, claude_dir):
        (claude_dir / "plugins" / "known_marketplaces.json").mkdir()
        assert PluginManager(claude_dir, []).get_known_marketplaces() == set()

    def test_installed_plugins_odd_shape(self, claude_dir):
        (claude_dir / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"plugins": ["x"]})
        )
        assert PluginManager(claude_dir, [LEGACY_PLUGIN]).check_installed() == {
            LEGACY_PLUGIN["name"]: False
        }


class TestEntryFormats:
    def test_marketplace_parsed(self):
        assert PluginManager.get_marketplace(TEAM_PLUGIN) == {
            "name": "team-tools",
            "source": "example-org/team-config",
        }

    def test_legacy_entry_has_no_marketplace(self):
        assert PluginManager.get_marketplace(LEGACY_PLUGIN) is None

    @pytest.mark.parametrize(
        "marketplace",
        [
            "example-org/team-config",
            {"name": "x"},
            {"source": "y"},
            {"name": "", "source": "y"},
            {"name": 1, "source": 2},
        ],
    )
    def test_invalid_marketplace_ignored_with_warning(self, marketplace):
        entry = {"name": "p@x", "description": "", "marketplace": marketplace}
        assert PluginManager.get_marketplace(entry) is None
        assert PluginManager.validate_entry(entry)

    def test_suffix_mismatch_warns(self):
        entry = {
            "name": "p@other",
            "marketplace": {"name": "team-tools", "source": "example-org/team-config"},
        }
        assert "does not match" in PluginManager.validate_entry(entry)[0]

    def test_valid_entries_no_warnings(self, claude_dir):
        assert (
            PluginManager(claude_dir, [TEAM_PLUGIN, LEGACY_PLUGIN]).get_warnings() == []
        )

    def test_plugin_id_appends_marketplace_when_missing(self):
        entry = {
            "name": "team-skills",
            "marketplace": {"name": "team-tools", "source": "example-org/team-config"},
        }
        assert PluginManager.plugin_id(entry) == "team-skills@team-tools"
        assert PluginManager.plugin_id(TEAM_PLUGIN) == "team-skills@team-tools"
        assert PluginManager.plugin_id(LEGACY_PLUGIN) == LEGACY_PLUGIN["name"]

    def test_bad_entries_dropped(self, claude_dir):
        mgr = PluginManager(
            claude_dir, [LEGACY_PLUGIN, "junk", {"description": "no name"}]
        )
        assert mgr.required_plugins == [LEGACY_PLUGIN]

    def test_team_marketplaces(self, claude_dir):
        dup = dict(TEAM_PLUGIN, name="other@team-tools")
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN, dup, LEGACY_PLUGIN])
        assert mgr.get_team_marketplaces() == {"team-tools": "example-org/team-config"}


class TestInstallWithMarketplace:
    def test_unknown_marketplace_added_before_install(self, claude_dir):
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN])
        with patch(RUN, return_value=ok()) as mock_run:
            results = mgr.install_all_missing()

        assert results == {"team-skills@team-tools": (True, "ok")}
        assert commands(mock_run) == [
            ["claude", "plugin", "marketplace", "add", "example-org/team-config"],
            ["claude", "plugin", "install", "team-skills@team-tools"],
        ]

    def test_known_marketplace_not_added_again(self, claude_dir):
        write_known(claude_dir, {"team-tools": {}})
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN])
        with patch(RUN, return_value=ok()) as mock_run:
            mgr.install_all_missing()

        assert commands(mock_run) == [
            ["claude", "plugin", "install", "team-skills@team-tools"]
        ]

    def test_marketplace_added_once_for_several_plugins(self, claude_dir):
        second = dict(TEAM_PLUGIN, name="team-agents@team-tools")
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN, second])
        with patch(RUN, return_value=ok()) as mock_run:
            mgr.install_all_missing()

        assert (
            commands(mock_run).count(
                ["claude", "plugin", "marketplace", "add", "example-org/team-config"]
            )
            == 1
        )
        assert len(commands(mock_run)) == 3

    def test_marketplace_failure_blocks_its_plugins_only(self, claude_dir):
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN, LEGACY_PLUGIN])

        def side_effect(argv, **kwargs):
            return fail("repo not found") if argv[2] == "marketplace" else ok()

        with patch(RUN, side_effect=side_effect) as mock_run:
            mkt_results = {}
            results = mgr.install_all_missing(mkt_results)

        assert results["team-skills@team-tools"][0] is False
        assert "repo not found" in results["team-skills@team-tools"][1]
        assert results[LEGACY_PLUGIN["name"]] == (True, "ok")
        assert mkt_results == {"team-tools": (False, "repo not found")}
        assert [
            "claude",
            "plugin",
            "install",
            "team-skills@team-tools",
        ] not in commands(mock_run)

    def test_legacy_entry_installs_without_marketplace_add(self, claude_dir):
        mgr = PluginManager(claude_dir, [LEGACY_PLUGIN])
        with patch(RUN, return_value=ok()) as mock_run:
            mgr.install_all_missing()
        assert commands(mock_run) == [
            ["claude", "plugin", "install", LEGACY_PLUGIN["name"]]
        ]

    def test_install_commands_include_marketplace_add(self, claude_dir):
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN, LEGACY_PLUGIN])
        assert mgr.get_install_commands() == [
            "claude plugin marketplace add example-org/team-config",
            "claude plugin install team-skills@team-tools",
            f"claude plugin install {LEGACY_PLUGIN['name']}",
        ]

    def test_no_yes_flag_passed(self, claude_dir):
        mgr = PluginManager(claude_dir, [])
        with patch(RUN, return_value=ok()) as mock_run:
            mgr.install_plugin("x@y")
            mgr.update_plugin("x@y")
        for argv in commands(mock_run):
            assert "-y" not in argv and "--yes" not in argv


class TestExecute:
    """The real _execute, with Popen mocked (never runs a process)."""

    def test_non_interactive_new_session(self):
        proc = MagicMock(pid=4242, returncode=0)
        proc.communicate.return_value = ("out", "err")
        with patch("claude_setup.plugins.subprocess.Popen", return_value=proc) as popen:
            result = REAL_EXECUTE(
                ["claude", "plugin", "list"], timeout=7, env={"A": "1"}
            )

        kwargs = popen.call_args.kwargs
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["start_new_session"] is True
        assert kwargs["env"] == {"A": "1"}
        proc.communicate.assert_called_once_with(timeout=7)
        assert (result.returncode, result.stdout, result.stderr) == (0, "out", "err")

    @pytest.mark.parametrize(
        "error", [subprocess.TimeoutExpired("claude", 7), KeyboardInterrupt()]
    )
    def test_timeout_kills_process_group(self, error):
        proc = MagicMock(pid=4242)
        proc.communicate.side_effect = [error, ("", "")]
        with (
            patch("claude_setup.plugins.subprocess.Popen", return_value=proc),
            patch("claude_setup.plugins.os.killpg") as killpg,
        ):
            with pytest.raises(type(error)):
                REAL_EXECUTE(["claude"], timeout=7, env={})
        killpg.assert_called_once()
        assert killpg.call_args.args[0] == 4242

    def test_git_ssh_configured_reads_core_sshcommand(self):
        with patch(
            "claude_setup.plugins.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="ssh -i key\n"),
        ) as run:
            assert REAL_GIT_SSH_CONFIGURED() is True
        assert run.call_args.args[0] == ["git", "config", "--get", "core.sshCommand"]
        with patch(
            "claude_setup.plugins.subprocess.run",
            return_value=MagicMock(returncode=1, stdout=""),
        ):
            assert REAL_GIT_SSH_CONFIGURED() is False
        with patch(
            "claude_setup.plugins.subprocess.run", side_effect=FileNotFoundError()
        ):
            assert REAL_GIT_SSH_CONFIGURED() is False


class TestRunErrors:
    def test_timeout(self, claude_dir):
        mgr = PluginManager(claude_dir, [])
        with patch(RUN, side_effect=subprocess.TimeoutExpired("claude", 1)):
            assert mgr.add_marketplace("example-org/team-config") == (
                False,
                "Adding marketplace timed out",
            )

    def test_cli_missing_short_circuits_later_calls(self, claude_dir):
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN, LEGACY_PLUGIN])
        with patch(RUN, side_effect=FileNotFoundError()) as mock_run:
            results = mgr.sync()

        assert mock_run.call_count == 1
        assert mgr.cli_missing is True
        assert results["marketplaces"]["team-tools"] == (False, CLI_NOT_FOUND)
        assert all(not ok_ for ok_, _ in results["installed"].values())

    def test_unexpected_exception_reported(self, claude_dir):
        mgr = PluginManager(claude_dir, [])
        with patch(RUN, side_effect=RuntimeError("weird")):
            success, message = mgr.update_plugin("x@y")
        assert not success and "weird" in message

    def test_failure_uses_stdout_when_no_stderr(self, claude_dir):
        mgr = PluginManager(claude_dir, [])
        with patch(
            RUN, return_value=MagicMock(returncode=2, stdout="from stdout", stderr="")
        ):
            assert mgr.update_plugin("x@y") == (False, "from stdout")


class TestSync:
    def test_full_sync_order_and_commands(self, claude_dir):
        write_known(claude_dir, {"team-tools": {}})
        installed_plugin = dict(TEAM_PLUGIN, name="team-agents@team-tools")
        write_installed(claude_dir, ["team-agents@team-tools"])
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN, installed_plugin, LEGACY_PLUGIN])

        with patch(RUN, return_value=ok()) as mock_run:
            results = mgr.sync()

        assert commands(mock_run) == [
            ["claude", "plugin", "marketplace", "update", "team-tools"],
            ["claude", "plugin", "install", "team-skills@team-tools"],
            ["claude", "plugin", "install", LEGACY_PLUGIN["name"]],
            ["claude", "plugin", "update", "team-agents@team-tools"],
        ]
        assert set(results["installed"]) == {
            "team-skills@team-tools",
            LEGACY_PLUGIN["name"],
        }
        assert set(results["updated"]) == {"team-agents@team-tools"}

    def test_sync_adds_unknown_team_marketplace_once(self, claude_dir):
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN])
        with patch(RUN, return_value=ok()) as mock_run:
            results = mgr.sync()

        assert commands(mock_run) == [
            ["claude", "plugin", "marketplace", "add", "example-org/team-config"],
            ["claude", "plugin", "install", "team-skills@team-tools"],
        ]
        assert results["marketplaces"]["team-tools"][0] is True

    def test_failed_marketplace_not_retried(self, claude_dir):
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN])
        with patch(RUN, return_value=fail("no network")) as mock_run:
            results = mgr.sync()

        assert mock_run.call_count == 1
        assert results["installed"]["team-skills@team-tools"][0] is False

    def test_update_failure_does_not_raise(self, claude_dir):
        write_installed(claude_dir, [LEGACY_PLUGIN["name"]])
        mgr = PluginManager(claude_dir, [LEGACY_PLUGIN])
        with patch(RUN, return_value=fail("update failed")):
            results = mgr.sync()
        assert results == {
            "marketplaces": {},
            "installed": {},
            "updated": {LEGACY_PLUGIN["name"]: (False, "update failed")},
        }

    def test_update_installed(self, claude_dir):
        write_installed(claude_dir, [LEGACY_PLUGIN["name"]])
        mgr = PluginManager(claude_dir, [LEGACY_PLUGIN, TEAM_PLUGIN])
        with patch(RUN, return_value=ok("updated")) as mock_run:
            assert mgr.update_installed() == {LEGACY_PLUGIN["name"]: (True, "updated")}
        assert commands(mock_run) == [
            ["claude", "plugin", "update", LEGACY_PLUGIN["name"]]
        ]

    def test_no_required_plugins_runs_nothing(self, claude_dir):
        with patch(RUN) as mock_run:
            assert PluginManager(claude_dir, []).sync() == {
                "marketplaces": {},
                "installed": {},
                "updated": {},
            }
        mock_run.assert_not_called()


def test_failed_refresh_of_known_marketplace_does_not_block_install(claude_dir):
    write_known(claude_dir, {"team-tools": {}})
    mgr = PluginManager(claude_dir, [TEAM_PLUGIN])

    def side_effect(argv, **kwargs):
        return fail("fetch failed") if argv[2] == "marketplace" else ok()

    with patch(RUN, side_effect=side_effect) as mock_run:
        results = mgr.sync()

    assert results["marketplaces"]["team-tools"] == (False, "fetch failed")
    assert results["installed"]["team-skills@team-tools"] == (True, "ok")
    assert commands(mock_run) == [
        ["claude", "plugin", "marketplace", "update", "team-tools"],
        ["claude", "plugin", "install", "team-skills@team-tools"],
    ]


class TestHardening:
    def test_git_cannot_prompt(self, claude_dir, monkeypatch):
        monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
        with patch(RUN, return_value=ok()) as mock_run:
            PluginManager(claude_dir, []).add_marketplace("example-org/team-config")
        env = mock_run.call_args.kwargs["env"]
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GIT_SSH_COMMAND"] == "ssh -o BatchMode=yes"

    def test_user_git_ssh_command_kept(self, claude_dir, monkeypatch):
        monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -i /tmp/key")
        with patch(RUN, return_value=ok()) as mock_run:
            PluginManager(claude_dir, []).update_marketplace("team-tools")
        assert mock_run.call_args.kwargs["env"]["GIT_SSH_COMMAND"] == "ssh -i /tmp/key"
        assert mock_run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"

    def test_marketplace_timeout_stops_further_marketplace_calls(self, claude_dir):
        write_known(claude_dir, {"a": {}, "b": {}, "c": {}})
        plugins = [
            {
                "name": f"p@{m}",
                "description": "",
                "marketplace": {"name": m, "source": f"example-org/{m}"},
            }
            for m in "abc"
        ]
        mgr = PluginManager(claude_dir, plugins)

        with patch(
            RUN, side_effect=subprocess.TimeoutExpired("claude", 300)
        ) as mock_run:
            results = mgr.refresh_marketplaces()

        assert mock_run.call_count == 1
        assert results["a"] == (False, "Updating marketplace timed out")
        assert (
            results["b"][1]
            == results["c"][1]
            == "skipped: an earlier marketplace operation timed out"
        )

    def test_plugin_timeout_does_not_stop_marketplaces(self, claude_dir):
        mgr = PluginManager(claude_dir, [])
        with patch(
            RUN, side_effect=[subprocess.TimeoutExpired("claude", 1), ok()]
        ) as mock_run:
            assert mgr.install_plugin("x@y")[0] is False
            assert mgr.update_marketplace("y") == (True, "ok")
        assert mock_run.call_count == 2

    @pytest.mark.parametrize(
        "name", ["--help", "-y", " -x@m", 5, None, ["a"], {"n": 1}, ""]
    )
    def test_bad_names_rejected_with_warning(self, claude_dir, name):
        mgr = PluginManager(
            claude_dir, [{"name": name, "description": ""}, LEGACY_PLUGIN]
        )
        assert mgr.required_plugins == [LEGACY_PLUGIN]
        assert len(mgr.get_warnings()) == 1
        with patch(RUN, return_value=ok()) as mock_run:
            mgr.install_all_missing()
        assert commands(mock_run) == [
            ["claude", "plugin", "install", LEGACY_PLUGIN["name"]]
        ]

    def test_non_dict_entries_rejected(self, claude_dir):
        mgr = PluginManager(claude_dir, ["string-entry", 3, LEGACY_PLUGIN])
        assert mgr.required_plugins == [LEGACY_PLUGIN]
        assert len(mgr.get_warnings()) == 2

    @pytest.mark.parametrize(
        "marketplace",
        [
            {"name": "--evil", "source": "x/y"},
            {"name": "m", "source": "--upload-pack=x"},
        ],
    )
    def test_option_like_marketplace_rejected(self, claude_dir, marketplace):
        entry = {"name": "p@m", "description": "", "marketplace": marketplace}
        mgr = PluginManager(claude_dir, [entry])
        assert PluginManager.get_marketplace(entry) is None
        assert mgr.get_warnings()
        with patch(RUN, return_value=ok()) as mock_run:
            mgr.sync()
        assert all(
            not any(a.startswith("-") for a in argv) for argv in commands(mock_run)
        )

    def test_install_commands_are_shell_quoted(self, claude_dir):
        entry = {
            "name": "p@m",
            "description": "",
            "marketplace": {"name": "m", "source": "/path with space/mkt"},
        }
        mgr = PluginManager(claude_dir, [entry])
        assert mgr.get_install_commands() == [
            "claude plugin marketplace add '/path with space/mkt'",
            "claude plugin install p@m",
        ]

    def test_relative_source_resolved_against_config_dir(self, claude_dir, tmp_path):
        config_dir = tmp_path / "config"
        (config_dir / "marketplace").mkdir(parents=True)
        entry = {
            "name": "p@m",
            "description": "",
            "marketplace": {"name": "m", "source": "./marketplace"},
        }
        mgr = PluginManager(claude_dir, [entry], config_dir=config_dir)

        with patch(RUN, return_value=ok()) as mock_run:
            mgr.install_all_missing()

        expected = str((config_dir / "marketplace").resolve())
        assert commands(mock_run)[0] == [
            "claude",
            "plugin",
            "marketplace",
            "add",
            expected,
        ]
        assert mgr.get_team_marketplaces() == {"m": expected}

    def test_github_shorthand_not_resolved(self, claude_dir, tmp_path):
        mgr = PluginManager(claude_dir, [TEAM_PLUGIN], config_dir=tmp_path)
        assert mgr.get_team_marketplaces() == {"team-tools": "example-org/team-config"}


@pytest.mark.parametrize(
    "env_vars, core_ssh, expect_batchmode",
    [
        ({}, False, True),
        ({"GIT_SSH_COMMAND": "ssh -i k"}, False, False),
        ({"GIT_SSH": "/usr/bin/myssh"}, False, False),
        ({}, True, False),
    ],
)
def test_git_ssh_command_only_set_without_user_override(
    claude_dir, monkeypatch, env_vars, core_ssh, expect_batchmode
):
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    monkeypatch.delenv("GIT_SSH", raising=False)
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(plugins_module, "_git_ssh_configured", lambda: core_ssh)

    with patch(RUN, return_value=ok()) as mock_run:
        PluginManager(claude_dir, []).update_marketplace("m")

    env = mock_run.call_args.kwargs["env"]
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    if expect_batchmode:
        assert env["GIT_SSH_COMMAND"] == "ssh -o BatchMode=yes"
    else:
        assert env.get("GIT_SSH_COMMAND") == env_vars.get("GIT_SSH_COMMAND")
