"""Regression tests for the final review probes (probe1/2/4, test_probe_cli*.py).

All in tmp dirs; the claude CLI is never run (see conftest safety net).
"""

import json
import os
import unicodedata
from datetime import datetime
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import claude_setup.archive as archive_module
from claude_setup import cli
from claude_setup.archive import ARCHIVE_MANIFEST, ArchiveManager
from claude_setup.backup import BackupError, BackupManager

DEEP = "[" * 200000 + "]" * 200000
CREATED = "2026-01-01T00:00:00"


@pytest.fixture
def claude_dir(tmp_path):
    d = tmp_path / ".claude"
    d.mkdir()
    return d


@pytest.fixture
def outside(tmp_path):
    d = tmp_path / "outside"
    d.mkdir()
    return d


def make_backup(claude_dir, name, manifest):
    backup = claude_dir / "backups" / name
    backup.mkdir(parents=True)
    content = manifest if isinstance(manifest, str) else json.dumps(manifest)
    (backup / "backup-manifest.json").write_text(content)
    return backup


# --- L3: allowlist root is an exact match -------------------------------------


@pytest.mark.parametrize(
    "entry",
    ["ſkills/x", "SKILLS/x", "Skills/x", "skills /x", "skills/ /x", " skills/x/ y"],
)
def test_allowlist_root_exact_and_no_padded_parts(claude_dir, entry):
    with pytest.raises(archive_module.UnsafePathError):
        archive_module.check_retirable(claude_dir, entry)


def test_long_s_directory_not_retirable(claude_dir):
    (claude_dir / "ſkills" / "x").mkdir(parents=True)
    with pytest.raises(archive_module.UnsafePathError):
        archive_module.check_retirable(claude_dir, "ſkills/x")


def test_nfd_root_normalised_to_allowlist(claude_dir):
    # NFC normalisation of the root is fine ("skills" has no combining marks either way)
    assert (
        archive_module.check_retirable(
            claude_dir, unicodedata.normalize("NFD", "skills") + "/x"
        )
        == claude_dir / "skills" / "x"
    )


def test_claude_dir_itself_may_be_symlink(tmp_path):
    real = tmp_path / "dotfiles"
    (real / "skills" / "a").mkdir(parents=True)
    os.symlink(real, tmp_path / ".claude")
    assert (
        archive_module.check_retirable(tmp_path / ".claude", "skills/a")
        == tmp_path / ".claude" / "skills" / "a"
    )


# --- M3: deep / odd JSON fails closed -----------------------------------------


def test_deep_archive_manifest(claude_dir):
    run = claude_dir / "archived" / "run1"
    run.mkdir(parents=True)
    mgr = ArchiveManager(claude_dir)
    for content in [DEEP, '{"items": ' + DEEP + "}"]:
        (run / ARCHIVE_MANIFEST).write_text(content)
        assert mgr.restore(run)["failed"]
    assert mgr.list_runs() == [{"path": run, "items": 0}]


@pytest.mark.parametrize(
    "kind",
    [
        "deep",
        "badutf8",
        "dir",
        "created_int",
        "created_bad",
        "categories_int",
        "archive_list",
    ],
)
def test_odd_backup_manifests_marked_invalid(claude_dir, kind):
    backup = claude_dir / "backups" / "claude-setup-2026-01-01-000000"
    backup.mkdir(parents=True)
    path = backup / "backup-manifest.json"
    if kind == "deep":
        path.write_text(DEEP)
    elif kind == "badutf8":
        path.write_bytes(b"\xff\xfe{")
    elif kind == "dir":
        path.mkdir()
    else:
        manifest = {
            "created_int": {"created_at": 5, "files": []},
            "created_bad": {"created_at": "2030", "files": []},
            "categories_int": {"created_at": CREATED, "files": [], "categories": 5},
            "archive_list": {"created_at": CREATED, "files": [], "archive": ["x"]},
        }[kind]
        path.write_text(json.dumps(manifest))

    mgr = BackupManager(claude_dir)
    listed = mgr.list_backups()
    assert len(listed) == 1 and listed[0]["invalid"]
    with pytest.raises((BackupError, OSError)):
        mgr.restore_backup(backup.name)


