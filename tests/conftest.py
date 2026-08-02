"""Shared pytest fixtures and fakes for the Atlas test suite.

The :class:`FakeLLMProvider` here is the canonical test double for the AI layer:
it implements :class:`atlas.ai.base.LLMProvider` by replaying scripted responses,
so tests can exercise the structured-output recovery ladder and future backends
without spawning a real coding CLI or hitting a network (AGENTS.md §6.2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import pytest

from atlas.ai.base import LLMRequest, LLMResponse
from atlas.ai.cli.runner import RunResult

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
