"""Archive for retired paths: move, never delete.

Retired paths (manifest ``"retired"``) are moved out of the way instead of
being deleted:

    ~/.claude/archived/<YYYY-MM-DD-HHMMSS>/<original relative path>

``archived/`` is not a directory Claude Code loads skills, agents, commands
or rules from, so archived copies don't show up as duplicates.

Safety rules (deliberately strict; anything unusual is refused):

* A retired path must be strictly inside ``skills/``, ``agents/`` or
  ``commands/`` (fixed allowlist, compared after Unicode NFC normalisation and
  case folding).
* No existing component between ``~/.claude`` and the leaf may be a symlink
  (the allowlisted directory itself included). Only the leaf may be a symlink;
  it is moved as a link.
* ``~/.claude/archived`` and the run directory must be real directories, not
  symlinks.
* ``archive-manifest.json`` is never read or written through a symlink and is
  replaced atomically (temp file + ``os.replace``).
* Each run journals an item as ``pending`` before moving it and ``done``
  afterwards, so an interrupted run can still be rolled back.

Rollback finds the run through the backup taken by the same install (its
``backup-manifest.json`` has ``"archive": "archived/<run>"``) and moves items
back only where the original path is free; conflicts are reported.

Residual risk: moves use ``os.rename`` after checking the destination is free.
Another process creating the destination between the check and the rename
could be overwritten (files) - acceptable for a single-user home directory.
"""

import json
import os
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Optional

ARCHIVE_DIR_NAME = "archived"
ARCHIVE_MANIFEST = "archive-manifest.json"

# Fixed allowlist: retired entries must be strictly inside one of these.
RETIRABLE_ROOTS = ("skills", "agents", "commands")


class UnsafePathError(ValueError):
    """Raised when a path fails the archive safety rules."""


def fold(text: str) -> str:
    """Normalise for comparison: NFC + casefold (macOS is NFD/case-insensitive)."""
    return unicodedata.normalize("NFC", text).casefold()


def fold_parts(path: Path) -> tuple[str, ...]:
    return tuple(fold(part) for part in path.parts)


def within(path: Path, base: Path) -> bool:
    """True if path equals base or lies inside it (normalised, case-insensitive)."""
    p, b = fold_parts(path), fold_parts(base)
    return p[: len(b)] == b