def test_mixed_valid_invalid_and_legacy_sort(claude_dir):
    make_backup(claude_dir, "claude-setup-a", {"created_at": 5, "files": []})
    make_backup(
        claude_dir, "claude-setup-b", {"created_at": "2099-01-01T00:00:00", "files": []}
    )
    (claude_dir / "backups" / "backup-legacy").mkdir()
    listed = BackupManager(claude_dir).list_backups()
    assert listed[0]["id"] == "claude-setup-b"
    assert {b["id"] for b in listed} == {
        "claude-setup-a",
        "claude-setup-b",
        "backup-legacy",
    }


def test_version_stamp_odd_content(claude_dir, tmp_path):
    from claude_setup.version import VersionManager

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    for content in [DEEP, "[1]", "\xff"]:
        (claude_dir / ".claude-setup-version.json").write_text(content)
        assert VersionManager(claude_dir, cfg).get_installed() == {}


# --- M1: unique backup directories --------------------------------------------


def test_backups_in_same_second_do_not_collide(claude_dir):
    mgr = BackupManager(claude_dir)
    fixed = datetime(2026, 1, 1, 12, 0, 0)
    with patch("claude_setup.backup.datetime") as dt:
        dt.now.return_value = fixed
        dt.fromisoformat = datetime.fromisoformat
        dt.fromtimestamp = datetime.fromtimestamp
        first = mgr.create_backup([], ["core"], archive="archived/X")
        second = mgr.create_backup([], ["core"])

    assert first != second
    assert second.name == first.name + "-1"
    assert (
        json.loads((first / "backup-manifest.json").read_text())["archive"]
        == "archived/X"
    )
    assert "archive" not in json.loads((second / "backup-manifest.json").read_text())


# --- M2: backup restore stays inside ~/.claude --------------------------------


def test_restore_through_symlinked_dest_parent_refused(claude_dir, outside):
    backup = make_backup(
        claude_dir,
        "claude-setup-x",
        {"created_at": CREATED, "files": ["skills/evil.md"]},
    )
    (backup / "skills").mkdir()
    (backup / "skills" / "evil.md").write_text("payload")
    os.symlink(outside, claude_dir / "skills")

    mgr = BackupManager(claude_dir)
    mgr.restore_backup("claude-setup-x")

    assert not (outside / "evil.md").exists()
    assert "symlink" in mgr.last_restore_skipped[0][1]


def test_restore_symlinked_source_refused(claude_dir, outside):
    (outside / "secret").write_text("SECRET")
    backup = make_backup(
        claude_dir,
        "claude-setup-x",
        {"created_at": CREATED, "files": ["leak.txt", "sub/leak.txt"]},
    )
    os.symlink(outside / "secret", backup / "leak.txt")
    os.symlink(outside, backup / "sub")

    mgr = BackupManager(claude_dir)
    mgr.restore_backup("claude-setup-x")

    assert not os.path.lexists(claude_dir / "leak.txt")
    assert not os.path.lexists(claude_dir / "sub")
    assert len(mgr.last_restore_skipped) == 2


@pytest.mark.parametrize(
    "backup_id", ["../../outside", "..", ".", "a/b", "/abs", "", "x\x00y", "missing"]
)
def test_backup_id_must_be_single_existing_name(claude_dir, outside, backup_id):
    (outside / "backup-manifest.json").write_text(
        json.dumps({"created_at": CREATED, "files": []})
    )
    with pytest.raises(FileNotFoundError):
        BackupManager(claude_dir).restore_backup(backup_id)


def test_symlinked_backup_dir_refused(claude_dir, outside):
    (outside / "backup-manifest.json").write_text(
        json.dumps({"created_at": CREATED, "files": []})
    )
    mgr = BackupManager(claude_dir)
    os.symlink(outside, claude_dir / "backups" / "claude-setup-link")
    with pytest.raises(FileNotFoundError):
        mgr.restore_backup("claude-setup-link")
    assert mgr.list_backups() == []


