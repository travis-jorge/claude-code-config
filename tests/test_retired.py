"""Tests for manifest "retired" paths: validation, archiving (move, never delete),
dry run, status and rollback."""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_setup.archive import ARCHIVE_MANIFEST, ArchiveManager, unique_path
from claude_setup.backup import BackupManager
from claude_setup.categories import CategoryRegistry
from claude_setup.installer import Installer
from claude_setup.version import VersionManager


def set_manifest(config_dir, retired=None, extra_categories=()):
    manifest_path = config_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if retired is not None:
        manifest["retired"] = retired
    manifest["categories"].extend(extra_categories)
    manifest_path.write_text(json.dumps(manifest))


def make_installer(config_dir, claude_dir):
    registry = CategoryRegistry(config_dir)
    return Installer(
        config_dir,
        claude_dir,
        registry,
        BackupManager(claude_dir),
        VersionManager(claude_dir, config_dir),
    )


def archive_runs(claude_dir):
    root = claude_dir / "archived"
    return sorted(p for p in root.iterdir()) if root.exists() else []


@pytest.fixture
def old_content(mock_claude_dir):
    """Populate ~/.claude with content the team has retired."""
    skill = mock_claude_dir / "skills" / "old-skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# old skill")
    (skill / "scripts" / "run.sh").write_text("echo old")
    (mock_claude_dir / "agents").mkdir()
    (mock_claude_dir / "agents" / "old.md").write_text("old agent")
    (mock_claude_dir / "agents" / "keep.md").write_text("keep me")
    return mock_claude_dir


class TestManifestLoading:
    def test_retired_defaults_to_empty(self, mock_config_dir):
        assert CategoryRegistry(mock_config_dir).retired == []

    def test_retired_loaded(self, mock_config_dir):
        set_manifest(mock_config_dir, ["skills/old-skill", "agents/old.md"])
        assert CategoryRegistry(mock_config_dir).retired == [
            "skills/old-skill",
            "agents/old.md",
        ]

    def test_non_list_retired_ignored(self, mock_config_dir):
        set_manifest(mock_config_dir, "skills/old-skill")
        assert CategoryRegistry(mock_config_dir).retired == []


