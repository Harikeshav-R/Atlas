"""Typed structure of a parsed master resume, with stable content IDs.

A :class:`ParsedResume` is the parser's output (:mod:`atlas.resume.parser`): an
ordered list of :class:`ParsedBlock`s, each a single addressable unit of the
resume (a summary paragraph, one experience bullet, a skill group, …). Each block
carries a **stable** :attr:`~ParsedBlock.content_id` derived from its type and
normalized text, so an unchanged bullet keeps the same id across versions and
tailoring/honesty validation can trace an output claim back to real source
content (PROJECT.md §5.3, §11).

Like :mod:`atlas.profiles.preferences`, these are plain Pydantic models with no
I/O: closed domains are :class:`~enum.StrEnum`s, every field is defaulted, and
the base model ignores unknown keys so a structure serialized by a newer schema
still loads. They serialize into the ``master_resume.parsed`` JSON column and
expand into ``resume_block`` rows (:class:`atlas.db.models.ResumeBlock`).
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BlockType",
    "ParsedBlock",
    "ParsedResume",
    "content_id_for",
    "normalize_text",
]

#: Prefix on every derived content id, so ids are recognizable in logs/output.
_CONTENT_ID_PREFIX = "blk_"

#: Number of hex characters of the digest kept in a content id (48 bits of the
#: SHA-256, ample to avoid collisions across a single resume's blocks).
_CONTENT_ID_LENGTH = 12

#: Collapses any run of whitespace to a single space for normalization.
_WHITESPACE = re.compile(r"\s+")


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible structure).

    Mirrors :class:`atlas.profiles.preferences._Base`: as the parsed-structure
    schema grows, an object stored by an older version still loads (its
    now-unknown keys are dropped rather than rejected).
    """

    model_config = ConfigDict(extra="ignore")


class BlockType(StrEnum):
    """The kind of a parsed resume block (PROJECT.md §5.3)."""

    CONTACT = "contact"
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    PROJECT = "project"
    SKILL = "skill"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    PUBLICATION = "publication"
    LINK = "link"
    OTHER = "other"


def normalize_text(text: str) -> str:
    """Return ``text`` with surrounding and collapsed internal whitespace removed.

    Used to derive a content id that is stable across cosmetic whitespace
    differences (trailing spaces, re-wrapping), so a bullet that only changed in
    layout keeps its id.
    """
    return _WHITESPACE.sub(" ", text).strip()


def content_id_for(block_type: BlockType, text: str, *, occurrence: int = 0) -> str:
    """Return a stable content id for a block of ``block_type`` and ``text``.

    The id is a truncated SHA-256 of the block type and normalized text, so the
    same content yields the same id across parses and versions (regardless of its
    position in the resume). When a resume genuinely repeats identical content
    (e.g. the same bullet under two roles), pass the 0-based ``occurrence`` so
    each duplicate gets a distinct-but-stable id rather than colliding.

    Args:
        block_type: The block's kind (folded into the hash so identical text
            under different section types gets different ids).
        text: The block's text; normalized via :func:`normalize_text` first.
        occurrence: 0-based index of this block among identical earlier blocks in
            the same parse; ``0`` (the default) adds nothing to the hash input.

    Returns:
        A content id of the form ``"blk_<hex>"``.
    """
    payload = f"{block_type.value}\n{normalize_text(text)}"
    if occurrence:
        payload = f"{payload}\n#{occurrence}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{_CONTENT_ID_PREFIX}{digest[:_CONTENT_ID_LENGTH]}"


class ParsedBlock(_Base):
    """One addressable block of a parsed master resume.

    Attributes:
        type: The block's kind.
        content_id: A stable identifier for this block's content (see
            :func:`content_id_for`).
        position: The block's 0-based order within the resume.
        text: The block's text content.
        tags: Optional structured metadata (metrics, tech tags); empty when none
            was extracted (the deterministic parser leaves this empty for now).
    """

    type: BlockType
    content_id: str
    position: int
    text: str
    tags: dict[str, Any] = Field(default_factory=dict)


class ParsedResume(_Base):
    """The full parsed structure of one master-resume version.

    Attributes:
        blocks: The resume's blocks in document order.
    """

    blocks: list[ParsedBlock] = Field(default_factory=list)