def parse_relative(entry: Any) -> tuple[str, ...]:
    """Split a manifest path into safe relative parts or raise UnsafePathError."""
    if not isinstance(entry, str):
        raise UnsafePathError("entry is not a string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in entry):
        raise UnsafePathError("control characters are not allowed")
    if "\\" in entry:
        raise UnsafePathError("backslashes are not allowed; use '/'")
    text = entry.strip()
    if not text:
        raise UnsafePathError("refers to the Claude directory itself")
    if (
        PurePosixPath(text).is_absolute()
        or PureWindowsPath(text).drive
        or text.startswith("~")
    ):
        raise UnsafePathError("absolute paths are not allowed")
    parts = tuple(part for part in text.split("/") if part not in ("", "."))
    if ".." in parts:
        raise UnsafePathError("'..' is not allowed")
    if any(part != part.strip() for part in parts):
        raise UnsafePathError("path parts may not start or end with whitespace")
    if not parts:
        raise UnsafePathError("refers to the Claude directory itself")
    return parts


def check_retirable(claude_dir: Path, entry: Any) -> Path:
    """Validate a retired entry against the allowlist and symlink rules.

    Returns the (unresolved) path under claude_dir; raises UnsafePathError.
    """
    parts = parse_relative(entry)
    # Exact (NFC, case-sensitive) match on the root: "SKILLS" or "ſkills" must not
    # widen the allowlist on case-sensitive filesystems. Overlap checks elsewhere
    # still use fold(), which only ever refuses more.
    if unicodedata.normalize("NFC", parts[0]) not in RETIRABLE_ROOTS or len(parts) < 2:
        raise UnsafePathError(
            "only paths inside "
            + ", ".join(r + "/" for r in RETIRABLE_ROOTS)
            + " can be retired"
        )

    # No existing component above the leaf may be a symlink (root included).
    for i in range(1, len(parts)):
        component = claude_dir.joinpath(*parts[:i])
        if os.path.islink(component):
            raise UnsafePathError(f"'{'/'.join(parts[:i])}' is a symlink")
        if not os.path.lexists(component):
            break

    real_claude = claude_dir.resolve()
    allowed_root = claude_dir / parts[0]
    real_root = (
        allowed_root.resolve()
        if os.path.lexists(allowed_root)
        else real_claude / parts[0]
    )
    real_parent = claude_dir.joinpath(*parts[:-1]).resolve()
    if not within(real_root, real_claude) or not within(real_parent, real_root):
        raise UnsafePathError("resolves outside the Claude directory")

    return claude_dir.joinpath(*parts)


def check_no_symlink_components(base: Path, parts: tuple[str, ...]) -> Path:
    """base/parts with no symlinked component except possibly the leaf."""
    for i in range(1, len(parts)):
        component = base.joinpath(*parts[:i])
        if os.path.islink(component):
            raise UnsafePathError(f"'{'/'.join(parts[:i])}' is a symlink")
    path = base.joinpath(*parts)
    if not within(path.parent.resolve(), base.resolve()):
        raise UnsafePathError("resolves outside its base directory")
    return path


def unique_path(path: Path) -> Path:
    """Return path, or path with a ``-N`` suffix if something already exists there."""
    if not os.path.lexists(path):
        return path
    n = 1
    while True:
        candidate = path.with_name(f"{path.name}-{n}")
        if not os.path.lexists(candidate):
            return candidate
        n += 1


def _rename_no_clobber(src: Path, dest: Path) -> None:
    """Rename src to dest, refusing if dest exists (see residual risk note)."""
    if os.path.lexists(dest):
        raise FileExistsError(f"destination already exists: {dest}")
    os.rename(src, dest)


class ArchiveManager:
    """Moves retired paths into ``~/.claude/archived`` and back."""

    def __init__(self, claude_dir: Path):
        self.claude_dir = claude_dir
        self.archive_root = claude_dir / ARCHIVE_DIR_NAME

    # ------------------------------------------------------------------
    # Archive root / run directory checks
    # ------------------------------------------------------------------

    def root_problem(self) -> Optional[str]:
        """Reason archiving is unsafe right now, or None."""
        if os.path.islink(self.archive_root):
            return f"{self.archive_root} is a symlink; refusing to archive into it"
        if os.path.lexists(self.archive_root) and not self.archive_root.is_dir():
            return f"{self.archive_root} exists and is not a directory"
        return None

    def validate_run_dir(self, run_dir: Path) -> Path:
        """run_dir must be a real, non-symlink direct child of the real archive root."""
        if self.root_problem() or not self.archive_root.is_dir():
            raise UnsafePathError(self.root_problem() or "no archive directory")
        if os.path.islink(run_dir) or not run_dir.is_dir():
            raise UnsafePathError(f"{run_dir} is not a real directory")
        if fold_parts(run_dir.resolve().parent) != fold_parts(
            self.archive_root.resolve()
        ):
            raise UnsafePathError(f"{run_dir} is not inside {self.archive_root}")
        return run_dir

    def next_run_dir(self, now: Optional[datetime] = None) -> Path:
        """Path for a new archive run (not created). Never an existing directory."""
        stamp = (now or datetime.now()).strftime("%Y-%m-%d-%H%M%S")
        return unique_path(self.archive_root / stamp)

    # ------------------------------------------------------------------
    # Manifest (journal)
    # ------------------------------------------------------------------

    def _write_manifest(self, run_dir: Path, items: list[dict]) -> None:
        """Atomically replace run_dir/archive-manifest.json (never through a symlink)."""
        target = run_dir / ARCHIVE_MANIFEST
        # Unique name per write: a write interrupted earlier may have left a stale temp file
        tmp = run_dir / f".{ARCHIVE_MANIFEST}.{uuid.uuid4().hex}.tmp"
        fd = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "w") as f:
            json.dump(
                {"updated_at": datetime.now().isoformat(), "items": items}, f, indent=2
            )
            f.write("\n")
        # os.replace swaps the directory entry; a symlink at target is replaced, not followed
        os.replace(tmp, target)

    def _read_manifest(self, run_dir: Path) -> list[Any]:
        """Return the raw items list. Raises UnsafePathError/ValueError when invalid."""
        path = run_dir / ARCHIVE_MANIFEST
        if os.path.islink(path):
            raise UnsafePathError(f"{ARCHIVE_MANIFEST} is a symlink; ignoring it")
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return []
        try:
            with os.fdopen(fd) as f:
                data = json.load(f)
        except RecursionError as e:
            raise ValueError(f"{ARCHIVE_MANIFEST} is nested too deeply") from e
        if not isinstance(data, dict) or not isinstance(data.get("items", []), list):
            raise ValueError(f"{ARCHIVE_MANIFEST} is not a valid archive manifest")
        return data.get("items", [])

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    def archive(self, paths: list[Path], run_dir: Path) -> dict[str, list]:
        """Move each (already validated) path to ``run_dir/<relative path>``.

        Nothing is copied or deleted. Each item is journaled as ``pending``
        before its move and ``done`` after; the journal is also written if the
        run is interrupted (e.g. Ctrl-C).

        Returns:
            {"moved": [(original, archived)], "failed": [(original, message)]}
        """
        moved: list[tuple[Path, Path]] = []
        failed: list[tuple[Path, str]] = []
        if not paths:
            return {"moved": moved, "failed": failed}

        problem = self.root_problem()
        if problem:
            return {"moved": moved, "failed": [(p, problem) for p in paths]}

        try:
            self.archive_root.mkdir(exist_ok=True)
            run_dir.mkdir()  # fresh directory; fails if something already exists there
            self.validate_run_dir(run_dir)
        except (OSError, ValueError) as e:
            return {
                "moved": moved,
                "failed": [(p, f"cannot create archive folder: {e}") for p in paths],
            }

        journal: list[dict] = []
        try:
            for path in paths:
                try:
                    rel = path.relative_to(self.claude_dir)
                    # Re-check right before moving: nothing above the leaf became a symlink
                    check_retirable(self.claude_dir, rel.as_posix())
                    dest = check_no_symlink_components(run_dir, rel.parts)
                    dest = unique_path(dest)
                    entry = {
                        "original": rel.as_posix(),
                        "archived": dest.relative_to(run_dir).as_posix(),
                        "state": "pending",
                    }
                    journal.append(entry)
                    self._write_manifest(run_dir, journal)

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    check_no_symlink_components(
                        run_dir, dest.relative_to(run_dir).parts
                    )
                    _rename_no_clobber(path, dest)
                    entry["state"] = "done"
                    moved.append((path, dest))
                except (OSError, ValueError) as e:
                    if (
                        journal
                        and journal[-1].get("original")
                        == path.relative_to(self.claude_dir).as_posix()
                    ):
                        journal[-1]["state"] = "failed"
                    failed.append((path, str(e)))
        finally:
            if journal:
                try:
                    self._write_manifest(run_dir, journal)
                except OSError as e:
                    # Moves already happened; report instead of a traceback
                    failed.append(
                        (
                            run_dir / ARCHIVE_MANIFEST,
                            f"could not write archive journal: {e}",
                        )
                    )

        return {"moved": moved, "failed": failed}

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore(self, run_dir: Path) -> dict[str, list]:
        """Move archived items back to their original paths, never overwriting.

        Every item is validated: the original must pass the same allowlist and
        symlink rules as archiving; the archived path must stay inside the run
        directory with no symlinked component except the leaf.

        Returns:
            {"restored": [Path], "conflicts": [(original, archived)],
             "missing": [archived], "failed": [(item, message)]}
        """
        result: dict[str, list] = {
            "restored": [],
            "conflicts": [],
            "missing": [],
            "failed": [],
        }

        try:
            self.validate_run_dir(run_dir)
            items = self._read_manifest(run_dir)
        except (OSError, ValueError) as e:
            result["failed"].append((str(run_dir), str(e)))
            return result

        remaining: list[Any] = []
        for item in items:
            try:
                if not isinstance(item, dict):
                    raise UnsafePathError("item is not an object")
                original_rel, archived_rel = item.get("original"), item.get("archived")
                if not isinstance(original_rel, str) or not isinstance(
                    archived_rel, str
                ):
                    raise UnsafePathError("'original' and 'archived' must be strings")
                original = check_retirable(self.claude_dir, original_rel)
                archived = check_no_symlink_components(
                    run_dir, parse_relative(archived_rel)
                )
            except (OSError, ValueError) as e:
                result["failed"].append(
                    (repr(item)[:200], f"invalid archive entry: {e}")
                )
                remaining.append(item)
                continue

            if not os.path.lexists(archived):
                # e.g. journaled as pending but never moved (interrupted run)
                result["missing"].append(archived)
                continue
            if os.path.lexists(original):
                result["conflicts"].append((original, archived))
                remaining.append(item)
                continue

            try:
                original.parent.mkdir(parents=True, exist_ok=True)
                # Parents created above must still be real directories
                check_retirable(self.claude_dir, original_rel)
                _rename_no_clobber(archived, original)
                result["restored"].append(original)
            except (OSError, ValueError) as e:
                result["failed"].append((str(original), str(e)))
                remaining.append(item)

        try:
            self._write_manifest(run_dir, remaining)
        except OSError as e:
            result["failed"].append((ARCHIVE_MANIFEST, f"could not update: {e}"))

        return result

    def list_runs(self) -> list[dict]:
        """Previous archive runs, newest first: [{"path": Path, "items": int}]."""
        if self.root_problem() or not self.archive_root.is_dir():
            return []
        runs = []
        for run_dir in sorted(self.archive_root.iterdir(), reverse=True):
            if run_dir.is_dir() and not run_dir.is_symlink():
                try:
                    count = len(self._read_manifest(run_dir))
                except (OSError, ValueError):
                    count = 0
                runs.append({"path": run_dir, "items": count})
        return runs
