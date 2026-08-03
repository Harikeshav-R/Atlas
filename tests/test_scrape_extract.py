"""Tests for the deterministic extractors in :mod:`atlas.scrape.extract`."""

from __future__ import annotations

from atlas.scrape.extract import (
    extract_jsonld,
    extract_main_text,
    extract_opengraph,
    extract_posting,
)

_JSONLD = """
<html><head>
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Backend Engineer",
 "hiringOrganization": {"name": "Acme"}, "employmentType": "FULL_TIME",
 "description": "Build things.", "datePosted": "2026-08-01"}
</script>
</head><body><p>ignored</p></body></html>
"""

_JSONLD_LIST_AND_STRING_ORG = """
<html><head>
<script type="application/ld+json">
[{"@type": "WebSite", "name": "Careers"},
 {"@type": ["JobPosting"], "title": "ML Engineer", "hiringOrganization": "Globex"}]
</script>
</head><body></body></html>
"""

_OPENGRAPH = """
<html><head>
<meta property="og:title" content="Data Engineer">
<meta property="og:description" content="Pipelines galore.">
</head><body></body></html>
"""

_PLAIN = """
<html><head><title>t</title></head>
<body><nav>menu</nav><script>var x=1;</script>
<p>We are hiring a Platform Engineer.</p></body></html>
"""


def test_extract_jsonld_maps_fields() -> None:
    posting = extract_jsonld(_JSONLD)
    assert posting is not None
    assert posting.title == "Backend Engineer"
    assert posting.company == "Acme"
    assert posting.employment_type == "FULL_TIME"
    assert posting.description == "Build things."
    assert posting.posted_at == "2026-08-01"


def test_extract_jsonld_handles_list_and_string_org() -> None:
    # A list of objects, a list-valued @type, and a string hiringOrganization.
    posting = extract_jsonld(_JSONLD_LIST_AND_STRING_ORG)
    assert posting is not None
    assert posting.title == "ML Engineer"
    assert posting.company == "Globex"


def test_extract_jsonld_without_hiring_org_leaves_company_blank() -> None:
    # No hiringOrganization (neither dict nor string) → company stays empty.
    html = (
        '<script type="application/ld+json">{"@type": "JobPosting", "title": "Solo Role"}</script>'
    )
    posting = extract_jsonld(html)
    assert posting is not None
    assert posting.title == "Solo Role"
    assert posting.company == ""


def test_extract_jsonld_none_when_absent() -> None:
    assert extract_jsonld("<html><body>no ld</body></html>") is None


def test_extract_jsonld_tolerates_malformed_block() -> None:
    html = '<script type="application/ld+json">{not json}</script>'
    assert extract_jsonld(html) is None


def test_extract_jsonld_ignores_empty_script() -> None:
    html = '<script type="application/ld+json"></script>'
    assert extract_jsonld(html) is None


def test_extract_opengraph_maps_title_and_description() -> None:
    posting = extract_opengraph(_OPENGRAPH)
    assert posting is not None
    assert posting.title == "Data Engineer"
    assert posting.description == "Pipelines galore."


def test_extract_opengraph_none_without_title() -> None:
    assert extract_opengraph("<html><head></head></html>") is None


def test_extract_main_text_strips_noise() -> None:
    text = extract_main_text(_PLAIN)
    assert "Platform Engineer" in text
    assert "menu" not in text
    assert "var x" not in text


def test_extract_posting_short_circuits_on_jsonld() -> None:
    posting, main_text = extract_posting(_JSONLD)
    assert posting is not None
    assert posting.title == "Backend Engineer"
    assert main_text  # always returned


def test_extract_posting_backfills_description_from_text() -> None:
    # OpenGraph with a title but no description → description filled from page text.
    html = (
        '<html><head><meta property="og:title" content="Role"></head>'
        "<body><p>Body text.</p></body></html>"
    )
    posting, _ = extract_posting(html)
    assert posting is not None
    assert posting.title == "Role"
    assert "Body text." in posting.description


def test_extract_posting_none_when_no_structured_data() -> None:
    posting, main_text = extract_posting(_PLAIN)
    assert posting is None
    assert "Platform Engineer" in main_text
