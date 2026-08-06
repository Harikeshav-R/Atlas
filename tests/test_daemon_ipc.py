"""Tests for the daemon's IPC protocol + pure handler in :mod:`atlas.daemon.ipc`.

Exercises the wire codec and :func:`handle_request` hermetically — an ``emit`` that
appends to a list, the in-memory ``db_engine``, a scripted ``FakeLLMProvider`` /
``FakeFetcher`` / ``FakeKeyring`` — with no real socket, thread, or process
(AGENTS.md §6.2). The transport (real socket I/O) is tested separately.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from atlas.config.schema import Config
from atlas.config.secrets import SecretStore
from atlas.daemon.errors import IpcError, IpcProtocolError, IpcUnavailableError
from atlas.daemon.ipc import (
    ErrorEvent,
    IpcEvent,
    IpcRequest,
    ProgressEvent,
    ResultEvent,
    StatusEvent,
    decode_event,
    decode_request,
    encode_event,
    encode_request,
    handle_request,
)
from atlas.daemon.service import write_pid
from atlas.db import session_scope
from atlas.profiles.preferences import ProfilePreferences
from atlas.profiles.repository import create_profile
from atlas.resume.repository import create_version
from atlas.resume.structure import BlockType, ParsedBlock, ParsedResume
from atlas.scrape.repository import (
    create_job_posting,
    get_or_create_company,
    get_or_create_url_source,
)
from tests.conftest import FakeKeyring, FakeLLMProvider, make_response

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Engine

_FETCHED = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def _store() -> SecretStore:
    return SecretStore(FakeKeyring())


def _assessment() -> dict[str, object]:
    return {
        "score": 80,
        "verdict": "strong",
        "rationale": "Great fit.",
        "matched_strengths": ["Python"],
        "gaps": [],
        "dealbreaker_hits": [],
        "salary_fit": "within",
    }


def _seed_scoreable(engine: Engine) -> None:
    """Seed an active profile, a master resume, and one unscored posting."""
    with session_scope(engine) as session:
        create_profile(session, name="Backend", preferences=ProfilePreferences(), active=True)
        create_version(
            session,
            raw_markdown="# Sam",
            source_path=None,
            parsed=ParsedResume(
                blocks=[
                    ParsedBlock(
                        type=BlockType.SUMMARY, content_id="blk_1", position=0, text="Engineer"
                    )
                ]
            ),
            created_at=_FETCHED,
        )
        company = get_or_create_company(session, name="Acme")
        source = get_or_create_url_source(session)
        assert company.id is not None
        assert source.id is not None
        create_job_posting(
            session,
            source_id=source.id,
            company_id=company.id,
            title="Backend Engineer",
            apply_url="https://jobs.acme.test/1",
            dedupe_hash="h1",
            fetched_at=_FETCHED,
            description="Build things.",
            keywords=["python"],
        )


# --- errors -------------------------------------------------------------------


def test_ipc_unavailable_error_message() -> None:
    exc = IpcUnavailableError()
    assert isinstance(exc, IpcError)
    assert "not running" in str(exc)


# --- codec --------------------------------------------------------------------


@pytest.mark.parametrize("action", ["status", "poll"])
def test_request_round_trip(action: str) -> None:
    request = IpcRequest(action=action)  # type: ignore[arg-type]
    assert decode_request(encode_request(request)) == request


@pytest.mark.parametrize(
    "event",
    [
        StatusEvent(running=True, pid=42),
        StatusEvent(running=False, pid=None),
        ProgressEvent(phase="discovery", stage="start", total=2),
        ProgressEvent(phase="scoring", stage="item", label="BE x posting 1", done=1, total=None),
        ResultEvent(discovered=3, scored=2, skipped=1, failed_sources=0, inactive=1, claimed=0),
        ErrorEvent(message="boom"),
    ],
)
def test_event_round_trip(event: IpcEvent) -> None:
    assert decode_event(encode_event(event)) == event


@pytest.mark.parametrize("bad", [b"{", b"not json\n", b'{"action": "explode"}', b"\xff\xfe"])
def test_decode_request_rejects_bad_input(bad: bytes) -> None:
    with pytest.raises(IpcProtocolError):
        decode_request(bad)


@pytest.mark.parametrize("bad", [b"{", b'{"event": "nope"}', b"\xff\xfe"])
def test_decode_event_rejects_bad_input(bad: bytes) -> None:
    with pytest.raises(IpcProtocolError):
        decode_event(bad)


# --- handle_request: status ---------------------------------------------------


def test_handle_status_running(db_engine: Engine, tmp_path: Path) -> None:
    pid_path = tmp_path / "daemon.pid"
    write_pid(pid_path, os.getpid())  # this process is alive → running
    events: list[IpcEvent] = []
    handle_request(
        IpcRequest(action="status"),
        engine=db_engine,
        config=Config(),
        store=_store(),
        provider=FakeLLMProvider([]),
        owner="pid-1",
        pid_path=pid_path,
        emit=events.append,
    )
    assert len(events) == 1
    status = events[0]
    assert isinstance(status, StatusEvent)
    assert status.running is True


def test_handle_status_stopped_when_no_pidfile(db_engine: Engine, tmp_path: Path) -> None:
    events: list[IpcEvent] = []
    handle_request(
        IpcRequest(action="status"),
        engine=db_engine,
        config=Config(),
        store=_store(),
        provider=FakeLLMProvider([]),
        owner="pid-1",
        pid_path=tmp_path / "absent.pid",
        emit=events.append,
    )
    assert events == [StatusEvent(running=False, pid=None)]


# --- handle_request: poll -----------------------------------------------------


def test_handle_poll_streams_progress_then_result(db_engine: Engine, tmp_path: Path) -> None:
    _seed_scoreable(db_engine)
    events: list[IpcEvent] = []
    handle_request(
        IpcRequest(action="poll"),
        engine=db_engine,
        config=Config(),
        store=_store(),
        provider=FakeLLMProvider([make_response(structured=_assessment())]),
        owner="pid-1",
        pid_path=tmp_path / "daemon.pid",
        emit=events.append,
    )
    # Each phase brackets with start/done; the scoring phase scores the one pair.
    phases = {e.phase for e in events if isinstance(e, ProgressEvent)}
    assert phases == {"discovery", "aggregator", "scoring"}
    assert isinstance(events[-1], ResultEvent)
    assert events[-1].scored == 1


def test_handle_poll_empty_still_emits_result(db_engine: Engine, tmp_path: Path) -> None:
    # No sources, no backlog: every phase brackets and a zero ResultEvent lands.
    events: list[IpcEvent] = []
    handle_request(
        IpcRequest(action="poll"),
        engine=db_engine,
        config=Config(),
        store=_store(),
        provider=FakeLLMProvider([]),
        owner="pid-1",
        pid_path=tmp_path / "daemon.pid",
        emit=events.append,
    )
    result = events[-1]
    assert isinstance(result, ResultEvent)
    assert result.discovered == 0
    assert result.scored == 0


def test_handle_poll_failure_emits_error_event(
    db_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A poll that raises internally becomes a terminal ErrorEvent, not a crash.
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("db exploded")

    # _run_poll lazy-imports the poll from its source module, so patch it there.
    monkeypatch.setattr("atlas.discovery.poller.run_discovery_poll", boom)
    events: list[IpcEvent] = []
    handle_request(
        IpcRequest(action="poll"),
        engine=db_engine,
        config=Config(),
        store=_store(),
        provider=FakeLLMProvider([]),
        owner="pid-1",
        pid_path=tmp_path / "daemon.pid",
        emit=events.append,
    )
    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
