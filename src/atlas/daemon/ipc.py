"""The daemon's local IPC surface (PROJECT.md §4.1).

A running daemon exposes a small local socket so the TUI/CLI can trigger on-demand
work (a "poll now") and read the daemon's status, streaming progress back as it
runs. Following the house pattern for OS/transport boundaries
(:mod:`atlas.platform.opener`'s ``sys.platform`` dispatch, the
:class:`~atlas.daemon.service.ProcessControl` seam), this module is split so that
**the wire protocol, the codec, and the request handler are pure and fully
tested**, and only the socket bind/accept/connect I/O (:mod:`atlas.daemon.ipc`'s
transport, added alongside) carries ``# pragma: no cover`` (AGENTS.md §6.2).

Wire protocol: one JSON object per newline-delimited line, matching the Claude
adapter's NDJSON idiom. A client sends exactly one :class:`IpcRequest` line, then
the server streams zero or more :class:`IpcEvent` lines (progress updates followed
by a terminal :class:`ResultEvent` or :class:`ErrorEvent`) and closes.

The request handler (:func:`handle_request`) is transport-free: it pushes events
through an injected ``emit`` callback, so the poll's per-source progress streams
out immediately and the whole flow is testable with an ``emit`` that appends to a
list. The ``"poll"`` action reuses the daemon's own claim ``owner`` token, so an
on-demand poll and the scheduled tick never double-score a pair (the ``score_claim``
lease, PROJECT.md §4.1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from atlas.daemon.errors import IpcProtocolError
from atlas.daemon.progress import ProgressUpdate
from atlas.daemon.service import daemon_status
from atlas.db import session_scope
from atlas.scrape.fetcher import default_fetcher

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy.engine import Engine

    from atlas.ai.base import LLMProvider
    from atlas.config.schema import Config
    from atlas.config.secrets import SecretStore
    from atlas.daemon.progress import ProgressCallback
    from atlas.scrape.fetcher import Fetcher

__all__ = [
    "ErrorEvent",
    "IpcEvent",
    "IpcRequest",
    "ProgressEvent",
    "ResultEvent",
    "StatusEvent",
    "decode_event",
    "decode_request",
    "encode_event",
    "encode_request",
    "handle_request",
]


class IpcRequest(BaseModel):
    """A single action the TUI/CLI asks the running daemon to perform.

    Attributes:
        action: ``"status"`` reports whether the daemon is running; ``"poll"`` runs
            one discovery + aggregator + scoring pass now, streaming progress.
    """

    action: Literal["status", "poll"]


class StatusEvent(BaseModel):
    """The daemon's run-state, in reply to a ``"status"`` request."""

    event: Literal["status"] = "status"
    running: bool
    pid: int | None


class ProgressEvent(BaseModel):
    """One progress step streamed while a ``"poll"`` runs.

    Mirrors :class:`~atlas.daemon.progress.ProgressUpdate`, tagged with the poll
    ``phase`` it came from so the client can group updates.
    """

    event: Literal["progress"] = "progress"
    phase: Literal["discovery", "aggregator", "scoring"]
    stage: Literal["start", "item", "done"]
    label: str = ""
    done: int = 0
    total: int | None = None


class ResultEvent(BaseModel):
    """The terminal summary of a successful ``"poll"``.

    Aggregates the three polls' outcomes. ``skipped`` sums the discovery/aggregator
    dedup-skips and the scoring backlog skips (a poll-summary rollup); the other
    counts map one-to-one onto their polls.
    """

    event: Literal["result"] = "result"
    discovered: int
    scored: int
    skipped: int
    failed_sources: int
    inactive: int
    claimed: int


class ErrorEvent(BaseModel):
    """A terminal error reply (secret-free message)."""

    event: Literal["error"] = "error"
    message: str


#: The discriminated union of everything the server can stream back.
IpcEvent = Annotated[
    StatusEvent | ProgressEvent | ResultEvent | ErrorEvent,
    Field(discriminator="event"),
]

_EVENT_ADAPTER: TypeAdapter[StatusEvent | ProgressEvent | ResultEvent | ErrorEvent] = TypeAdapter(
    IpcEvent
)


def encode_request(request: IpcRequest) -> bytes:
    """Serialize a request to one newline-terminated JSON line."""
    return request.model_dump_json().encode("utf-8") + b"\n"


def decode_request(line: bytes) -> IpcRequest:
    """Parse one request line, raising :class:`IpcProtocolError` on bad input.

    A malformed, empty, non-UTF-8, or unknown-action line is rejected with a
    secret-free error rather than crashing the caller.
    """
    try:
        return IpcRequest.model_validate_json(line)
    except (ValidationError, UnicodeDecodeError) as exc:
        raise IpcProtocolError("Malformed IPC request.") from exc


