"""On-disk storage of raw job-posting HTML snapshots (PROJECT.md §5.5, §6).

A posting's raw HTML is stored as a file under the data dir and referenced from
:attr:`atlas.db.models.JobPosting.raw_snapshot_ref` — never as a DB blob (§6) — so
a posting can be re-parsed without re-fetching. The snapshots directory is an
injectable argument defaulting to ``<data_dir>/snapshots`` (composed like
:func:`atlas.db.engine.db_path`), so tests write into a ``tmp_path`` and never
touch the real data dir (AGENTS.md §6.2).
"""

from __future__ import annotations

from pathlib import Path

from atlas.config.paths import data_dir

__all__ = ["default_snapshots_dir", "write_snapshot"]

#: Subdirectory of the data dir that holds raw HTML snapshots.
_SNAPSHOTS_SUBDIR = "snapshots"


def default_snapshots_dir() -> Path:
    """Return the default snapshots directory under the data dir."""
    return data_dir() / _SNAPSHOTS_SUBDIR


def write_snapshot(html: str, *, dedupe_hash: str, snapshots_dir: Path | None = None) -> str:
    """Write ``html`` to ``<snapshots_dir>/<dedupe_hash>.html`` and return the path.

    Creates the directory if needed (the path helpers are pure and never create
    directories). The returned string is stored as the posting's
    ``raw_snapshot_ref``.

    Args:
        html: The raw HTML to persist.
        dedupe_hash: The posting's dedupe hash, used as the file stem so a
            re-fetch of the same posting overwrites its own snapshot.
        snapshots_dir: The directory to write into; defaults to
            :func:`default_snapshots_dir` (a ``tmp_path`` is injected in tests).

    Returns:
        The absolute path to the written snapshot file, as a string.
    """
    directory = snapshots_dir if snapshots_dir is not None else default_snapshots_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{dedupe_hash}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)