class TestValidation:
    @pytest.mark.parametrize(
        "entry",
        [
            # not under an allowlisted directory
            "projects/some-project",
            "plugins/cache",
            "plugins/installed_plugins.json",
            "todos/x.json",
            "shell-snapshots/snap.sh",
            "statsig/cache",
            "ide/1234.lock",
            ".credentials.json",
            "history.jsonl",
            "settings.json",
            "settings.local.json",
            ".claude-setup-version.json",
            "CLAUDE.md",
            "statusline.sh",
            "archived/2026-01-01-000000",
            "Archived/x",
            "backups",
            "backups/claude-setup-2024-01-01-000000",
            "Backups",
            "BACKUPS/claude-setup-2024-01-01-000000",
            "sources/team-config",
            "SOURCES/x",
            "rules/old.md",  # no category installs into rules/ in this manifest
            # the allowlisted directories themselves
            "skills",
            "Skills/",
            "Skills/Old-Skill",  # allowlist root is case-sensitive
            "SKILLS/x",
            "\u017fkills/x",  # long s folds to "s"; must not match skills/
            "agents",
            "commands",
            # structural problems
            "",
            ".",
            "./",
            "/",
            "/etc/passwd",
            "~/.ssh",
            "C:\\Windows",
            "\\\\server\\share",
            "..",
            "../outside",
            "skills/../../outside",
            "skills/..",
            "skills\\..\\..\\outside",
            "skills/a\x00b",
            "skills/bad\nname",
            None,
            42,
            ["skills"],
        ],
    )
    def test_refused_entries(self, mock_config_dir, mock_claude_dir, entry):
        installer = make_installer(mock_config_dir, mock_claude_dir)
        path, reason = installer.validate_retired_path(entry)
        assert path is None
        assert reason

    def test_nul_byte_does_not_crash_plan(self, mock_config_dir, mock_claude_dir):
        set_manifest(mock_config_dir, ["skills/a\x00b", "agents/old.md"])
        installer = make_installer(mock_config_dir, mock_claude_dir)
        result = installer.compute_retired()
        assert [e for e, _ in result["refused"]] == ["skills/a\x00b"]

    def test_value_error_during_resolution_is_refused(
        self, mock_config_dir, mock_claude_dir
    ):
        installer = make_installer(mock_config_dir, mock_claude_dir)
        with patch.object(
            Path, "resolve", side_effect=ValueError("embedded null byte")
        ):
            path, reason = installer.validate_retired_path("skills/x")
        assert path is None and "invalid path" in reason

    def test_parent_symlink_outside_refused(
        self, mock_config_dir, mock_claude_dir, temp_dir
    ):
        outside = temp_dir / "outside"
        outside.mkdir()
        (outside / "precious").mkdir()
        (mock_claude_dir / "skills").symlink_to(outside, target_is_directory=True)

        installer = make_installer(mock_config_dir, mock_claude_dir)
        path, reason = installer.validate_retired_path("skills/precious")

        assert path is None
        assert "symlink" in reason

    @pytest.mark.parametrize(
        "entry",
        [
            "skills/old-skill",
            "agents/old.md",
            "commands/old.md",
            "./agents/old.md",
            "skills/old-skill/",
        ],
    )
    def test_valid_entries(self, mock_config_dir, mock_claude_dir, entry):
        installer = make_installer(mock_config_dir, mock_claude_dir)
        path, reason = installer.validate_retired_path(entry)
        assert reason is None, entry
        assert mock_claude_dir in path.parents

    def test_category_target_dirs_do_not_extend_allowlist(
        self, mock_config_dir, mock_claude_dir
    ):
        """Fixed allowlist: a category installing into rules/, projects/ etc. doesn't make it retirable."""
        cats = [
            {
                "name": n,
                "description": n,
                "target_dir": f".claude/{n}",
                "install_type": "overwrite",
                "files": [],
            }
            for n in [
                "rules",
                "projects",
                "todos",
                "shell-snapshots",
                "file-history",
                "session-env",
                "ide",
                "statsig",
            ]
        ]
        set_manifest(mock_config_dir, extra_categories=cats)
        installer = make_installer(mock_config_dir, mock_claude_dir)

        for cat in cats:
            entry = cat["target_dir"].split("/", 1)[1] + "/a"
            path, reason = installer.validate_retired_path(entry)
            assert path is None and "only paths inside" in reason, entry

    def test_overlap_with_installed_dest_refused(
        self, mock_config_dir, mock_claude_dir
    ):
        set_manifest(
            mock_config_dir,
            extra_categories=[
                {
                    "name": "skills",
                    "description": "Skills",
                    "target_dir": ".claude/skills",
                    "install_type": "overwrite",
                    "files": [
                        {"src": "core/CLAUDE.md", "dest": "team/SKILL.md"},
                    ],
                }
            ],
        )
        installer = make_installer(mock_config_dir, mock_claude_dir)
        for entry in ["skills/team", "skills/TEAM/skill.md", "skills/Team"]:
            path, reason = installer.validate_retired_path(entry)
            assert path is None and "overlaps" in reason, entry


class TestPlan:
    def test_dry_run_lists_archive_destinations_without_touching(
        self, mock_config_dir, old_content
    ):
        set_manifest(
            mock_config_dir,
            [
                "skills/old-skill",
                "agents/old.md",
                "agents/never-existed.md",
                "../escape",
            ],
        )
        installer = make_installer(mock_config_dir, old_content)

        result = installer.install(["core"], dry_run=True)

        archive = result["plan"]["Archive"]
        assert [p for p, _ in archive] == [
            old_content / "skills" / "old-skill",
            old_content / "agents" / "old.md",
        ]
        run_dir = installer.planned_archive_dir
        assert run_dir.parent == old_content / "archived"
        assert archive[0][1] == f"Move to {run_dir / 'skills' / 'old-skill'}"
        assert [e for e, _ in result["plan"]["Refused"]] == ["../escape"]
        assert (old_content / "skills" / "old-skill" / "SKILL.md").exists()
        assert (old_content / "agents" / "old.md").exists()
        assert not (old_content / "archived").exists()

    def test_retired_present(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["skills/old-skill", "agents/gone.md"])
        installer = make_installer(mock_config_dir, old_content)
        assert installer.get_retired_present() == [old_content / "skills" / "old-skill"]

    def test_duplicates_collapsed(self, mock_config_dir, old_content):
        set_manifest(
            mock_config_dir, ["agents/old.md", "./agents/old.md", "AGENTS/old.md"]
        )
        installer = make_installer(mock_config_dir, old_content)
        assert installer.compute_retired()["archive"] == [
            old_content / "agents" / "old.md"
        ]

    def test_nested_entries_counted_once(self, mock_config_dir, old_content):
        set_manifest(
            mock_config_dir,
            ["skills/old-skill/scripts", "skills/old-skill", "skills/missing"],
        )
        installer = make_installer(mock_config_dir, old_content)

        retired = installer.compute_retired()
        assert retired["archive"] == [old_content / "skills" / "old-skill"]
        assert retired["covered"] == [old_content / "skills" / "old-skill" / "scripts"]
        assert retired["absent"] == [old_content / "skills" / "missing"]

        result = installer.install(["core"])
        assert result["stats"]["archived"] == 1
        assert result["retired"]["failed"] == []