def test_leaf_symlink_dest_written_only_if_managed(claude_dir, outside):
    dotfile = outside / "CLAUDE.md"
    dotfile.write_text("current")
    os.symlink(dotfile, claude_dir / "CLAUDE.md")
    backup = make_backup(
        claude_dir, "claude-setup-x", {"created_at": CREATED, "files": ["CLAUDE.md"]}
    )
    (backup / "CLAUDE.md").write_text("from backup")
    mgr = BackupManager(claude_dir)

    mgr.restore_backup("claude-setup-x")
    assert dotfile.read_text() == "current"
    assert "not a file the manifest installs" in mgr.last_restore_skipped[0][1]

    mgr.restore_backup("claude-setup-x", managed_files={"CLAUDE.md"})
    assert dotfile.read_text() == "from backup"
    assert (claude_dir / "CLAUDE.md").is_symlink()


# --- probe2: archive + tampered journal ---------------------------------------


def test_archive_then_tampered_journal(claude_dir, outside):
    (claude_dir / "skills" / "old").mkdir(parents=True)
    (claude_dir / "skills" / "old" / "f").write_text("x")
    os.symlink(outside, claude_dir / "skills" / "linkout")
    mgr = ArchiveManager(claude_dir)
    run = mgr.next_run_dir()
    result = mgr.archive(
        [claude_dir / "skills" / "old", claude_dir / "skills" / "linkout"], run
    )
    assert len(result["moved"]) == 2 and os.path.islink(run / "skills" / "linkout")

    os.symlink(outside, run / "evil")
    (outside / "x").write_text("outside")
    items = [
        {"original": "projects/p", "archived": "skills/old"},
        {"original": "skills/z", "archived": "../../../outside"},
        {"original": "skills/z2", "archived": "evil/x"},
        {"original": "skills/z3", "archived": "evil"},
        {"original": "skills/old", "archived": "skills/old"},
        {"original": "skills/linkout", "archived": "skills/linkout"},
        "junk",
        {"original": None},
        {"original": "skills/q", "archived": 5},
    ]
    (run / ARCHIVE_MANIFEST).write_text(json.dumps({"items": items}))

    restore = mgr.restore(run)

    # "evil" is itself a symlink leaf, which may be moved (as a link, target untouched);
    # nothing is read through it ("evil/x" is refused).
    assert sorted(restore["restored"]) == sorted(
        [
            claude_dir / "skills" / "old",
            claude_dir / "skills" / "linkout",
            claude_dir / "skills" / "z3",
        ]
    )
    assert os.path.islink(claude_dir / "skills" / "z3")
    assert (outside / "x").read_text() == "outside"
    assert not os.path.lexists(claude_dir / "skills" / "z2")
    assert not os.path.lexists(claude_dir / "projects")
    assert len(restore["failed"]) == 6


# --- CLI probes ----------------------------------------------------------------


@pytest.fixture
def cli_env(mock_config_dir, mock_claude_dir):
    with (
        patch.object(cli, "get_config_dir", return_value=mock_config_dir),
        patch.object(cli, "get_claude_dir", return_value=mock_claude_dir),
    ):
        yield mock_config_dir, mock_claude_dir


def setup_retired(cfg, cl, retired, stale=True):
    manifest = json.loads((cfg / "manifest.json").read_text())
    manifest["retired"] = retired
    (cfg / "manifest.json").write_text(json.dumps(manifest))
    (cl / "skills" / "old").mkdir(parents=True)
    (cl / "skills" / "old" / "f").write_text("x")
    (cl / "skills" / "old2").mkdir(parents=True)
    if stale:
        (cl / ".claude-setup-version.json").write_text(
            json.dumps(
                {"tool_version": "x", "config_hash": "stale", "categories": ["core"]}
            )
        )


def snapshot(directory):
    return sorted(
        (str(p.relative_to(directory)), p.read_bytes() if p.is_file() else None)
        for p in directory.rglob("*")
        if p.relative_to(directory).parts[0] != "backups" or p.is_file()
    )


def invoke(args, **kwargs):
    return CliRunner().invoke(cli.app, args, env={"COLUMNS": "300"}, **kwargs)


@pytest.mark.parametrize("answer", ["n\n", ""], ids=["no", "eof"])
def test_cli_decline_with_updates_changes_nothing(cli_env, answer):
    cfg, cl = cli_env
    setup_retired(cfg, cl, ["skills/old"])
    before = snapshot(cl)

    result = invoke(["update", "--skip-plugins"], input=answer)

    assert result.exit_code == 0
    assert "Update cancelled; nothing changed" in result.output
    assert snapshot(cl) == before


