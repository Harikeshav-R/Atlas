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

import logging
import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from atlas.daemon.errors import IpcProtocolError, IpcUnavailableError
from atlas.daemon.progress import ProgressUpdate
from atlas.daemon.service import daemon_status
from atlas.db import session_scope
from atlas.scrape.fetcher import default_fetcher

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from atlas.ai.base import LLMProvider
    from atlas.config.schema import Config
    from atlas.config.secrets import SecretStore
    from atlas.daemon.progress import ProgressCallback
    from atlas.scrape.fetcher import Fetcher

__all__ = [
    "Connect",
    "Connection",
    "Dispatch",
    "ErrorEvent",
    "IpcEvent",
    "IpcRequest",
    "IpcServer",
    "ProgressEvent",
    "ResultEvent",
    "StatusEvent",
    "decode_event",
    "decode_request",
    "default_connect",
    "default_ipc_server",
    "encode_event",
    "encode_request",
    "handle_connection",
    "handle_request",
    "ipc_request",
    "stream_events",
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


# --- transport ----------------------------------------------------------------
#
# The socket layer, split so the framing is pure and tested and only the real
# bind/accept/connect I/O carries ``# pragma: no cover`` (AGENTS.md §6.2). A
# ``Connection`` is a binary duplex stream (a socket's ``makefile("rwb")`` in
# production, a paired-``BytesIO`` fake in tests); ``handle_connection`` (server
# side) and ``stream_events`` (client side) drive one exchange over it without
# knowing it is a socket.


@runtime_checkable
class Connection(Protocol):
    """A binary, newline-framed duplex stream (a socket file, or a test fake)."""

    def readline(self) -> bytes:
        """Read one newline-terminated line; ``b""`` at end of stream."""

    def write(self, data: bytes) -> int:
        """Write ``data`` to the stream, returning the number of bytes written."""

    def flush(self) -> None:
        """Flush any buffered writes to the peer."""

    def close(self) -> None:
        """Close the stream."""


#: The bound request handler the server invokes per connection (see
#: :func:`handle_request`, partially applied with the daemon's deps).
Dispatch = Callable[["IpcRequest", Callable[["IpcEvent"], None]], None]

#: Opens a :class:`Connection` to the daemon's socket (raises
#: :class:`~atlas.daemon.errors.IpcUnavailableError` when it cannot).
Connect = Callable[[Path], Connection]


def _write_event(conn: Connection, event: IpcEvent) -> None:
    """Frame one event onto ``conn`` and flush it so the client sees it promptly."""
    conn.write(encode_event(event))
    conn.flush()


def handle_connection(conn: Connection, dispatch: Dispatch) -> None:
    """Serve one client exchange over ``conn`` (the server side; pure framing).

    Reads the single request line, decodes it, and runs ``dispatch`` with an
    ``emit`` that frames each event back onto ``conn``. A malformed request line
    is answered with an :class:`ErrorEvent` rather than raising, so one bad client
    never disturbs the accept loop.
    """
    line = conn.readline()
    try:
        request = decode_request(line)
    except IpcProtocolError:
        _write_event(conn, ErrorEvent(message="Malformed IPC request."))
        return
    dispatch(request, lambda event: _write_event(conn, event))


def stream_events(
    conn: Connection,
    request: IpcRequest,
    on_event: Callable[[IpcEvent], None],
) -> None:
    """Send ``request`` over ``conn`` and stream decoded events to ``on_event``.

    The client side (pure framing): writes the request line, then reads event
    lines until the server closes the stream, decoding each and pushing it to
    ``on_event``.
    """
    conn.write(encode_request(request))
    conn.flush()
    while True:
        line = conn.readline()
        if not line:
            break
        on_event(decode_event(line))


def ipc_request(
    socket_path: Path,
    request: IpcRequest,
    *,
    on_event: Callable[[IpcEvent], None],
    connect: Connect | None = None,
) -> None:
    """Connect to the daemon, send ``request``, and stream its events.

    Args:
        socket_path: The daemon's IPC socket (:func:`atlas.config.paths.socket_file`).
        request: The request to send.
        on_event: Called with each decoded event as it arrives.
        connect: The transport that opens the connection (injectable for tests);
            defaults to :func:`default_connect`.

    Raises:
        IpcUnavailableError: If the daemon is not running / its socket is unreachable.
        IpcProtocolError: If the daemon sends an undecodable event.
    """
    connect = connect or default_connect
    conn = connect(socket_path)
    try:
        stream_events(conn, request, on_event)
    finally:
        conn.close()


@runtime_checkable
class IpcServer(Protocol):
    """The daemon's IPC listener (injectable seam; a fake is used in tests)."""

    def serve(self, socket_path: Path, dispatch: Dispatch) -> None:
        """Bind ``socket_path`` and start accepting connections in the background."""

    def stop(self) -> None:
        """Stop accepting, close the socket, and remove the socket file."""


def _bind_listener(socket_path: Path) -> socket.socket:  # pragma: no cover - real socket bind
    """Bind and return the platform-appropriate listening socket.

    On POSIX a Unix-domain socket bound to ``socket_path``; on Windows a loopback
    TCP socket whose chosen port is written to ``socket_path`` as a sidecar (named
    pipes need ``pywin32``; loopback TCP is stdlib-only). All real socket I/O, so
    ``# pragma: no cover`` (AGENTS.md §6.2) — the framing above is tested instead.
    """
    if sys.platform == "win32":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        _, port = listener.getsockname()
        socket_path.write_text(str(port), encoding="utf-8")
    else:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
        listener.bind(str(socket_path))
    listener.listen()
    return listener


def default_connect(socket_path: Path) -> Connection:  # pragma: no cover - real socket connect
    """Open a :class:`Connection` to the daemon, dispatching on ``sys.platform``.

    POSIX connects to the Unix-domain socket; Windows reads the port sidecar and
    connects to loopback. A refused/absent socket becomes an
    :class:`~atlas.daemon.errors.IpcUnavailableError`. Real socket I/O, so
    ``# pragma: no cover`` — :func:`ipc_request` is tested with a fake ``connect``.
    """
    try:
        if sys.platform == "win32":
            port = int(socket_path.read_text(encoding="utf-8"))
            sock = socket.create_connection(("127.0.0.1", port))
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined, unused-ignore]
            sock.connect(str(socket_path))
    except (OSError, ValueError) as exc:
        raise IpcUnavailableError from exc
    return sock.makefile("rwb")


