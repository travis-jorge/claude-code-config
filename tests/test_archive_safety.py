"""Regression tests for archive/rollback safety issues found in review.

Each test reproduces one reported case (tampered manifests, symlinks, Unicode
normalisation, interrupted runs, malformed manifests, update prompts).
Everything runs in tmp dirs; no real ~/.claude is touched.
"""

import json
import os
import unicodedata
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import claude_setup.archive as archive_module
from claude_setup import cli
from claude_setup.archive import ARCHIVE_MANIFEST, ArchiveManager
from claude_setup.backup import BackupError, BackupManager
from claude_setup.categories import CategoryRegistry
from claude_setup.installer import Installer, ManifestEntryError
from claude_setup.plugins import PluginManager
from claude_setup.version import VersionManager


@pytest.fixture
def env(tmp_path):
    """Factory: (claude_dir, config_dir, installer) for a manifest with retired entries."""

    def make(retired, categories=None):
        claude_dir = tmp_path / "home" / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        config_dir = tmp_path / "cfg"
        config_dir.mkdir(exist_ok=True)
        manifest = {"version": "1", "retired": retired, "categories": categories or []}
        (config_dir / "manifest.json").write_text(json.dumps(manifest))
        registry = CategoryRegistry(config_dir)
        installer = Installer(
            config_dir,
            claude_dir,
            registry,
            BackupManager(claude_dir),
            VersionManager(claude_dir, config_dir),
        )
        return claude_dir, config_dir, installer

    return make


def make_run(claude_dir, name="2026-01-01-000000"):
    run = claude_dir / "archived" / name
    run.mkdir(parents=True)
    return run


def write_backup(claude_dir, manifest_content, name="claude-setup-2026-01-01-000000"):
    mgr = BackupManager(claude_dir)
    backup = mgr.backup_dir / name
    backup.mkdir()
    if isinstance(manifest_content, dict):
        manifest_content = {"created_at": "2026-01-01T00:00:00", **manifest_content}
    (backup / "backup-manifest.json").write_text(
        manifest_content
        if isinstance(manifest_content, str)
        else json.dumps(manifest_content)
    )
    return mgr, name


# --- 5: malformed archive manifests must not crash rollback -------------------


@pytest.mark.parametrize(
    "manifest",
    [
        {"items": [{"original": "skills/x", "archived": 123}]},
        {"items": 5},
        {"items": [{"original": "skills/a\x00b", "archived": "x"}]},
        {"items": [{"original": "skills/x", "archived": "a\x00b"}]},
        {"items": ["not-an-object", None]},
        [1, 2],
        "not json at all",
    ],
)
def test_malformed_archive_manifest_reported_not_crash(env, manifest):
    claude_dir, _, _ = env([])
    run = make_run(claude_dir)
    (run / "x").write_text("x")
    content = manifest if isinstance(manifest, str) else json.dumps(manifest)
    (run / ARCHIVE_MANIFEST).write_text(content)

    result = ArchiveManager(claude_dir).restore(run)

    assert result["restored"] == []
    assert result["failed"]
    assert (run / "x").read_text() == "x"
    assert not (claude_dir / "skills").exists()


@pytest.mark.parametrize("content", ["[1, 2]", "{not json", '{"files": "nope"}'])
def test_invalid_backup_manifest_fails_cleanly(env, content):
    claude_dir, _, _ = env([])
    mgr, name = write_backup(claude_dir, content)

    with pytest.raises(BackupError):
        mgr.restore_backup(name)
    # Listing still works and marks it
    assert mgr.list_backups()[0]["invalid"] is True