def encode_event(event: StatusEvent | ProgressEvent | ResultEvent | ErrorEvent) -> bytes:
    """Serialize an event to one newline-terminated JSON line."""
    return _EVENT_ADAPTER.dump_json(event) + b"\n"


def decode_event(line: bytes) -> StatusEvent | ProgressEvent | ResultEvent | ErrorEvent:
    """Parse one event line, raising :class:`IpcProtocolError` on bad input."""
    try:
        return _EVENT_ADAPTER.validate_json(line)
    except (ValidationError, UnicodeDecodeError) as exc:
        raise IpcProtocolError("Malformed IPC event.") from exc


def _phase_emitter(
    emit: Callable[[IpcEvent], None],
    *,
    phase: Literal["discovery", "aggregator", "scoring"],
) -> ProgressCallback:
    """Adapt a poll's :class:`ProgressUpdate`s into ``phase``-tagged progress events."""

    def on_progress(update: ProgressUpdate) -> None:
        emit(
            ProgressEvent(
                phase=phase,
                stage=update.stage,
                label=update.label,
                done=update.done,
                total=update.total,
            )
        )

    return on_progress


def _run_poll(
    *,
    engine: Engine,
    config: Config,
    store: SecretStore,
    provider: LLMProvider,
    owner: str,
    fetcher: Fetcher,
    emit: Callable[[IpcEvent], None],
) -> ResultEvent:
    """Run one discovery + aggregator + scoring pass, streaming per-phase progress.

    Each poll runs in its own short transaction (so its new rows are committed
    before the next reads them), reusing the daemon's ``owner`` claim token. Lazy
    imports of the poll functions keep :mod:`atlas.daemon.ipc` free of an import
    cycle with :mod:`atlas.discovery`.
    """
    from atlas.daemon.poll import run_scoring_poll
    from atlas.discovery.poller import run_aggregator_poll, run_discovery_poll

    with session_scope(engine) as session:
        ats = run_discovery_poll(
            session, fetcher=fetcher, on_progress=_phase_emitter(emit, phase="discovery")
        )
    with session_scope(engine) as session:
        agg = run_aggregator_poll(
            session,
            config=config.aggregators,
            store=store,
            fetcher=fetcher,
            on_progress=_phase_emitter(emit, phase="aggregator"),
        )
    with session_scope(engine) as session:
        scoring = run_scoring_poll(
            session,
            provider=provider,
            owner=owner,
            on_progress=_phase_emitter(emit, phase="scoring"),
        )
    return ResultEvent(
        discovered=ats.discovered + agg.discovered,
        scored=scoring.scored,
        skipped=ats.skipped + agg.skipped + scoring.skipped,
        failed_sources=ats.failed_sources + agg.failed_sources,
        inactive=agg.inactive,
        claimed=scoring.claimed,
    )


def handle_request(
    request: IpcRequest,
    *,
    engine: Engine,
    config: Config,
    store: SecretStore,
    provider: LLMProvider,
    owner: str,
    pid_path: Path,
    emit: Callable[[IpcEvent], None],
    fetcher: Fetcher = default_fetcher,
) -> None:
    """Dispatch one IPC request, pushing every reply/progress event through ``emit``.

    Transport-free (the tested core): a ``"status"`` request emits a single
    :class:`StatusEvent`; a ``"poll"`` request runs the three-poll pass, streaming
    :class:`ProgressEvent`s and a terminal :class:`ResultEvent`. Any failure during
    the poll becomes a terminal :class:`ErrorEvent` (secret-free) rather than
    propagating into the transport, so one bad request never tears down the server.

    Args:
        request: The decoded request to service.
        engine: The daemon's database engine (each poll opens its own session).
        config: The loaded config (its ``aggregators`` section drives the aggregator poll).
        store: The secret store key-gated aggregators resolve credentials from.
        provider: The AI backend (or failover chain) the scoring poll scores with.
        owner: The daemon's claim token (its pid, as a string), reused so an
            on-demand poll never double-scores against the scheduled tick.
        pid_path: The daemon's PID file, read for the ``"status"`` reply.
        emit: The sink every event is pushed to (the transport writes it to the wire).
        fetcher: The HTTP boundary the discovery adapters fetch through (injectable).
    """
    if request.action == "status":
        status = daemon_status(pid_path)
        emit(StatusEvent(running=status.running, pid=status.pid))
        return
    try:
        result = _run_poll(
            engine=engine,
            config=config,
            store=store,
            provider=provider,
            owner=owner,
            fetcher=fetcher,
            emit=emit,
        )
    except Exception:
        # Any poll failure becomes a secret-free error reply rather than
        # propagating into the transport and tearing down the accept loop.
        emit(ErrorEvent(message="The poll failed; see the daemon log for details."))
        return
    emit(result)
