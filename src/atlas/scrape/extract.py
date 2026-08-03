"""Deterministic job-posting extraction from HTML (PROJECT.md §5.5).

The extraction ladder prefers structured data before falling back to text:

1. **JSON-LD** — a schema.org ``JobPosting`` object in a
   ``<script type="application/ld+json">`` block maps almost one-to-one onto a
   :class:`~atlas.scrape.structure.ScrapedPosting`.
2. **OpenGraph** — ``og:title`` / ``og:description`` meta tags as a weaker fill.
3. **Main text** — the page's visible text, for the AI extraction pass
   (:mod:`atlas.scrape.ai_extract`) to parse when structured data is absent.

:func:`extract_posting` runs the ladder and returns
``(posting, main_text)``: ``posting`` is a usable structured posting (it has at
least a title) when steps 1-2 found one, else ``None`` — signalling the caller to
run the AI pass over ``main_text``. All functions here are pure over an HTML
string (no network), so they are covered without fetching anything.

HTML is parsed with ``BeautifulSoup`` over the stdlib ``html.parser`` (no ``lxml``)
to keep the dependency pure-Python and cross-platform.
"""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup, Tag

from atlas.scrape.structure import ScrapedPosting

__all__ = [
    "extract_jsonld",
    "extract_main_text",
    "extract_opengraph",
    "extract_posting",
]

#: The stdlib HTML parser (pure-Python, no lxml/html5lib dependency).
_PARSER = "html.parser"

#: Tags whose text is navigation/boilerplate, dropped before main-text extraction.
_NOISE_TAGS = ("script", "style", "nav", "header", "footer", "noscript")


def _soup(html: str) -> BeautifulSoup:
    """Parse ``html`` into a :class:`~bs4.BeautifulSoup` over the stdlib parser."""
    return BeautifulSoup(html, _PARSER)


def _jsonld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Return every JSON object found across the page's JSON-LD script blocks.

    Tolerant of malformed blocks (skipped) and of both a single object and a
    list of objects per block.
    """
    objects: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not isinstance(script, Tag) or script.string is None:
            continue
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        objects.extend(item for item in candidates if isinstance(item, dict))
    return objects


def _as_str(value: Any) -> str | None:
    """Return ``value`` as a stripped non-empty string, or ``None``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def extract_jsonld(html: str) -> ScrapedPosting | None:
    """Extract a schema.org ``JobPosting`` from JSON-LD, if present.

    Returns a :class:`ScrapedPosting` built from the first JSON-LD object whose
    ``@type`` is ``JobPosting`` (case-insensitive), or ``None`` if there is none.
    Only fields the object actually provides are populated.
    """
    for obj in _jsonld_objects(_soup(html)):
        raw_type = obj.get("@type", "")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if not any(isinstance(t, str) and t.lower() == "jobposting" for t in types):
            continue
        hiring = obj.get("hiringOrganization")
        company = ""
        if isinstance(hiring, dict):
            company = _as_str(hiring.get("name")) or ""
        elif (name := _as_str(hiring)) is not None:
            company = name
        return ScrapedPosting(
            title=_as_str(obj.get("title")) or "",
            company=company,
            employment_type=_as_str(obj.get("employmentType")),
            description=_as_str(obj.get("description")) or "",
            posted_at=_as_str(obj.get("datePosted")),
        )
    return None


def extract_opengraph(html: str) -> ScrapedPosting | None:
    """Extract a weak posting from OpenGraph meta tags, if a title is present.

    Returns a :class:`ScrapedPosting` from ``og:title`` (and ``og:description``
    when present), or ``None`` if there is no ``og:title``.
    """
    soup = _soup(html)
    title = _meta_content(soup, "og:title")
    if title is None:
        return None
    return ScrapedPosting(
        title=title,
        description=_meta_content(soup, "og:description") or "",
    )


def _meta_content(soup: BeautifulSoup, property_name: str) -> str | None:
    """Return the ``content`` of the ``<meta property=...>`` tag, or ``None``."""
    tag = soup.find("meta", attrs={"property": property_name})
    if isinstance(tag, Tag):
        return _as_str(tag.get("content"))
    return None


def extract_main_text(html: str) -> str:
    """Return the page's visible text with navigation/script noise removed."""
    soup = _soup(html)
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def extract_posting(html: str) -> tuple[ScrapedPosting | None, str]:
    """Run the deterministic extraction ladder over ``html``.

    Returns ``(posting, main_text)``: ``posting`` is a usable structured posting
    (JSON-LD, else OpenGraph, provided it has a title) or ``None`` when no
    structured data was found; ``main_text`` is always the page's visible text,
    for the AI pass to parse when ``posting`` is ``None``.
    """
    main_text = extract_main_text(html)
    posting = extract_jsonld(html) or extract_opengraph(html)
    if posting is not None and posting.title:
        # Structured data with a real title short-circuits the AI pass; back-fill
        # the description from the page text when the structured record omitted it.
        if not posting.description:
            posting = posting.model_copy(update={"description": main_text})
        return posting, main_text
    return None, main_text