class _DefaultIpcServer:
    """The real :class:`IpcServer`, accepting connections on a background thread."""

    def __init__(self) -> None:  # pragma: no cover - trivial state init for the real server
        """Start with no bound socket or accept thread."""
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._socket_path: Path | None = None
        self._stopping = False

    def serve(
        self, socket_path: Path, dispatch: Dispatch
    ) -> None:  # pragma: no cover - real socket serve
        """Bind the socket and spawn the (daemon) accept-loop thread; non-blocking."""
        self._socket_path = socket_path
        self._listener = _bind_listener(socket_path)
        self._thread = threading.Thread(
            target=self._accept_loop, args=(dispatch,), daemon=True, name="atlas-ipc"
        )
        self._thread.start()

    def _accept_loop(self, dispatch: Dispatch) -> None:  # pragma: no cover - real accept loop
        """Accept and serve connections until :meth:`stop` closes the listener."""
        assert self._listener is not None
        while not self._stopping:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                break  # listener closed by stop()
            try:
                with conn.makefile("rwb") as stream:
                    handle_connection(stream, dispatch)
            except OSError:
                _LOGGER.debug("IPC connection errored; dropping it.", exc_info=True)
            finally:
                conn.close()

    def stop(self) -> None:  # pragma: no cover - real socket teardown
        """Stop accepting, close the listener, join the thread, unlink the socket."""
        self._stopping = True
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._socket_path is not None and sys.platform != "win32":
            self._socket_path.unlink(missing_ok=True)


def default_ipc_server() -> IpcServer:  # pragma: no cover - constructs the real server
    """Return a fresh real :class:`IpcServer` (owns its own thread + socket state).

    A factory (not a singleton) mirroring :func:`atlas.daemon.scheduler.default_scheduler`,
    carrying ``# pragma: no cover`` because the hermetic suite never binds a real
    socket (AGENTS.md §6.2); tests inject a fake :class:`IpcServer`.
    """
    return _DefaultIpcServer()