class TestInstallArchivesRetired:
    def test_moves_into_archive(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["skills/old-skill", "agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)

        result = installer.install(["core"])

        assert not (old_content / "skills" / "old-skill").exists()
        assert not (old_content / "agents" / "old.md").exists()
        assert (old_content / "agents" / "keep.md").read_text() == "keep me"
        assert result["stats"]["archived"] == 2

        runs = archive_runs(old_content)
        assert len(runs) == 1
        run = runs[0]
        assert result["retired"]["archive_dir"] == str(run)
        assert (run / "skills" / "old-skill" / "SKILL.md").read_text() == "# old skill"
        assert (
            run / "skills" / "old-skill" / "scripts" / "run.sh"
        ).read_text() == "echo old"
        assert (run / "agents" / "old.md").read_text() == "old agent"

        items = json.loads((run / ARCHIVE_MANIFEST).read_text())["items"]
        assert {i["original"] for i in items} == {"skills/old-skill", "agents/old.md"}

    def test_backup_links_archive_and_does_not_copy_retired(
        self, mock_config_dir, old_content
    ):
        set_manifest(mock_config_dir, ["skills/old-skill"])
        installer = make_installer(mock_config_dir, old_content)

        result = installer.install(["core"])

        backup = Path(result["backup_path"])
        manifest = json.loads((backup / "backup-manifest.json").read_text())
        assert manifest["archive"] == str(
            archive_runs(old_content)[0].relative_to(old_content)
        )
        assert not any(f.startswith("skills/") for f in manifest["files"])
        assert not (backup / "skills").exists()

    def test_archive_only_change_still_creates_linked_backup(
        self, mock_config_dir, old_content
    ):
        installer = make_installer(mock_config_dir, old_content)
        installer.install(["core"])  # files now up to date
        set_manifest(mock_config_dir, ["agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)
        plan = installer.compute_plan(["core"])
        assert plan["Updated"] == [] and plan["New"] == []

        result = installer.install(["core"])

        assert result["backup_path"]
        manifest = json.loads(
            (Path(result["backup_path"]) / "backup-manifest.json").read_text()
        )
        assert manifest["archive"].startswith("archived/")

    def test_never_deletes(self, mock_config_dir, old_content):
        """No delete primitive is used anywhere on the retired code path."""
        set_manifest(mock_config_dir, ["skills/old-skill", "agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)

        with (
            patch("shutil.rmtree") as rmtree,
            patch("os.unlink") as unlink,
            patch("os.remove") as remove,
            patch("os.rmdir") as rmdir,
            patch.object(Path, "unlink") as path_unlink,
            patch.object(Path, "rmdir") as path_rmdir,
        ):
            result = installer.install(["core"])

        assert result["stats"]["archived"] == 2
        for mock in (rmtree, unlink, remove, rmdir, path_unlink, path_rmdir):
            mock.assert_not_called()

    def test_declining_leaves_paths_in_place(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)

        result = installer.install(["core"], archive_retired=False)

        assert (old_content / "agents" / "old.md").exists()
        assert result["stats"]["archived"] == 0
        assert result["retired"]["skipped"] == [str(old_content / "agents" / "old.md")]
        assert not (old_content / "archived").exists()

    def test_refused_entries_never_touched(
        self, mock_config_dir, old_content, temp_dir
    ):
        outside = temp_dir / "outside.txt"
        outside.write_text("precious")
        (old_content / "backups" / "keep-me").mkdir(parents=True)
        (old_content / "projects" / "p").mkdir(parents=True)
        (old_content / "history.jsonl").write_text("{}")
        set_manifest(
            mock_config_dir,
            [
                str(outside),
                "../outside.txt",
                "",
                ".",
                "backups",
                "Backups",
                "backups/keep-me",
                "projects/p",
                "history.jsonl",
                "agents",
                "agents/../agents/keep.md",
            ],
        )
        installer = make_installer(mock_config_dir, old_content)

        result = installer.install(["core"])

        assert outside.read_text() == "precious"
        assert (old_content / "backups" / "keep-me").is_dir()
        assert (old_content / "projects" / "p").is_dir()
        assert (old_content / "history.jsonl").exists()
        assert (old_content / "agents" / "keep.md").exists()
        assert result["stats"]["archived"] == 0
        assert len(result["retired"]["refused"]) == 11
        assert not (old_content / "archived").exists()

    def test_symlink_moved_as_link(self, mock_config_dir, mock_claude_dir, temp_dir):
        target = temp_dir / "real-skill"
        target.mkdir()
        (target / "SKILL.md").write_text("real")
        (mock_claude_dir / "skills").mkdir()
        (mock_claude_dir / "skills" / "linked").symlink_to(
            target, target_is_directory=True
        )
        set_manifest(mock_config_dir, ["skills/linked"])
        installer = make_installer(mock_config_dir, mock_claude_dir)

        installer.install(["core"])

        assert not os.path.lexists(mock_claude_dir / "skills" / "linked")
        archived = archive_runs(mock_claude_dir)[0] / "skills" / "linked"
        assert archived.is_symlink()
        assert os.readlink(archived) == str(target)
        assert (target / "SKILL.md").read_text() == "real"

    def test_absent_retired_is_noop(self, mock_config_dir, mock_claude_dir):
        set_manifest(mock_config_dir, ["skills/never-there"])
        installer = make_installer(mock_config_dir, mock_claude_dir)
        result = installer.install(["core"])
        assert result["stats"]["archived"] == 0
        assert result["plan"]["Archive"] == []
        assert result["retired"]["archive_dir"] is None
        assert not (mock_claude_dir / "archived").exists()

    def test_move_failure_left_in_place_and_reported(
        self, mock_config_dir, old_content
    ):
        set_manifest(mock_config_dir, ["agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)

        with patch(
            "claude_setup.archive.os.rename", side_effect=OSError("cross-device link")
        ):
            result = installer.install(["core"])

        assert (old_content / "agents" / "old.md").read_text() == "old agent"
        assert result["stats"]["archived"] == 0
        assert "cross-device" in result["retired"]["failed"][0][1]


class TestUniqueNames:
    def test_unique_path(self, tmp_path):
        assert unique_path(tmp_path / "a") == tmp_path / "a"
        (tmp_path / "a").mkdir()
        (tmp_path / "a-1").write_text("x")
        assert unique_path(tmp_path / "a") == tmp_path / "a-2"

    def test_next_run_dir_avoids_existing(self, tmp_path):
        mgr = ArchiveManager(tmp_path)
        now = datetime(2026, 11, 17, 10, 6, 5)
        (tmp_path / "archived" / "2026-11-17-100605").mkdir(parents=True)
        assert mgr.next_run_dir(now) == tmp_path / "archived" / "2026-11-17-100605-1"

    def test_existing_run_dir_not_reused(self, tmp_path):
        (tmp_path / "skills" / "x").mkdir(parents=True)
        (tmp_path / "skills" / "x" / "SKILL.md").write_text("new")
        run = tmp_path / "archived" / "run"
        (run / "skills" / "x").mkdir(parents=True)
        (run / "skills" / "x" / "SKILL.md").write_text("already archived")

        outcome = ArchiveManager(tmp_path).archive([tmp_path / "skills" / "x"], run)

        assert outcome["moved"] == []
        assert "cannot create archive folder" in outcome["failed"][0][1]
        assert (run / "skills" / "x" / "SKILL.md").read_text() == "already archived"
        assert (tmp_path / "skills" / "x" / "SKILL.md").read_text() == "new"

    def test_destination_collision_gets_unique_name(self, tmp_path):
        (tmp_path / "skills" / "x").mkdir(parents=True)
        run = tmp_path / "archived" / "run"
        real_mkdir = Path.mkdir

        def mkdir_then_collide(self, *args, **kwargs):
            real_mkdir(self, *args, **kwargs)
            if self == run:
                # Something already sits at the destination inside the fresh run dir
                real_mkdir(run / "skills" / "x", parents=True)

        with patch.object(Path, "mkdir", mkdir_then_collide):
            outcome = ArchiveManager(tmp_path).archive([tmp_path / "skills" / "x"], run)

        assert outcome["moved"] == [(tmp_path / "skills" / "x", run / "skills" / "x-1")]
        assert (run / "skills" / "x").is_dir()

    def test_planned_dir_matches_actual(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)
        planned = installer.compute_plan(["core"])["Archive"][0][1]

        result = installer.install(["core"])

        assert planned == f"Move to {result['retired']['archived'][0][1]}"


class TestRollback:
    def test_rollback_moves_archived_items_back(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["skills/old-skill", "agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)
        installer.install(["core"])

        installer.backup_mgr.restore_backup()

        restore = installer.backup_mgr.last_archive_restore
        assert sorted(restore["restored"]) == sorted(
            [old_content / "skills" / "old-skill", old_content / "agents" / "old.md"]
        )
        assert restore["conflicts"] == []
        assert (
            old_content / "skills" / "old-skill" / "scripts" / "run.sh"
        ).read_text() == "echo old"
        assert (old_content / "agents" / "old.md").read_text() == "old agent"
        run = archive_runs(old_content)[0]
        assert json.loads((run / ARCHIVE_MANIFEST).read_text())["items"] == []

    def test_rollback_conflict_not_overwritten(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)
        installer.install(["core"])
        (old_content / "agents" / "old.md").write_text("recreated by user")

        installer.backup_mgr.restore_backup()

        restore = installer.backup_mgr.last_archive_restore
        run = archive_runs(old_content)[0]
        assert restore["restored"] == []
        assert restore["conflicts"] == [
            (old_content / "agents" / "old.md", run / "agents" / "old.md")
        ]
        assert (old_content / "agents" / "old.md").read_text() == "recreated by user"
        assert (run / "agents" / "old.md").read_text() == "old agent"
        # still recorded, so a later rollback can retry
        assert len(json.loads((run / ARCHIVE_MANIFEST).read_text())["items"]) == 1

    def test_rollback_missing_archived_item(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)
        result = installer.install(["core"])
        Path(result["retired"]["archived"][0][1]).rename(old_content / "elsewhere.md")

        installer.backup_mgr.restore_backup()

        assert len(installer.backup_mgr.last_archive_restore["missing"]) == 1

    def test_tampered_archive_manifest_ignored(self, tmp_path):
        run = tmp_path / "archived" / "run"
        run.mkdir(parents=True)
        (run / ARCHIVE_MANIFEST).write_text(
            json.dumps(
                {
                    "items": [
                        {"original": "../evil", "archived": "x"},
                        {"original": "/abs", "archived": "y"},
                    ]
                }
            )
        )
        restore = ArchiveManager(tmp_path).restore(run)
        assert len(restore["failed"]) == 2
        assert restore["restored"] == []

    @pytest.mark.parametrize(
        "archive", ["../outside", "/abs/archived/x", "backups/x", "archived/a/b", 5]
    )
    def test_backup_archive_reference_validated(self, tmp_path, archive):
        mgr = BackupManager(tmp_path)
        assert mgr.get_archive_dir({"archive": archive}) is None

    def test_list_runs(self, mock_config_dir, old_content):
        set_manifest(mock_config_dir, ["skills/old-skill", "agents/old.md"])
        installer = make_installer(mock_config_dir, old_content)
        installer.install(["core"])

        runs = installer.archive_mgr.list_runs()
        assert len(runs) == 1 and runs[0]["items"] == 2