def test_corrupt_backup_does_not_shadow_newer_valid_one(env):
    claude_dir, _, _ = env([])
    mgr, corrupt = write_backup(
        claude_dir, "[1, 2]", name="claude-setup-2026-01-02-000000"
    )
    _, valid = write_backup(
        claude_dir,
        {
            "created_at": "2099-01-01T00:00:00",
            "files": ["CLAUDE.md"],
            "categories": ["core"],
        },
        name="claude-setup-2099-01-01-000000",
    )
    (mgr.backup_dir / valid / "CLAUDE.md").write_text("from valid backup")

    listed = mgr.list_backups()
    assert listed[0]["id"] == valid
    assert listed[1]["id"] == corrupt and listed[1]["invalid"]

    restored = mgr.restore_backup()
    assert restored.name == valid
    assert (claude_dir / "CLAUDE.md").read_text() == "from valid backup"


def test_most_recent_restore_skips_corrupt_backup(env):
    claude_dir, _, _ = env([])
    mgr, _ = write_backup(
        claude_dir, "{not json", name="claude-setup-2026-01-02-000000"
    )
    with pytest.raises(FileNotFoundError):
        mgr.restore_backup()


def test_invalid_backup_manifest_cli_exit_1(env):
    claude_dir, config_dir, installer = env([])
    _, name = write_backup(claude_dir, "[1, 2]")
    with (
        patch.object(cli, "get_claude_dir", return_value=claude_dir),
        patch.object(cli, "get_config_dir", return_value=config_dir),
    ):
        (config_dir / "plugins").mkdir()
        explicit = CliRunner().invoke(
            cli.app, ["rollback", name, "--force"], env={"COLUMNS": "300"}
        )
        default = CliRunner().invoke(
            cli.app, ["rollback", "--force"], env={"COLUMNS": "300"}
        )
    assert explicit.exit_code == 1
    assert "not a valid backup manifest" in explicit.output
    assert "Traceback" not in explicit.output
    assert default.exit_code == 1
    assert "No valid backups available" in default.output


def test_backup_files_with_traversal_ignored(env, tmp_path):
    claude_dir, _, _ = env([])
    mgr, name = write_backup(
        claude_dir, {"files": ["../escaped.txt", "/abs.txt", 5, "ok.txt"]}
    )
    backup = mgr.backup_dir / name
    (backup / "ok.txt").write_text("ok")
    (claude_dir.parent / "escaped.txt").write_text("original")

    mgr.restore_backup(name)

    assert (claude_dir / "ok.txt").read_text() == "ok"
    assert (claude_dir.parent / "escaped.txt").read_text() == "original"


# --- 3: symlinked archive-manifest.json is never followed ----------------------


def test_symlinked_manifest_not_written_through(env):
    claude_dir, _, _ = env([])
    victim = claude_dir / "settings.json"
    victim.write_text('{"items": [], "model": "mine"}')
    run = make_run(claude_dir)
    os.symlink(victim, run / ARCHIVE_MANIFEST)

    result = ArchiveManager(claude_dir).restore(run)

    assert victim.read_text() == '{"items": [], "model": "mine"}'
    assert "symlink" in result["failed"][0][1]


def test_manifest_written_atomically_replacing_symlink(env):
    """Even if a symlink appears at the manifest path, writing replaces the link, not its target."""
    claude_dir, _, _ = env([])
    victim = claude_dir / "settings.json"
    victim.write_text("keep")
    run = make_run(claude_dir)
    os.symlink(victim, run / ARCHIVE_MANIFEST)

    ArchiveManager(claude_dir)._write_manifest(run, [])

    assert victim.read_text() == "keep"
    assert not (run / ARCHIVE_MANIFEST).is_symlink()
    assert json.loads((run / ARCHIVE_MANIFEST).read_text())["items"] == []


# --- 2: rollback never pulls files from outside ~/.claude ---------------------


