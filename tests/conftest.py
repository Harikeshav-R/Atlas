"""Shared pytest fixtures and fakes for the Atlas test suite.

The :class:`FakeLLMProvider` here is the canonical test double for the AI layer:
it implements :class:`atlas.ai.base.LLMProvider` by replaying scripted responses,
so tests can exercise the structured-output recovery ladder and future backends
without spawning a real coding CLI or hitting a network (AGENTS.md §6.2).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest
from sqlmodel import SQLModel

from atlas.ai.base import LLMRequest, LLMResponse
from atlas.ai.cli.runner import RunResult
from atlas.db.engine import create_db_engine

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

# A per-call scripted response: either a ready :class:`LLMResponse` or a callable
# that builds one from the request it receives (to assert on prompt/schema).
ScriptedResponse = LLMResponse | Callable[[LLMRequest], LLMResponse]


class FakeLLMProvider:
    """A scripted, offline :class:`~atlas.ai.base.LLMProvider` for tests.

    Each call to :meth:`complete` returns the next entry from ``script`` (a
    ready response or a callable applied to the request). Requests are recorded
    on :attr:`calls` so tests can assert what the provider was asked, including
    the temperature escalation and prompt-only fallback driven by
    :func:`atlas.ai.complete_json.complete_json`.
    """

    def __init__(
        self,
        script: list[ScriptedResponse],
        *,
        name: str = "fake",
        available: bool = True,
    ) -> None:
        """Store the scripted responses and provider metadata."""
        self._script = list(script)
        self._index = 0
        self.name = name
        self._available = available
        self.calls: list[LLMRequest] = []

    def is_available(self) -> bool:
        """Return the configured availability flag."""
        return self._available

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the next scripted response, recording the request.

        Raises:
            AssertionError: If called more times than the script provides — a
                signal that the code under test made an unexpected extra call.
        """
        self.calls.append(request)
        assert self._index < len(self._script), "FakeLLMProvider script exhausted"
        entry = self._script[self._index]
        self._index += 1
        if callable(entry):
            return entry(request)
        return entry

    def stream(self, request: LLMRequest) -> Iterator[str]:
        """Yield the completed response text as a single chunk."""
        yield self.complete(request).text


def make_response(
    *,
    text: str = "",
    structured: dict[str, object] | None = None,
    model: str = "fake-model",
    backend: str = "fake",
) -> LLMResponse:
    """Build an :class:`~atlas.ai.base.LLMResponse` with test-friendly defaults."""
    return LLMResponse(
        text=text,
        structured=structured,
        model=model,
        backend=backend,
    )


class FakeProviderFactory(Protocol):
    """Callable protocol for the ``make_fake_provider`` fixture."""

    def __call__(
        self,
        script: list[ScriptedResponse],
        *,
        name: str = ...,
        available: bool = ...,
    ) -> FakeLLMProvider:
        """Build a :class:`FakeLLMProvider` from a scripted response list."""
        ...


@pytest.fixture
def make_fake_provider() -> FakeProviderFactory:
    """Return a factory that builds :class:`FakeLLMProvider` instances."""

    def factory(
        script: list[ScriptedResponse],
        *,
        name: str = "fake",
        available: bool = True,
    ) -> FakeLLMProvider:
        return FakeLLMProvider(script, name=name, available=available)

    return factory


@dataclass
class RunnerCall:
    """A single recorded invocation of :class:`FakeSubprocessRunner`."""

    argv: list[str]
    cwd: str | None
    input_text: str | None
    timeout_s: int
    env: dict[str, str] | None


class FakeSubprocessRunner:
    """A scripted, offline :class:`~atlas.ai.cli.runner.SubprocessRunner` for tests.

    Returns ``result`` for every call, or raises ``raises`` (e.g. a
    :class:`subprocess.TimeoutExpired` or :class:`FileNotFoundError`) instead.
    Every invocation is recorded on :attr:`calls` so tests can assert on the
    argv, scratch cwd, piped stdin, timeout, and environment the adapter passed.
    """

    def __init__(
        self,
        result: RunResult | None = None,
        *,
        raises: BaseException | None = None,
    ) -> None:
        """Store the scripted result or exception to replay."""
        self._result = result
        self._raises = raises
        self.calls: list[RunnerCall] = []

    def __call__(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None,
        input_text: str | None,
        timeout_s: int,
        env: Mapping[str, str] | None,
    ) -> RunResult:
        """Record the call and return the scripted result, or raise."""
        self.calls.append(
            RunnerCall(
                argv=list(argv),
                cwd=cwd,
                input_text=input_text,
                timeout_s=timeout_s,
                env=dict(env) if env is not None else None,
            )
        )
        if self._raises is not None:
            raise self._raises
        assert self._result is not None, "FakeSubprocessRunner needs a result or a raises"
        return self._result


