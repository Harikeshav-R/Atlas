"""Persistence for the versioned master resume (PROJECT.md §5.3, §6).

Like :mod:`atlas.profiles.repository`, these are thin, pure functions over an
**open** :class:`~sqlmodel.Session`: the caller opens the transaction with
:func:`atlas.db.session.session_scope`, calls one or more of these, and the scope
commits (or rolls back) on exit. Nothing here opens its own session or engine.

Two invariants Atlas relies on are enforced here in code (not by database
constraints, per the :class:`~atlas.db.models.MasterResume` docstring):

- **One master resume, monotonic versions** — Atlas keeps a single logical master
  resume; :func:`create_version` numbers each new row one above the current
  latest (starting at 1), so versions form one increasing sequence.
- **Immutable versions** — :func:`create_version` only ever inserts a new
  :class:`~atlas.db.models.MasterResume` and its
  :class:`~atlas.db.models.ResumeBlock` rows; it never mutates an earlier
  version's rows, so a tailored resume that points at a version keeps its
  traceability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import col, desc, select

from atlas.db.models import MasterResume, ResumeBlock
from atlas.resume.errors import MasterResumeNotFoundError

if TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel import Session

    from atlas.resume.structure import ParsedResume

__all__ = [
    "create_version",
    "get_blocks",
    "get_latest_master_resume",
    "get_master_resume",
    "list_versions",
]


def get_latest_master_resume(session: Session) -> MasterResume | None:
    """Return the highest-numbered master-resume version, or ``None`` if none."""
    return session.exec(select(MasterResume).order_by(desc(col(MasterResume.version)))).first()


def get_master_resume(session: Session, version: int) -> MasterResume:
    """Return the master resume with ``version``.

    Raises:
        MasterResumeNotFoundError: If no version with that number exists.
    """
    resume = session.exec(select(MasterResume).where(MasterResume.version == version)).first()
    if resume is None:
        raise MasterResumeNotFoundError(f"No master resume version {version}.")
    return resume


def list_versions(session: Session) -> list[MasterResume]:
    """Return every master-resume version ordered by version number (ascending)."""
    return list(session.exec(select(MasterResume).order_by(col(MasterResume.version))).all())


def get_blocks(session: Session, master_resume_id: int) -> list[ResumeBlock]:
    """Return one version's blocks ordered by their position in the resume."""
    return list(
        session.exec(
            select(ResumeBlock)
            .where(ResumeBlock.master_resume_id == master_resume_id)
            .order_by(col(ResumeBlock.position))
        ).all()
    )


def create_version(
    session: Session,
    *,
    raw_markdown: str,
    source_path: str | None,
    parsed: ParsedResume,
    created_at: datetime,
) -> MasterResume:
    """Insert a new master-resume version and its blocks.

    The version number is one above the current latest (or ``1`` for the first).
    The parsed structure is stored both as the ``parsed`` JSON snapshot and
    expanded into :class:`~atlas.db.models.ResumeBlock` rows, from the single
    ``parsed`` source so the two never drift. Earlier versions are never touched.

    Args:
        session: The open session/transaction to write within.
        raw_markdown: The verbatim Markdown source for this version.
        source_path: The path this version was read from, or ``None``.
        parsed: The parsed structure to persist.
        created_at: When this version was created (timezone-aware UTC).

    Returns:
        The created :class:`~atlas.db.models.MasterResume` (id assigned).
    """
    latest = get_latest_master_resume(session)
    version = latest.version + 1 if latest is not None else 1
    resume = MasterResume(
        version=version,
        source_path=source_path,
        raw_markdown=raw_markdown,
        parsed=parsed.model_dump(mode="json"),
        created_at=created_at,
    )
    session.add(resume)
    session.flush()
    assert resume.id is not None  # freshly flushed → id assigned
    for block in parsed.blocks:
        session.add(
            ResumeBlock(
                master_resume_id=resume.id,
                type=block.type.value,
                content_id=block.content_id,
                position=block.position,
                text=block.text,
                tags=dict(block.tags),
            )
        )
    session.flush()
    return resume