def test_symlinked_run_dir_outside_refused(env, tmp_path):
    claude_dir, _, _ = env([])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside data")
    (outside / ARCHIVE_MANIFEST).write_text(
        json.dumps({"items": [{"original": "skills/stolen", "archived": "secret.txt"}]})
    )
    (claude_dir / "archived").mkdir()
    os.symlink(outside, claude_dir / "archived" / "evil")
    mgr, name = write_backup(
        claude_dir, {"files": [], "categories": [], "archive": "archived/evil"}
    )

    mgr.restore_backup(name)

    assert (outside / "secret.txt").read_text() == "outside data"
    assert not (claude_dir / "skills" / "stolen").exists()
    assert mgr.last_archive_restore["failed"]
    # Direct call is refused too
    assert ArchiveManager(claude_dir).restore(claude_dir / "archived" / "evil")[
        "failed"
    ]


def test_symlinked_archive_root_refused_for_restore(env, tmp_path):
    claude_dir, _, _ = env([])
    outside = tmp_path / "outside"
    (outside / "run").mkdir(parents=True)
    (outside / "run" / "f").write_text("o")
    (outside / "run" / ARCHIVE_MANIFEST).write_text(
        json.dumps({"items": [{"original": "skills/f", "archived": "f"}]})
    )
    os.symlink(outside, claude_dir / "archived")

    result = ArchiveManager(claude_dir).restore(claude_dir / "archived" / "run")

    assert result["failed"] and result["restored"] == []
    assert (outside / "run" / "f").exists()


def test_symlink_component_inside_run_dir_refused(env, tmp_path):
    claude_dir, _, _ = env([])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f").write_text("o")
    run = make_run(claude_dir)
    os.symlink(outside, run / "lnk")
    (run / ARCHIVE_MANIFEST).write_text(
        json.dumps({"items": [{"original": "skills/f", "archived": "lnk/f"}]})
    )

    result = ArchiveManager(claude_dir).restore(run)

    assert result["restored"] == []
    assert "symlink" in result["failed"][0][1]
    assert (outside / "f").read_text() == "o"
    assert not (claude_dir / "skills" / "f").exists()


@pytest.mark.parametrize(
    "original", ["projects/x", "settings.json", "../x", "skills", "/tmp/x"]
)
def test_restore_original_must_pass_allowlist(env, original):
    claude_dir, _, _ = env([])
    run = make_run(claude_dir)
    (run / "item").write_text("x")
    (run / ARCHIVE_MANIFEST).write_text(
        json.dumps({"items": [{"original": original, "archived": "item"}]})
    )

    result = ArchiveManager(claude_dir).restore(run)

    assert result["restored"] == [] and result["failed"]
    assert (run / "item").exists()


def test_restore_original_with_symlinked_parent_refused(env, tmp_path):
    claude_dir, _, _ = env([])
    outside = tmp_path / "outside"
    outside.mkdir()
    (claude_dir / "skills").symlink_to(outside, target_is_directory=True)
    run = make_run(claude_dir)
    (run / "item").write_text("x")
    (run / ARCHIVE_MANIFEST).write_text(
        json.dumps({"items": [{"original": "skills/item", "archived": "item"}]})
    )

    result = ArchiveManager(claude_dir).restore(run)

    assert result["restored"] == [] and "symlink" in result["failed"][0][1]
    assert list(outside.iterdir()) == []


def test_restore_archived_leaf_symlink_moved_as_link(env, tmp_path):
    claude_dir, _, _ = env([])
    target = tmp_path / "target"
    target.mkdir()
    run = make_run(claude_dir)
    os.symlink(target, run / "linked")
    (run / ARCHIVE_MANIFEST).write_text(
        json.dumps({"items": [{"original": "skills/linked", "archived": "linked"}]})
    )

    result = ArchiveManager(claude_dir).restore(run)

    assert result["restored"] == [claude_dir / "skills" / "linked"]
    assert (claude_dir / "skills" / "linked").is_symlink()
    assert target.is_dir()


# --- 1: allowlist and symlinked parents ---------------------------------------


