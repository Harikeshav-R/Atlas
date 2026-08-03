"""Typed structure of a scraped, normalized job posting (PROJECT.md §5.5).

A :class:`ScrapedPosting` is the shape the deterministic extractors
(:mod:`atlas.scrape.extract`) and the AI extraction pass
(:mod:`atlas.scrape.ai_extract`) both produce, and the shape that
:func:`complete_json` validates the model's JSON output against. It is a plain
Pydantic model with no I/O — like :mod:`atlas.resume.structure` and
:mod:`atlas.profiles.preferences`: every field is defaulted (so a partial
extraction is still valid), and the base ignores unknown keys so a richer future
schema still loads.

The service (:mod:`atlas.scrape.service`) maps a :class:`ScrapedPosting` onto the
persisted :class:`atlas.db.models.JobPosting` columns.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Requirements", "ScrapedPosting"]


class _Base(BaseModel):
    """Base model that ignores unknown keys (forward-compatible extraction).

    Mirrors :class:`atlas.resume.structure._Base`: as the extracted-posting schema
    grows, an object produced by an older/newer extractor still loads (its
    now-unknown keys are dropped rather than rejected) — important because the AI
    pass may return extra fields.
    """

    model_config = ConfigDict(extra="ignore")


class Requirements(_Base):
    """A posting's requirements, split into must-have and nice-to-have.

    Attributes:
        must: Requirements the posting states as required.
        nice: Requirements the posting marks as preferred / nice-to-have.
    """

    must: list[str] = Field(default_factory=list)
    nice: list[str] = Field(default_factory=list)


class ScrapedPosting(_Base):
    """The normalized fields extracted from a job posting (PROJECT.md §5.5).

    Attributes:
        title: The role title.
        company: The hiring company's name.
        location: The posting's location(s), as free text.
        remote_type: ``"onsite"`` / ``"hybrid"`` / ``"remote"``, if determinable.
        employment_type: Full-time / contract / internship, if determinable.
        seniority: The role's seniority, if determinable.
        salary: Salary details (e.g. ``min`` / ``max`` / ``currency``); empty when
            not stated.
        description: The full role-description text.
        responsibilities: Listed responsibilities, if any.
        requirements: Must-have and nice-to-have requirements.
        keywords: Tech stack / keywords named in the posting.
        team: The team/org, if stated.
        posted_at: The posting date as free text/ISO, if stated (the service
            parses it into a timestamp where possible).
        apply_url: The URL to apply at.
    """

    title: str = ""
    company: str = ""
    location: str | None = None
    remote_type: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    salary: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    requirements: Requirements = Field(default_factory=Requirements)
    keywords: list[str] = Field(default_factory=list)
    team: str | None = None
    posted_at: str | None = None
    apply_url: str = ""
