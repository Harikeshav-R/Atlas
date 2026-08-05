"""Tests for the Workday adapter in :mod:`atlas.discovery.ats.workday`.

Detection is pure over URL strings; listing (a paginated POST) is exercised
offline through a scripted :class:`FakeFetcher` — the ``results`` sequence replays
one page per offset — so no real HTTP happens (AGENTS.md §6.2).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from atlas.discovery.ats.workday import WorkdayAdapter
from atlas.discovery.errors import DiscoveryError
from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import FetchResult
from tests.conftest import FakeFetcher

_TIMEOUT = 30


def _page(jobs: list[Any], total: int) -> FetchResult:
    return FetchResult(
        url="https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/careers/jobs",
        status_code=200,
        content_type="application/json",
        body=json.dumps({"total": total, "jobPostings": jobs}),
    )


def _job(path: str, title: str = "Engineer") -> dict[str, object]:
    return {
        "title": title,
        "externalPath": path,
        "locationsText": "Santa Clara, CA",
        "postedOn": "Posted 3 Days Ago",
    }


@pytest.mark.parametrize(
    ("url", "token"),
    [
        # Board URLs.
        ("https://nvidia.wd5.myworkdayjobs.com/careers", "nvidia:wd5:careers"),
        ("https://nvidia.wd5.myworkdayjobs.com/en-US/careers", "nvidia:wd5:careers"),
        ("https://nvidia.wd5.myworkdayjobs.com/en-US/careers/", "nvidia:wd5:careers"),
        # Raw CxS API URL.
        (
            "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/careers/jobs",
            "nvidia:wd5:careers",
        ),
    ],
)
def test_detect_recognizes_urls(url: str, token: str) -> None:
    assert WorkdayAdapter().detect(url) == token


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.lever.co/acme",  # a different ATS
        "https://example.com/careers",  # not workday
        "https://nvidia.careers.myworkdayjobs.com/careers",  # 2nd label isn't wd\d+
        "https://nvidia.wd5.myworkdayjobs.com/en-US",  # only a locale, no site
        "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia",  # no site after tenant
    ],
)
def test_detect_rejects_unrecognized_urls(url: str) -> None:
    assert WorkdayAdapter().detect(url) is None


def test_list_postings_posts_and_normalizes() -> None:
    jobs = [
        _job("/job/Santa-Clara/Senior-Engineer_JR100"),
        _job("/job/Remote/Staff-Engineer_JR200"),
    ]
    fetcher = FakeFetcher(results=[_page(jobs, total=2)])
    postings = WorkdayAdapter().list_postings(
        "nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert [p.external_id for p in postings] == ["JR100", "JR200"]
    first = postings[0]
    assert first.posting.title == "Engineer"
    assert first.posting.apply_url == (
        "https://nvidia.wd5.myworkdayjobs.com/job/Santa-Clara/Senior-Engineer_JR100"
    )
    assert first.posting.location == "Santa Clara, CA"
    assert first.posting.posted_at == "Posted 3 Days Ago"
    # The request is a POST with the CxS body + Accept header.
    call = fetcher.calls[0]
    assert call.method == "POST"
    assert call.headers == {"Accept": "application/json"}
    assert call.json_body == {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    assert call.url == "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/careers/jobs"


def test_list_postings_external_id_without_underscore() -> None:
    # An externalPath with no "_JR" suffix falls back to the whole trailing segment.
    fetcher = FakeFetcher(results=[_page([_job("/job/plain-path")], total=1)])
    postings = WorkdayAdapter().list_postings(
        "nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert postings[0].external_id == "/job/plain-path"


def test_list_postings_paginates() -> None:
    page1 = _page([_job(f"/job/a_JR{i}") for i in range(20)], total=25)
    page2 = _page([_job(f"/job/b_JR{i}") for i in range(20, 25)], total=25)
    fetcher = FakeFetcher(results=[page1, page2])
    postings = WorkdayAdapter().list_postings(
        "nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert len(postings) == 25
    # Two pages fetched, at offsets 0 and 20.
    assert [call.json_body["offset"] for call in fetcher.calls] == [0, 20]  # type: ignore[index]


def test_list_postings_stops_on_empty_page() -> None:
    # total claims more than a page, but the second page comes back empty → stop.
    page1 = _page([_job(f"/job/a_JR{i}") for i in range(20)], total=99)
    page2 = _page([], total=99)
    fetcher = FakeFetcher(results=[page1, page2])
    postings = WorkdayAdapter().list_postings(
        "nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert len(postings) == 20
    assert len(fetcher.calls) == 2


def test_list_postings_caps_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    # total far exceeds the cap; every page is full → capped at _MAX_PAGES with a warning.
    full_page = _page([_job(f"/job/a_JR{i}") for i in range(20)], total=1000)
    fetcher = FakeFetcher(results=[full_page] * 10)
    with caplog.at_level(logging.WARNING, logger="atlas.discovery.ats.workday"):
        postings = WorkdayAdapter().list_postings(
            "nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT
        )
    assert len(postings) == 200  # _MAX_PAGES * _LIMIT
    assert len(fetcher.calls) == 10
    assert any("capped at 200 of 1000" in record.message for record in caplog.records)


def test_list_postings_skips_malformed_jobs() -> None:
    # A single-page board (total=1) whose page also carries malformed entries: the
    # missing-title, non-dict, and missing-externalPath jobs are all skipped.
    jobs: list[Any] = [
        _job("/job/ok_JR1"),
        {"title": "no path"},
        "not-a-dict",
        {"locationsText": "x"},
    ]
    fetcher = FakeFetcher(results=[_page(jobs, total=1)])
    postings = WorkdayAdapter().list_postings(
        "nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT
    )
    assert [p.external_id for p in postings] == ["JR1"]


def test_list_postings_malformed_board_ref_raises() -> None:
    fetcher = FakeFetcher(results=[_page([], total=0)])
    with pytest.raises(DiscoveryError, match="Malformed Workday board reference"):
        WorkdayAdapter().list_postings("bad-ref", fetcher=fetcher, timeout_s=_TIMEOUT)


def test_list_postings_non_json_raises() -> None:
    body = FetchResult(url="u", status_code=200, content_type=None, body="<html>")
    fetcher = FakeFetcher(results=[body])
    with pytest.raises(DiscoveryError, match="non-JSON"):
        WorkdayAdapter().list_postings("nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT)


@pytest.mark.parametrize(
    "body",
    ['{"jobPostings": []}', '{"total": 5}', '{"total": "x", "jobPostings": []}', "[]"],
)
def test_list_postings_unexpected_shape_raises(body: str) -> None:
    fetcher = FakeFetcher(
        results=[FetchResult(url="u", status_code=200, content_type=None, body=body)]
    )
    with pytest.raises(DiscoveryError, match="unexpected response"):
        WorkdayAdapter().list_postings("nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT)


def test_list_postings_propagates_fetch_error() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError):
        WorkdayAdapter().list_postings("nvidia:wd5:careers", fetcher=fetcher, timeout_s=_TIMEOUT)