@pytest.mark.parametrize(
    "target_dir",
    [
        ".claude/projects",
        ".claude/todos",
        ".claude/shell-snapshots",
        ".claude/file-history",
        ".claude/ide",
    ],
)
def test_category_cannot_widen_allowlist(env, target_dir):
    rel = target_dir.split("/", 1)[1]
    cats = [
        {
            "name": "x",
            "description": "x",
            "target_dir": target_dir,
            "install_type": "overwrite",
            "files": [],
        }
    ]
    claude_dir, _, installer = env([f"{rel}/a"], cats)
    (claude_dir / rel / "a").mkdir(parents=True)

    result = installer.compute_retired()

    assert result["archive"] == []
    assert "only paths inside" in result["refused"][0][1]


def test_symlinked_parent_into_projects_refused(env):
    claude_dir, _, installer = env(["skills/linkdir/-Users-me-app"])
    project = claude_dir / "projects" / "-Users-me-app"
    project.mkdir(parents=True)
    (project / "s.jsonl").write_text("h")
    (claude_dir / "skills").mkdir()
    os.symlink(claude_dir / "projects", claude_dir / "skills" / "linkdir")

    path, reason = installer.validate_retired_path("skills/linkdir/-Users-me-app")
    installer.install([], force=True)

    assert path is None and "symlink" in reason
    assert (project / "s.jsonl").read_text() == "h"


def test_symlinked_allowlisted_root_refused(env, tmp_path):
    claude_dir, _, installer = env(["skills/x"])
    real = tmp_path / "dotfiles-skills"
    (real / "x").mkdir(parents=True)
    (claude_dir / "skills").symlink_to(real, target_is_directory=True)

    path, reason = installer.validate_retired_path("skills/x")

    assert path is None and "'skills' is a symlink" in reason


def test_symlinked_archive_root_refused_for_archiving(env, tmp_path):
    claude_dir, _, installer = env(["skills/old"])
    (claude_dir / "skills" / "old").mkdir(parents=True)
    (claude_dir / "skills" / "old" / "f").write_text("x")
    out = tmp_path / "out"
    out.mkdir()
    os.symlink(out, claude_dir / "archived")

    result = installer.install([], force=True)

    assert result["retired"]["archived"] == []
    assert any("symlink" in reason for _, reason in result["retired"]["refused"])
    assert (claude_dir / "skills" / "old" / "f").exists()
    assert list(out.iterdir()) == []


def test_archive_manager_refuses_symlinked_root_directly(env, tmp_path):
    claude_dir, _, _ = env([])
    (claude_dir / "skills" / "old").mkdir(parents=True)
    out = tmp_path / "out"
    out.mkdir()
    os.symlink(out, claude_dir / "archived")

    outcome = ArchiveManager(claude_dir).archive(
        [claude_dir / "skills" / "old"], claude_dir / "archived" / "r"
    )

    assert outcome["moved"] == [] and "symlink" in outcome["failed"][0][1]
    assert (claude_dir / "skills" / "old").is_dir()


def test_leaf_symlink_moved_as_link(env, tmp_path):
    claude_dir, _, installer = env(["skills/x"])
    out = tmp_path / "outdir"
    out.mkdir()
    (out / "keep").write_text("k")
    (claude_dir / "skills").mkdir()
    os.symlink(out, claude_dir / "skills" / "x")

    result = installer.install([], force=True)

    dest = Path(result["retired"]["archived"][0][1])
    assert dest.is_symlink()
    assert (out / "keep").read_text() == "k"


def test_local_source_from_sources_json_protected(env, tmp_path):
    claude_dir, _, installer = env(["skills/team-config"])
    source = claude_dir / "skills" / "team-config"
    source.mkdir(parents=True)
    (claude_dir / "sources.json").write_text(
        json.dumps({"sources": [{"type": "local", "path": str(source)}]})
    )

    path, reason = installer.validate_retired_path("skills/team-config")

    assert path is None and "configuration source" in reason


