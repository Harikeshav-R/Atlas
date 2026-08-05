"""Tests for the fetch boundary in :mod:`atlas.scrape.fetcher`.

The real :func:`atlas.scrape.fetcher.default_fetcher` performs network I/O and is
``# pragma: no cover``; the scrape flow is exercised through the injected
:class:`~tests.conftest.FakeFetcher` instead (AGENTS.md §6.2).
"""

from __future__ import annotations

import pytest

from atlas.scrape.errors import FetchError
from atlas.scrape.fetcher import BrowserFetcher, Fetcher, FetchResult
from tests.conftest import FakeFetcher


def test_fetch_result_fields() -> None:
    result = FetchResult(
        url="https://x.test", status_code=200, content_type="text/html", body="<html>"
    )
    assert result.url == "https://x.test"
    assert result.status_code == 200
    assert result.content_type == "text/html"
    assert result.body == "<html>"


def test_fake_fetcher_records_call_and_returns_result() -> None:
    result = FetchResult(url="https://x.test", status_code=200, content_type="text/html", body="ok")
    fetcher = FakeFetcher(result)
    got = fetcher("https://x.test", timeout_s=30)
    assert got is result
    assert fetcher.calls[0].url == "https://x.test"
    assert fetcher.calls[0].timeout_s == 30


def test_fake_fetcher_can_raise() -> None:
    fetcher = FakeFetcher(raises=FetchError("boom"))
    with pytest.raises(FetchError, match="boom"):
        fetcher("https://x.test", timeout_s=30)


def test_fake_fetcher_satisfies_both_protocols() -> None:
    # The same double stands in for the static Fetcher and the BrowserFetcher seam.
    fetcher = FakeFetcher(FetchResult(url="u", status_code=200, content_type=None, body=""))
    assert isinstance(fetcher, Fetcher)
    assert isinstance(fetcher, BrowserFetcher)


def test_fake_fetcher_get_call_records_defaults() -> None:
    result = FetchResult(url="https://x.test", status_code=200, content_type=None, body="ok")
    fetcher = FakeFetcher(result)
    fetcher("https://x.test", timeout_s=30)
    call = fetcher.calls[0]
    assert call.method == "GET"
    assert call.json_body is None
    assert call.headers is None


def test_fake_fetcher_records_post_method_body_and_headers() -> None:
    result = FetchResult(url="https://x.test", status_code=200, content_type=None, body="{}")
    fetcher = FakeFetcher(result)
    body = {"limit": 20, "offset": 0}
    got = fetcher(
        "https://x.test",
        timeout_s=30,
        method="POST",
        json_body=body,
        headers={"Accept": "application/json"},
    )
    assert got is result
    call = fetcher.calls[0]
    assert call.method == "POST"
    assert call.json_body == body
    assert call.headers == {"Accept": "application/json"}


def test_fake_fetcher_replays_results_sequence_in_order() -> None:
    pages = [
        FetchResult(url="u", status_code=200, content_type=None, body="page1"),
        FetchResult(url="u", status_code=200, content_type=None, body="page2"),
    ]
    fetcher = FakeFetcher(results=pages)
    assert fetcher("u", timeout_s=30).body == "page1"
    assert fetcher("u", timeout_s=30).body == "page2"
    # Exhausting the sequence fails loudly rather than silently repeating.
    with pytest.raises(AssertionError, match="ran out of scripted results"):
        fetcher("u", timeout_s=30)
