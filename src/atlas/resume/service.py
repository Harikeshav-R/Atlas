"""Master-resume ingest/reparse orchestration (PROJECT.md §5.3).

This is the domain layer between the CLI and the repository: it applies the two
versioning rules over an open :class:`~sqlmodel.Session`, with the parser, and
clock injected so the logic is pure and hermetic to test.

- :func:`apply_set` ingests new Markdown, creating a version **only when the
  content changed** (normalized) from the current latest; identical content is a
  no-op that reports the existing version.
- :func:`apply_reparse` re-runs the parser on the latest version's stored source
  and always creates a new version, so a parser improvement can be re-applied
  without the original file.

Both return a small, serializable outcome the CLI renders; neither opens its own
transaction (the caller wraps them in :func:`atlas.db.session.session_scope`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from atlas.resume.errors import MasterResumeNotFoundError
from atlas.resume.parser import normalize_markdown, parse_markdown
from atlas.resume.repository import create_version, get_latest_master_resume

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel import Session

    from atlas.resume.structure import ParsedResume

__all__ = ["Parser", "SetOutcome", "apply_reparse", "apply_set", "utcnow"]


class Parser(Protocol):
    """The Markdown-parsing seam the service depends on.

    :func:`atlas.resume.parser.parse_markdown` is the production implementation;
    tests inject a fake to assert the service parses exactly when it should.
    """

    def __call__(self, markdown: str) -> ParsedResume:
        """Parse ``markdown`` into a structured resume."""


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC :class:`~datetime.datetime`.

    The default clock injected into the service functions; tests pass a fixed
    clock instead so persisted timestamps are deterministic.
    """
    return datetime.now(tz=UTC)


class SetOutcome(BaseModel):
    """The result of :func:`apply_set` (and :func:`apply_reparse`).

    Attributes:
        version: The resulting master-resume version number.
        created: Whether a new version was created (``False`` only when
            :func:`apply_set` found the content unchanged).
        block_count: How many blocks the resulting version has.
    """

    version: int
    created: bool
    block_count: int


def apply_set(
    session: Session,
    *,
    raw_markdown: str,
    source_path: str | None,
    parse: Parser = parse_markdown,
    clock: Callable[[], datetime] = utcnow,
) -> SetOutcome:
    """Ingest ``raw_markdown``, creating a new version only if the content changed.

    Compares the normalized incoming Markdown to the latest version's normalized
    source. If they match, this is a no-op reporting the existing version;
    otherwise the source is parsed and persisted as the next version.

    Args:
        session: The open session/transaction to write within.
        raw_markdown: The Markdown source being ingested.
        source_path: The path it was read from, recorded on a new version.
        parse: The Markdown parser (injectable for tests).
        clock: The clock used for a new version's ``created_at`` (injectable).

    Returns:
        A :class:`SetOutcome` describing the resulting version.
    """
    latest = get_latest_master_resume(session)
    if latest is not None and normalize_markdown(latest.raw_markdown) == normalize_markdown(
        raw_markdown
    ):
        block_count = len(latest.parsed.get("blocks", []))
        return SetOutcome(version=latest.version, created=False, block_count=block_count)
    parsed = parse(raw_markdown)
    resume = create_version(
        session,
        raw_markdown=raw_markdown,
        source_path=source_path,
        parsed=parsed,
        created_at=clock(),
    )
    return SetOutcome(version=resume.version, created=True, block_count=len(parsed.blocks))


def apply_reparse(
    session: Session,
    *,
    parse: Parser = parse_markdown,
    clock: Callable[[], datetime] = utcnow,
) -> SetOutcome:
    """Re-parse the latest version's source into a new version.

    Loads the latest version, re-runs the parser on its stored ``raw_markdown``,
    and persists the result as the next version (carrying the prior source path).
    Always creates a new version, so an improved parser can be re-applied.

    Args:
        session: The open session/transaction to write within.
        parse: The Markdown parser (injectable for tests).
        clock: The clock used for the new version's ``created_at`` (injectable).

    Returns:
        A :class:`SetOutcome` for the newly created version.

    Raises:
        MasterResumeNotFoundError: If no master resume has been set yet.
    """
    latest = get_latest_master_resume(session)
    if latest is None:
        raise MasterResumeNotFoundError(
            "No master resume to reparse; run `atlas resume set <path>` first."
        )
    parsed = parse(latest.raw_markdown)
    resume = create_version(
        session,
        raw_markdown=latest.raw_markdown,
        source_path=latest.source_path,
        parsed=parsed,
        created_at=clock(),
    )
    return SetOutcome(version=resume.version, created=True, block_count=len(parsed.blocks))
