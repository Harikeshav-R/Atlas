"""On-disk storage of rendered PDFs (PROJECT.md §5.11, §6).

Rendered PDFs are written as files under the data dir and referenced by path —
never stored as DB blobs (§6) — mirroring the raw-HTML snapshot store in
:mod:`atlas.scrape.snapshot`. The renders directory is an injectable argument
defaulting to ``<data_dir>/renders`` (composed like :func:`atlas.db.engine.db_path`),
so tests write into a ``tmp_path`` and never touch the real data dir (AGENTS.md
§6.2).
"""

from __future__ import annotations

from pathlib import Path

from atlas.config.paths import data_dir

__all__ = ["default_renders_dir", "write_pdf"]

#: Subdirectory of the data dir that holds rendered PDFs.
_RENDERS_SUBDIR = "renders"


def default_renders_dir() -> Path:
    """Return the default renders directory under the data dir."""
    return data_dir() / _RENDERS_SUBDIR


def write_pdf(pdf_bytes: bytes, *, filename: str, renders_dir: Path | None = None) -> str:
    """Write ``pdf_bytes`` to ``<renders_dir>/<filename>`` and return the path.

    Creates the directory if needed (the path helpers are pure and never create
    directories). The returned string is stored as the referencing row's PDF path.

    Args:
        pdf_bytes: The rendered PDF document bytes.
        filename: The file name to write (stem chosen by the caller so a re-render
            of the same artifact overwrites its own file).
        renders_dir: The directory to write into; defaults to
            :func:`default_renders_dir` (a ``tmp_path`` is injected in tests).

    Returns:
        The absolute path to the written PDF file, as a string.
    """
    directory = renders_dir if renders_dir is not None else default_renders_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(pdf_bytes)
    return str(path)
