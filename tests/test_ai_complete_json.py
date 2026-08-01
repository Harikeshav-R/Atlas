"""Tests for the structured-output recovery ladder in :mod:`atlas.ai.complete_json`."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from atlas.ai import LLMOutputError, LLMRequest, complete_json
from atlas.ai.complete_json import _extract_json, _temperature_for
from tests.conftest import FakeLLMProvider, make_response


class Point(BaseModel):
    """Minimal schema used to validate recovered JSON."""

    x: int
    y: int


def _request(temperature: float | None = None) -> LLMRequest:
    return LLMRequest(system=None, prompt="give me a point", temperature=temperature)


# --- _extract_json ---------------------------------------------------------------


def test_extract_json_plain_object() -> None:
    assert _extract_json('{"x": 1, "y": 2}') == {"x": 1, "y": 2}


def test_extract_json_returns_none_without_brace() -> None:
    assert _extract_json("no json here") is None


def test_extract_json_ignores_braces_inside_strings() -> None:
    assert _extract_json('{"note": "a } and a { inside"}') == {"note": "a } and a { inside"}


def test_extract_json_handles_escaped_quote_in_string() -> None:
    assert _extract_json('{"quote": "a \\" mark"}') == {"quote": 'a " mark'}


def test_extract_json_handles_escaped_backslash_before_quote() -> None:
    # The backslash is escaped, so the following quote closes the string.
    assert _extract_json('{"path": "c\\\\"}') == {"path": "c\\"}


def test_extract_json_strips_leading_and_trailing_prose() -> None:
    text = 'Here you go:\n```json\n{"x": 3, "y": 4}\n```\nHope that helps!'
    assert _extract_json(text) == {"x": 3, "y": 4}


def test_extract_json_returns_none_for_unbalanced_braces() -> None:
    assert _extract_json('{"x": 1') is None


def test_extract_json_returns_none_for_malformed_balanced_span() -> None:
    # Braces balance but the content is not valid JSON.
    assert _extract_json("{not valid}") is None


def test_extract_json_stops_at_first_balanced_object() -> None:
    assert _extract_json('{"x": 1, "y": 2} {"x": 9, "y": 9}') == {"x": 1, "y": 2}


def test_extract_json_handles_nested_objects() -> None:
    # A nested closing brace drops depth to a non-zero value and keeps scanning.
    assert _extract_json('{"outer": {"inner": 1}}') == {"outer": {"inner": 1}}


# --- _temperature_for ------------------------------------------------------------


def test_temperature_first_attempt_keeps_base() -> None:
    assert _temperature_for(0.5, 0, 0.2) == pytest.approx(0.5)
    assert _temperature_for(None, 0, 0.2) is None


def test_temperature_escalates_from_base() -> None:
    assert _temperature_for(0.5, 2, 0.2) == pytest.approx(0.9)


def test_temperature_escalates_from_zero_when_base_none() -> None:
    assert _temperature_for(None, 1, 0.2) == pytest.approx(0.2)


# --- complete_json ladder --------------------------------------------------------


def test_happy_path_reads_native_structured_field() -> None:
    provider = FakeLLMProvider([make_response(structured={"x": 1, "y": 2})])
    result = complete_json(provider, _request(), Point)
    assert result == Point(x=1, y=2)
    # The schema was injected into the request the provider saw.
    assert provider.calls[0].response_schema == Point.model_json_schema()


def test_falls_back_to_text_extraction_when_no_structured_field() -> None:
    provider = FakeLLMProvider([make_response(text='result: {"x": 5, "y": 6}')])
    assert complete_json(provider, _request(), Point) == Point(x=5, y=6)


def test_invalid_structured_field_recovers_from_text() -> None:
    provider = FakeLLMProvider([make_response(structured={"x": "nope"}, text='{"x": 7, "y": 8}')])
    assert complete_json(provider, _request(), Point) == Point(x=7, y=8)


def test_retries_then_succeeds_and_escalates_temperature() -> None:
    provider = FakeLLMProvider(
        [
            make_response(text="no json at all"),
            make_response(structured={"x": 1, "y": 1}),
        ]
    )
    result = complete_json(provider, _request(temperature=0.1), Point)
    assert result == Point(x=1, y=1)
    # First attempt keeps base temperature; second attempt escalates.
    assert provider.calls[0].temperature == pytest.approx(0.1)
    assert provider.calls[1].temperature == pytest.approx(0.3)


def test_prompt_only_fallback_after_retries_exhausted() -> None:
    provider = FakeLLMProvider(
        [
            make_response(text="still nothing"),
            make_response(text="nope"),
            make_response(text="nada"),
            make_response(text='{"x": 2, "y": 2}'),
        ]
    )
    result = complete_json(provider, _request(), Point)
    assert result == Point(x=2, y=2)
    # The fallback call drops the schema and appends the JSON-only instruction.
    fallback = provider.calls[-1]
    assert fallback.response_schema is None
    assert "ONLY a single JSON object" in fallback.prompt


def test_raises_output_error_when_everything_fails() -> None:
    provider = FakeLLMProvider([make_response(text="x") for _ in range(4)])
    with pytest.raises(LLMOutputError, match="did not return output matching Point"):
        complete_json(provider, _request(), Point)


def test_output_error_chains_last_validation_error() -> None:
    # Every attempt yields extractable-but-invalid JSON, so a ValidationError
    # is chained onto the raised LLMOutputError.
    provider = FakeLLMProvider([make_response(text='{"x": 1}') for _ in range(4)])
    with pytest.raises(LLMOutputError) as excinfo:
        complete_json(provider, _request(), Point)
    assert excinfo.value.__cause__ is not None


def test_does_not_mutate_caller_request() -> None:
    provider = FakeLLMProvider([make_response(structured={"x": 1, "y": 2})])
    request = _request(temperature=0.4)
    complete_json(provider, request, Point)
    assert request.response_schema is None
    assert request.temperature == pytest.approx(0.4)
    assert request.prompt == "give me a point"


def test_respects_custom_max_retries() -> None:
    # max_retries=0 means one structured attempt, then the prompt-only fallback.
    provider = FakeLLMProvider([make_response(text="miss"), make_response(text='{"x": 0, "y": 0}')])
    assert complete_json(provider, _request(), Point, max_retries=0) == Point(x=0, y=0)
    assert len(provider.calls) == 2