class FakeRunnerFactory(Protocol):
    """Callable protocol for the ``make_fake_runner`` fixture."""

    def __call__(
        self,
        result: RunResult | None = ...,
        *,
        raises: BaseException | None = ...,
    ) -> FakeSubprocessRunner:
        """Build a :class:`FakeSubprocessRunner` from a scripted result or error."""
        ...


@pytest.fixture
def make_fake_runner() -> FakeRunnerFactory:
    """Return a factory that builds :class:`FakeSubprocessRunner` instances."""

    def factory(
        result: RunResult | None = None,
        *,
        raises: BaseException | None = None,
    ) -> FakeSubprocessRunner:
        return FakeSubprocessRunner(result, raises=raises)

    return factory


@dataclass
class FakeMessage:
    """The ``choices[i].message`` shape the API provider reads via ``getattr``."""

    content: str | None


@dataclass
class FakeChoice:
    """One entry of a fake LiteLLM ``ModelResponse.choices`` list."""

    message: FakeMessage


@dataclass
class FakeUsage:
    """The ``usage`` shape the API provider reads via ``getattr``."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class FakeModelResponse:
    """A minimal stand-in for LiteLLM's ``ModelResponse``.

    The :class:`~atlas.ai.api.provider.LiteLLMProvider` reads responses through
    defensive ``getattr``/``dict`` access (never importing LiteLLM's types), so a
    plain object exposing ``choices``, ``usage``, ``model``, ``_hidden_params``,
    and ``model_dump`` is a faithful, offline double (AGENTS.md §6.2).
    """

    def __init__(
        self,
        *,
        content: str | None = "the answer",
        model: str | None = "openrouter/anthropic/claude-sonnet",
        usage: FakeUsage | None = None,
        response_cost: float | None = None,
        choices: list[FakeChoice] | None = None,
        dumpable: bool = True,
    ) -> None:
        """Build a fake response; ``choices`` defaults to one message of ``content``."""
        self.choices = choices if choices is not None else [FakeChoice(FakeMessage(content))]
        self.usage = usage
        self.model = model
        self._hidden_params = {"response_cost": response_cost}
        if not dumpable:
            # Drop ``model_dump`` so the provider's raw-dict fallback is exercised.
            self.model_dump = None  # type: ignore[assignment]

    def model_dump(self) -> dict[str, object]:
        """Return a debug dict, mirroring ``ModelResponse.model_dump()``."""
        return {"model": self.model, "content": self.choices[0].message.content}


@dataclass
class CompleterCall:
    """A single recorded invocation of :class:`FakeChatCompleter`."""

    model: str
    messages: list[dict[str, str]]
    api_key: str | None
    api_base: str | None
    timeout_s: int
    temperature: float | None
    max_tokens: int | None
    response_format: dict[str, object] | None
    num_retries: int


class FakeChatCompleter:
    """A scripted, offline :class:`~atlas.ai.api.client.CompletionFn` for tests.

    Returns ``result`` for every call, or raises ``raises`` (e.g. a fake
    LiteLLM error) instead. Every invocation is recorded on :attr:`calls` so
    tests can assert on the model id, messages, injected key, adaptive timeout,
    ``response_format``, and transport-retry count the provider passed — without
    importing or invoking ``litellm``.
    """

    def __init__(
        self,
        result: object = None,
        *,
        raises: BaseException | None = None,
    ) -> None:
        """Store the scripted result or exception to replay."""
        self._result = result
        self._raises = raises
        self.calls: list[CompleterCall] = []

    def __call__(
        self,
        *,
        model: str,
        messages: Sequence[dict[str, str]],
        api_key: str | None,
        api_base: str | None,
        timeout_s: int,
        temperature: float | None,
        max_tokens: int | None,
        response_format: dict[str, object] | None,
        num_retries: int,
    ) -> object:
        """Record the call and return the scripted result, or raise."""
        self.calls.append(
            CompleterCall(
                model=model,
                messages=[dict(m) for m in messages],
                api_key=api_key,
                api_base=api_base,
                timeout_s=timeout_s,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                num_retries=num_retries,
            )
        )
        if self._raises is not None:
            raise self._raises
        return self._result


class FakeLiteLLMError(Exception):
    """A stand-in for a LiteLLM/OpenAI error carrying an HTTP ``status_code``.

    The provider classifies failures by ``status_code`` (and message) via
    ``getattr``, so this reproduces that surface without importing ``litellm``.
    ``status_code=None`` models the status-less transport errors (e.g. timeouts).
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        """Store the message and optional HTTP status code."""
        super().__init__(message)
        self.status_code = status_code


class FakeKeyring:
    """An in-memory keyring backend for tests (no real keychain, no credentials).

    Implements the :class:`atlas.config.secrets.KeyringBackend` protocol against a
    plain dict keyed by ``(service, username)``. Its class name is not in Atlas's
    insecure-backend denylist, so it is treated as a secure backend.
    """

    def __init__(self) -> None:
        """Create an empty fake keyring."""
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        """Return the stored secret or ``None``."""
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store ``password`` under ``(service, username)``."""
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        """Delete the secret for ``(service, username)``."""
        del self._store[(service, username)]


def named_keyring(fqn: str) -> FakeKeyring:
    """Return a :class:`FakeKeyring` whose type reports the fully-qualified ``fqn``.

    Backend selection reads ``type(backend).__module__`` and ``__qualname__``, so
    this builds a distinct subclass with those set — letting a test pose a fake
    as, e.g., ``keyrings.alt.file.PlaintextKeyring`` without shared-state hacks.
    """
    module, _, qualname = fqn.rpartition(".")
    named_type = type(qualname, (FakeKeyring,), {"__module__": module, "__qualname__": qualname})
    instance: FakeKeyring = named_type()
    return instance


@pytest.fixture
def fake_keyring() -> FakeKeyring:
    """Return a fresh in-memory :class:`FakeKeyring`."""
    return FakeKeyring()


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """Yield an in-memory SQLite engine with Atlas's schema created.

    Hermetic and offline (AGENTS.md §6.2): no real data dir is touched. The
    engine is disposed on teardown so no connection outlives the test — the same
    contract file-backed tests rely on for Windows-safe ``tmp_path`` cleanup.
    """
    engine = create_db_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def reset_atlas_logging() -> Iterator[None]:
    """Snapshot and restore the ``"atlas"`` logger so tests don't leak handlers.

    ``setup_logging`` mutates global logging state; this autouse fixture saves the
    logger's handlers/level/propagate before each test and restores them after,
    closing any handler the test installed. Closing file handlers also releases
    the log file so Windows ``tmp_path`` cleanup never fails on an open lock (the
    same teardown contract the db-engine fixture follows).
    """
    atlas_logger = logging.getLogger("atlas")
    saved_handlers = list(atlas_logger.handlers)
    saved_level = atlas_logger.level
    saved_propagate = atlas_logger.propagate
    try:
        yield
    finally:
        for handler in list(atlas_logger.handlers):
            if handler not in saved_handlers:
                atlas_logger.removeHandler(handler)
                handler.close()
        atlas_logger.handlers = saved_handlers
        atlas_logger.setLevel(saved_level)
        atlas_logger.propagate = saved_propagate


@dataclass
class HandlerFactoryCall:
    """A single recorded invocation of :class:`FakeHandlerFactory`."""

    console_level: int
    log_path: Path
    max_bytes: int
    backup_count: int


class FakeHandlerFactory:
    """A scripted, offline ``HandlerFactory`` for logging tests.

    Returns handlers that touch nothing external — a bare
    :class:`logging.NullHandler` for the console and, unless ``with_file`` is
    ``False``, a :class:`logging.FileHandler` opened on the injected ``log_path``
    (a ``tmp_path`` in tests, never the real state dir). Records each call on
    :attr:`calls` so tests assert on the console level, log path, and rotation
    settings the setup passed.
    """

    def __init__(self, *, with_file: bool = True) -> None:
        """Store whether to include a file handler in the built list."""
        self._with_file = with_file
        self.calls: list[HandlerFactoryCall] = []

    def __call__(
        self, *, console_level: int, log_path: Path, max_bytes: int, backup_count: int
    ) -> Sequence[logging.Handler]:
        """Record the call and return offline handlers for it."""
        self.calls.append(
            HandlerFactoryCall(
                console_level=console_level,
                log_path=log_path,
                max_bytes=max_bytes,
                backup_count=backup_count,
            )
        )
        console = logging.NullHandler()
        console.setLevel(console_level)
        handlers: list[logging.Handler] = [console]
        if self._with_file:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            handlers.append(file_handler)
        return handlers