def test_odd_sources_json_tolerated(env):
    claude_dir, _, installer = env(["skills/x"])
    (claude_dir / "sources.json").write_text(
        '{"sources": [5, {"type": "local", "path": 3}, {"type": "local", "path": "a\\u0000b"}]}'
    )
    assert installer.validate_retired_path("skills/x")[1] is None


# --- 4: Unicode normalisation -------------------------------------------------


def test_nfd_entry_overlapping_nfc_install_dest_refused(env):
    nfc = unicodedata.normalize("NFC", "café")
    nfd = unicodedata.normalize("NFD", "café")
    assert nfc != nfd
    cats = [
        {
            "name": "sk",
            "description": "x",
            "target_dir": ".claude",
            "install_type": "overwrite",
            "files": [{"src": "s/SKILL.md", "dest": f"skills/{nfc}/SKILL.md"}],
        }
    ]
    claude_dir, config_dir, installer = env([f"skills/{nfd}"], cats)
    (config_dir / "s").mkdir()
    (config_dir / "s" / "SKILL.md").write_text("new")
    (claude_dir / "skills" / nfc).mkdir(parents=True)
    (claude_dir / "skills" / nfc / "SKILL.md").write_text("old")

    path, reason = installer.validate_retired_path(f"skills/{nfd}")
    result = installer.install(["sk"], force=True)

    assert path is None and "overlaps" in reason
    assert (claude_dir / "skills" / nfc / "SKILL.md").read_text() == "new"
    assert result["retired"]["archived"] == []


def test_nfd_duplicates_collapsed(env):
    nfc = unicodedata.normalize("NFC", "café")
    nfd = unicodedata.normalize("NFD", "café")
    claude_dir, _, installer = env([f"skills/{nfc}", f"skills/{nfd}"])
    (claude_dir / "skills" / nfc).mkdir(parents=True)
    assert len(installer.compute_retired()["archive"]) == 1


# --- 6: Ctrl-C mid-archive is journaled and rollback-able ---------------------