@pytest.mark.parametrize("answer", ["n\n", ""], ids=["no", "eof"])
def test_cli_decline_retired_only_after_install(cli_env, answer):
    cfg, cl = cli_env
    assert invoke(["install", "--all", "--force"]).exit_code == 0
    manifest = json.loads((cfg / "manifest.json").read_text())
    manifest["retired"] = ["skills/old"]
    (cfg / "manifest.json").write_text(json.dumps(manifest))
    (cl / "skills" / "old").mkdir(parents=True)
    before = snapshot(cl)

    result = invoke(["update", "--skip-plugins"], input=answer)

    assert result.exit_code == 0
    assert snapshot(cl) == before


def test_cli_ctrl_c_at_prompt(cli_env):
    cfg, cl = cli_env
    setup_retired(cfg, cl, ["skills/old"])
    before = snapshot(cl)
    with patch.object(cli, "confirm", side_effect=KeyboardInterrupt):
        result = invoke(["update", "--skip-plugins"])
    assert result.exit_code == 130
    assert snapshot(cl) == before


def test_cli_ctrl_c_mid_archive_then_rollback(cli_env):
    cfg, cl = cli_env
    setup_retired(cfg, cl, ["skills/old", "skills/old2"])
    real_rename = os.rename
    calls = {"n": 0}

    def rename(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return real_rename(src, dst)

    with patch.object(archive_module.os, "rename", side_effect=rename):
        result = invoke(["update", "--skip-plugins", "--yes"])

    assert result.exit_code == 130
    assert "Update interrupted" in result.output
    run = next((cl / "archived").iterdir())
    states = [
        i["state"] for i in json.loads((run / ARCHIVE_MANIFEST).read_text())["items"]
    ]
    assert states == ["done", "pending"]

    rollback = invoke(["rollback", "--force"])
    assert rollback.exit_code == 0, rollback.output
    assert (cl / "skills" / "old" / "f").read_text() == "x"
    assert (cl / "skills" / "old2").is_dir()


def test_cli_final_journal_write_fails(cli_env):
    """L1: a failing final journal write is reported, not a traceback; rollback still works."""
    cfg, cl = cli_env
    setup_retired(cfg, cl, ["skills/old"])
    real_write = archive_module.ArchiveManager._write_manifest
    calls = {"n": 0}

    def write(self, run_dir, items):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError(28, "No space left on device")
        return real_write(self, run_dir, items)

    with patch.object(archive_module.ArchiveManager, "_write_manifest", write):
        result = invoke(["update", "--skip-plugins", "--yes"])

    assert result.exit_code == 0, result.output
    assert "could not write archive journal" in result.output
    assert not (cl / "skills" / "old").exists()
    stamp = json.loads((cl / ".claude-setup-version.json").read_text())
    assert stamp["config_hash"] != "stale"

    # Journal on disk still says "pending"; rollback moves it back because it exists in the archive
    assert invoke(["rollback", "--force"]).exit_code == 0
    assert (cl / "skills" / "old" / "f").read_text() == "x"


def test_cli_status_and_rollback_with_deep_archive_manifest(cli_env):
    cfg, cl = cli_env
    setup_retired(cfg, cl, [])
    (cl / "archived" / "r").mkdir(parents=True)
    (cl / "archived" / "r" / ARCHIVE_MANIFEST).write_text("[" * 100000 + "]" * 100000)
    assert invoke(["status"]).exit_code == 0
    make_backup(
        cl,
        "claude-setup-2099",
        {"created_at": CREATED, "files": [], "archive": "archived/r"},
    )
    result = invoke(["rollback", "--force"])
    assert result.exit_code == 0, result.output
    assert "Could not move back" in result.output


def test_cli_rollback_bad_types(cli_env):
    cfg, cl = cli_env
    setup_retired(cfg, cl, [])
    make_backup(cl, "claude-setup-2030", {"files": [], "created_at": 5})
    make_backup(
        cl, "claude-setup-2031", {"files": [], "created_at": "2031-01-01T00:00:00"}
    )
    assert invoke(["rollback", "--force"]).exit_code == 0
    for manifest in [
        {"files": [], "created_at": CREATED, "categories": 5},
        {"files": [], "created_at": CREATED, "archive": ["x"]},
    ]:
        (cl / "backups" / "claude-setup-2030" / "backup-manifest.json").write_text(
            json.dumps(manifest)
        )
        result = invoke(["rollback", "--force", "claude-setup-2030"])
        assert result.exit_code == 1, result.output
        assert "not a valid backup manifest" in result.output


@pytest.mark.parametrize(
    "content",
    [
        "[" * 100000 + "]" * 100000,
        json.dumps({"sources": [{"type": "local", "path": "\x00"}]}),
        "SKILL_FILE",
        json.dumps({"sources": "x"}),
        "\xff",
    ],
)
def test_cli_sources_json_variants(cli_env, content):
    cfg, cl = cli_env
    setup_retired(cfg, cl, ["skills/old"])
    if content == "SKILL_FILE":
        content = json.dumps(
            {"sources": [{"type": "local", "path": str(cl / "skills" / "old" / "f")}]}
        )
    (cl / "sources.json").write_text(content)
    result = invoke(["update", "--check"])
    assert result.exit_code == 0, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.update(retired="skills/old"),
        lambda m: m.update(retired=[{"a": 1}, None, 5, ["skills/old"]]),
        lambda m: m["categories"][0]["files"].append(
            {"src": "core/CLAUDE.md", "dest": None}
        ),
        lambda m: m["categories"][0]["files"].append({"src": "core/CLAUDE.md"}),
        lambda m: m["categories"][0]["files"].append("str"),
        lambda m: m["categories"][0].update(target_dir=None),
        lambda m: m.update(categories=None),
        lambda m: m.update(categories=[5]),
    ],
)
def test_cli_manifest_variants_never_traceback(cli_env, mutate):
    cfg, cl = cli_env
    setup_retired(cfg, cl, [])
    manifest = json.loads((cfg / "manifest.json").read_text())
    mutate(manifest)
    (cfg / "manifest.json").write_text(json.dumps(manifest))
    for args in (
        ["update", "--check"],
        ["status"],
        ["update", "--yes", "--skip-plugins"],
    ):
        result = invoke(args)
        assert result.exit_code in (0, 1), (args, result.output)
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            args,
            result.exception,
        )
    assert (cl / "skills" / "old").exists()


