"""Master-resume ingest, parsing, and versioning (PROJECT.md §5.3).

Atlas keeps exactly one master resume per user, shared across all profiles and
**versioned**: each ingest or reparse that changes content creates a new,
immutable version. This package turns a Markdown source into a structured
:class:`~atlas.resume.structure.ParsedResume` of content-ID'd blocks
(:mod:`atlas.resume.parser`, :mod:`atlas.resume.structure`), persists versions
via pure repository functions over an open session
(:mod:`atlas.resume.repository`), and orchestrates the "new version only on
content change" and reparse rules (:mod:`atlas.resume.service`). The parsed
blocks are the traceability anchor the later fit-scoring (§5.6), tailoring
(§5.7), and honesty-validation (§11) steps build on.

The parser is deterministic today; an AI-assisted structure-extraction fallback
(the ``parse_master_resume`` task, PROJECT.md §7) plugs into the
:class:`~atlas.resume.parser.StructureExtractor` seam in a later step without
reworking the deterministic path.
"""

from __future__ import annotations

from atlas.resume.errors import (
    MasterResumeNotFoundError,
    ResumeError,
    ResumeSourceError,
)
from atlas.resume.parser import StructureExtractor, normalize_markdown, parse_markdown
from atlas.resume.structure import (
    BlockType,
    ParsedBlock,
    ParsedResume,
    content_id_for,
    normalize_text,
)

__all__ = [
    "BlockType",
    "MasterResumeNotFoundError",
    "ParsedBlock",
    "ParsedResume",
    "ResumeError",
    "ResumeSourceError",
    "StructureExtractor",
    "content_id_for",
    "normalize_markdown",
    "normalize_text",
    "parse_markdown",
]