def test_interrupted_archive_is_journaled_and_rolled_back(env):
    claude_dir, _, installer = env(["skills/a", "skills/b"])
    for name in "ab":
        (claude_dir / "skills" / name).mkdir(parents=True)
        (claude_dir / "skills" / name / "SKILL.md").write_text(name)

    real_rename = os.rename
    calls = {"n": 0}

    def interrupt_second(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        real_rename(src, dst)

    with patch.object(archive_module.os, "rename", interrupt_second):
        with pytest.raises(KeyboardInterrupt):
            installer.install([], force=True)

    run = next((claude_dir / "archived").iterdir())
    items = json.loads((run / ARCHIVE_MANIFEST).read_text())["items"]
    assert [(i["original"], i["state"]) for i in items] == [
        ("skills/a", "done"),
        ("skills/b", "pending"),
    ]
    assert (claude_dir / "skills" / "b" / "SKILL.md").read_text() == "b"  # never moved

    mgr = BackupManager(claude_dir)
    mgr.restore_backup(mgr.list_backups()[0]["id"])

    restore = mgr.last_archive_restore
    assert restore["restored"] == [claude_dir / "skills" / "a"]
    assert (claude_dir / "skills" / "a" / "SKILL.md").read_text() == "a"
    assert (claude_dir / "skills" / "b" / "SKILL.md").read_text() == "b"


def test_journal_written_before_move(env):
    claude_dir, _, installer = env(["skills/a"])
    (claude_dir / "skills" / "a").mkdir(parents=True)
    seen = {}
    real_rename = os.rename

    def check_journal(src, dst):
        run = next((claude_dir / "archived").iterdir())
        seen["items"] = json.loads((run / ARCHIVE_MANIFEST).read_text())["items"]
        real_rename(src, dst)

    with patch.object(archive_module.os, "rename", check_journal):
        installer.install([], force=True)

    assert seen["items"] == [
        {"original": "skills/a", "archived": "skills/a", "state": "pending"}
    ]


# --- 8: malformed manifest file entries ---------------------------------------


@pytest.mark.parametrize(
    "bad_file",
    [{"src": "a", "dest": None}, {"src": None, "dest": "x"}, {"src": "a", "dest": 5}],
)
def test_malformed_file_entry_refuses_all_retired(env, bad_file):
    cats = [
        {
            "name": "x",
            "description": "x",
            "target_dir": ".claude",
            "install_type": "overwrite",
            "files": [bad_file],
        }
    ]
    claude_dir, _, installer = env(["skills/a"], cats)
    (claude_dir / "skills" / "a").mkdir(parents=True)

    retired = installer.compute_retired()

    assert retired["archive"] == []
    assert "invalid 'src' or 'dest'" in retired["refused"][0][1]
    assert installer.get_retired_present() == []
    with pytest.raises(ManifestEntryError):
        installer.compute_plan(["x"])


def test_malformed_file_entry_cli_status_and_update(env):
    cats = [
        {
            "name": "core",
            "description": "x",
            "target_dir": ".claude",
            "install_type": "overwrite",
            "files": [{"src": "a", "dest": None}],
        }
    ]
    claude_dir, config_dir, installer = env(["skills/a"], cats)
    (claude_dir / "skills" / "a").mkdir(parents=True)
    (claude_dir / ".claude-setup-version.json").write_text(
        json.dumps({"config_hash": "stale", "categories": ["core"]})
    )

    with (
        patch.object(cli, "get_claude_dir", return_value=claude_dir),
        patch.object(cli, "get_config_dir", return_value=config_dir),
    ):
        status = CliRunner().invoke(cli.app, ["status"])
        update = CliRunner().invoke(
            cli.app, ["update", "--skip-plugins", "--yes"], env={"COLUMNS": "300"}
        )

    assert status.exit_code == 0, status.output
    assert update.exit_code == 1
    assert "invalid 'src' or 'dest'" in update.output
    assert "Traceback" not in update.output
    assert (claude_dir / "skills" / "a").is_dir()


# --- 7: update declines / Ctrl-C ----------------------------------------------


def _up_to_date_with_retired(env):
    claude_dir, config_dir, installer = env(["skills/old"])
    (config_dir / "core").mkdir()
    (config_dir / "core" / "CLAUDE.md").write_text("team")
    manifest = json.loads((config_dir / "manifest.json").read_text())
    manifest["categories"] = [
        {
            "name": "core",
            "description": "x",
            "target_dir": ".claude",
            "install_type": "overwrite",
            "files": [{"src": "core/CLAUDE.md", "dest": "CLAUDE.md"}],
        }
    ]
    (config_dir / "manifest.json").write_text(json.dumps(manifest))
    installer.registry = CategoryRegistry(config_dir)
    installer.install(
        ["core"], force=True, archive_retired=False
    )  # stamp written, up to date
    (claude_dir / "CLAUDE.md").write_text("MY LOCAL EDITS")
    (claude_dir / "skills" / "old").mkdir(parents=True)
    plugin_mgr = PluginManager(claude_dir, [])
    managers = (
        installer.registry,
        installer.backup_mgr,
        installer.version_mgr,
        plugin_mgr,
        installer,
    )
    return claude_dir, managers


@pytest.mark.parametrize("answer", [[False], EOFError()])
def test_update_decline_with_only_retired_changes_installs_nothing(env, answer):
    claude_dir, managers = _up_to_date_with_retired(env)

    with (
        patch.object(cli, "initialize_managers", return_value=managers),
        patch.object(cli, "confirm", side_effect=answer),
    ):
        result = CliRunner().invoke(cli.app, ["update", "--skip-plugins"])

    assert result.exit_code == 0, result.output
    assert (claude_dir / "CLAUDE.md").read_text() == "MY LOCAL EDITS"
    assert (claude_dir / "skills" / "old").is_dir()
    assert not (claude_dir / "archived").exists()


def test_update_ctrl_c_aborts_nonzero(env):
    claude_dir, managers = _up_to_date_with_retired(env)

    with (
        patch.object(cli, "initialize_managers", return_value=managers),
        patch.object(cli, "confirm", side_effect=KeyboardInterrupt()),
    ):
        result = CliRunner().invoke(cli.app, ["update", "--skip-plugins"])

    assert result.exit_code == 130
    assert (claude_dir / "CLAUDE.md").read_text() == "MY LOCAL EDITS"
    assert (claude_dir / "skills" / "old").is_dir()


def test_interactive_update_ctrl_c_returns_without_changes(env):
    claude_dir, managers = _up_to_date_with_retired(env)

    with (
        patch.object(cli, "initialize_managers", return_value=managers),
        patch.object(cli, "confirm", side_effect=KeyboardInterrupt()),
        patch.object(cli.questionary, "confirm") as q_confirm,
    ):
        q_confirm.return_value.ask.return_value = True
        cli.interactive_update()

    assert (claude_dir / "CLAUDE.md").read_text() == "MY LOCAL EDITS"
    assert (claude_dir / "skills" / "old").is_dir()


def test_update_accept_with_only_retired_changes_archives(env):
    claude_dir, managers = _up_to_date_with_retired(env)

    with (
        patch.object(cli, "initialize_managers", return_value=managers),
        patch.object(cli, "confirm", side_effect=[True]),
    ):
        result = CliRunner().invoke(cli.app, ["update", "--skip-plugins"])

    assert result.exit_code == 0, result.output
    assert not (claude_dir / "skills" / "old").exists()
    assert len(list((claude_dir / "archived").glob("*/skills/old"))) == 1


def test_interrupt_during_manifest_write_still_journals(env):
    """Repro: Ctrl-C inside the atomic manifest replace must not break the final journal write."""
    claude_dir, _, installer = env(["skills/a", "skills/b"])
    for name in "ab":
        (claude_dir / "skills" / name).mkdir(parents=True)
        (claude_dir / "skills" / name / "SKILL.md").write_text(name)

    real_replace = os.replace
    calls = {"n": 0}

    def interrupt_second(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        real_replace(src, dst)

    with patch.object(archive_module.os, "replace", interrupt_second):
        with pytest.raises(KeyboardInterrupt):
            installer.install([], force=True)

    run = next((claude_dir / "archived").iterdir())
    items = json.loads((run / ARCHIVE_MANIFEST).read_text())["items"]
    assert [(i["original"], i["state"]) for i in items] == [
        ("skills/a", "done"),
        ("skills/b", "pending"),
    ]

    mgr = BackupManager(claude_dir)
    mgr.restore_backup(mgr.list_backups()[0]["id"])
    assert (claude_dir / "skills" / "a" / "SKILL.md").read_text() == "a"
    assert (claude_dir / "skills" / "b" / "SKILL.md").read_text() == "b"


def test_cli_rollback_default_skips_corrupt_backup(env):
    claude_dir, config_dir, _ = env([])
    (config_dir / "plugins").mkdir()
    mgr, _ = write_backup(claude_dir, "[1, 2]", name="claude-setup-2026-01-02-000000")
    _, valid = write_backup(
        claude_dir,
        {"created_at": "2099-01-01T00:00:00", "files": [], "categories": ["core"]},
        name="claude-setup-2099-01-01-000000",
    )
    with (
        patch.object(cli, "get_claude_dir", return_value=claude_dir),
        patch.object(cli, "get_config_dir", return_value=config_dir),
    ):
        result = CliRunner().invoke(
            cli.app, ["rollback", "--force"], env={"COLUMNS": "300"}
        )
    assert result.exit_code == 0, result.output
    assert valid in result.output