@pytest.mark.parametrize(
    "entry,make", [("projects/[/b]", False), ("skills/x[/b]", True)]
)
def test_cli_rich_markup_in_paths_is_escaped(cli_env, entry, make):
    """M5: entries/paths containing Rich markup must not crash or be interpreted."""
    cfg, cl = cli_env
    (cl / ".claude-setup-version.json").write_text(
        json.dumps(
            {"tool_version": "x", "config_hash": "stale", "categories": ["core"]}
        )
    )
    manifest = json.loads((cfg / "manifest.json").read_text())
    manifest["retired"] = [entry]
    (cfg / "manifest.json").write_text(json.dumps(manifest))
    if make:
        (cl / "skills" / "x[").mkdir(parents=True)
        (cl / "skills" / "x[/b]").mkdir(parents=True)
    for args in (
        ["install", "--all", "--dry-run"],
        ["status"],
        ["update", "--skip-plugins", "--yes"],
    ):
        result = invoke(args)
        assert result.exit_code == 0, (args, result.output, result.exception)
        # Shown literally wherever the entry is reported (status lists only present, valid ones)
        if args[0] != "status" or make:
            assert "[/b]" in result.output, args


@pytest.mark.parametrize("answer", [[False], EOFError()], ids=["no", "eof"])
def test_interactive_update_decline_changes_nothing(cli_env, answer):
    cfg, cl = cli_env
    setup_retired(cfg, cl, ["skills/old"])
    before = snapshot(cl)
    with (
        patch.object(cli, "confirm", side_effect=answer),
        patch.object(cli.questionary, "confirm") as q_confirm,
    ):
        q_confirm.return_value.ask.return_value = True  # "Install updates now?" -> yes
        cli.interactive_update()
    assert snapshot(cl) == before
    assert (cl / "skills" / "old" / "f").read_text() == "x"
