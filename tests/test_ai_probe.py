"""Tests for the live capability probe in :mod:`atlas.ai.probe`."""

from __future__ import annotations

import json

import pytest

from atlas.ai.base import (
    LLMAuthError,
    LLMBackendError,
    LLMError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from atlas.ai.probe import PROBE_SCHEMA, BackendCapabilities, ProbeResult, probe_backend
from tests.conftest import FakeLLMProvider, ScriptedResponse, make_response

# The sentinel the probe asks the backend to echo (mirrors probe._SENTINEL).
_SENTINEL = "atlas-probe-ok"


def _schema_response(**structured: object) -> ScriptedResponse:
    """A scripted entry returning native structured output echoing the sentinel."""

    def _build(request: LLMRequest) -> LLMResponse:
        payload: dict[str, object] = {"ok": True, "echo": _SENTINEL}
        payload.update(structured)
        return make_response(structured=payload, backend="fake")

    return _build


def test_all_capabilities_supported() -> None:
    # Primary complete → structured w/ sentinel; stream → yields; override → ok.
    primary = FakeLLMProvider(
        [_schema_response(), make_response(text="chunk")],  # complete, then stream
        name="claude_code",
    )
    override = FakeLLMProvider([make_response(structured={"ok": True})], name="claude_code")

    result = probe_backend(primary, override_provider=override)

    assert result.ok is True
    assert result.backend == "claude_code"
    caps = result.capabilities
    assert caps.json_output is True
    assert caps.json_schema is True
    assert caps.system_prompt is True
    assert caps.streaming is True
    assert caps.model_override is True


def test_primary_call_threads_schema_and_system_prompt() -> None:
    primary = FakeLLMProvider([_schema_response(), make_response(text="c")], name="fake")
    probe_backend(primary)
    first = primary.calls[0]
    assert first.response_schema == PROBE_SCHEMA
    assert first.system is not None and _SENTINEL in first.system


def test_json_output_without_schema_via_text() -> None:
    # No native structured field, but the text parses as a JSON object → json_output
    # true, json_schema false.
    text = json.dumps({"ok": True, "echo": _SENTINEL})
    primary = FakeLLMProvider(
        [make_response(text=text), make_response(text="chunk")],
        name="fake",
    )
    result = probe_backend(primary)
    assert result.capabilities.json_output is True
    assert result.capabilities.json_schema is False
    # Sentinel echoed in the text counts as honoring the system prompt.
    assert result.capabilities.system_prompt is True


def test_no_json_at_all() -> None:
    primary = FakeLLMProvider(
        [make_response(text="plain prose, no json"), make_response(text="chunk")],
        name="fake",
    )
    result = probe_backend(primary)
    assert result.ok is True
    assert result.capabilities.json_output is False
    assert result.capabilities.json_schema is False
    assert result.capabilities.system_prompt is False


def test_model_override_skipped_when_no_override_provider() -> None:
    primary = FakeLLMProvider([_schema_response(), make_response(text="c")], name="fake")
    result = probe_backend(primary)
    assert result.capabilities.model_override is False


def test_model_override_false_when_override_call_errors() -> None:
    primary = FakeLLMProvider([_schema_response(), make_response(text="c")], name="fake")

    def _boom(request: LLMRequest) -> LLMResponse:
        raise LLMBackendError("override model rejected")

    override = FakeLLMProvider([_boom], name="fake")
    result = probe_backend(primary, override_provider=override)
    assert result.capabilities.model_override is False


def test_streaming_false_when_stream_raises() -> None:
    def _stream_boom(request: LLMRequest) -> LLMResponse:
        raise LLMTimeoutError("no streaming")

    # First entry answers complete(); second (consumed by stream()) raises.
    primary = FakeLLMProvider([_schema_response(), _stream_boom], name="fake")
    result = probe_backend(primary)
    assert result.capabilities.streaming is False
    # A failed streaming probe must not fail the overall probe.
    assert result.ok is True


def test_streaming_false_when_stream_yields_nothing() -> None:
    # A provider whose stream() is empty must report streaming False (not error).
    from collections.abc import Iterator

    class _EmptyStreamProvider:
        name = "fake"

        def is_available(self) -> bool:
            return True

        def complete(self, request: LLMRequest) -> LLMResponse:
            return make_response(structured={"ok": True, "echo": _SENTINEL})

        def stream(self, request: LLMRequest) -> Iterator[str]:
            return iter(())

    result = probe_backend(_EmptyStreamProvider())
    assert result.capabilities.streaming is False
    assert result.ok is True


@pytest.mark.parametrize(
    "error",
    [
        LLMBackendError("down"),
        LLMAuthError("unauthorized at /home/x"),
        LLMRateLimitError("quota"),
        LLMTimeoutError("timed out"),
    ],
)
def test_primary_failure_yields_not_ok(error: LLMError) -> None:
    def _fail(request: LLMRequest) -> LLMResponse:
        raise error

    primary = FakeLLMProvider([_fail], name="openrouter")
    result = probe_backend(primary)
    assert result.ok is False
    assert result.backend == "openrouter"
    assert result.capabilities == BackendCapabilities()
    assert result.error is not None
    assert result.detail == "probe failed"


def test_probe_result_is_json_serializable() -> None:
    primary = FakeLLMProvider([_schema_response(), make_response(text="c")], name="fake")
    result = probe_backend(primary)
    assert ProbeResult.model_validate_json(result.model_dump_json()) == result
