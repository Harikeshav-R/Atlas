"""Shared pytest fixtures and fakes for the Atlas test suite.

The :class:`FakeLLMProvider` here is the canonical test double for the AI layer:
it implements :class:`atlas.ai.base.LLMProvider` by replaying scripted responses,
so tests can exercise the structured-output recovery ladder and future backends
without spawning a real coding CLI or hitting a network (AGENTS.md §6.2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

import pytest

from atlas.ai.base import LLMRequest, LLMResponse

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
