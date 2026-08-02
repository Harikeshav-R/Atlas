"""End-to-end seam test: the Claude Code adapter feeding :func:`complete_json`.

Proves that a Claude-shaped JSON envelope flows through the shipping
:class:`~atlas.ai.cli.claude_code.ClaudeCodeAdapter` and then through the
structured-output recovery ladder to a validated Pydantic model, without
spawning any real subprocess.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from atlas.ai import LLMRequest, complete_json
from atlas.ai.cli import ClaudeCodeAdapter, RunResult
from tests.conftest import FakeSubprocessRunner


class Extraction(BaseModel):
    """The structured result the caller wants back."""

    functions: list[str]


def _envelope_stdout() -> str:
    return json.dumps(
        {
            "result": "Here are the functions.",
            "structured_output": {"functions": ["main", "parse"]},
            "session_id": "abc-123",
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "total_cost_usd": 0.0021,
            "model": "claude-sonnet",
        }
    )


def test_envelope_flows_through_complete_json_to_model() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_envelope_stdout(), stderr=""))
    adapter = ClaudeCodeAdapter(command="claude", runner=runner)

    result = complete_json(adapter, LLMRequest(system=None, prompt="list funcs"), Extraction)

    assert result == Extraction(functions=["main", "parse"])
    # complete_json injected the schema, so the adapter emitted --json-schema.
    assert "--json-schema" in runner.calls[0].argv


def test_adapter_maps_cost_and_keeps_raw_envelope() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_envelope_stdout(), stderr=""))
    adapter = ClaudeCodeAdapter(command="claude", runner=runner)

    response = adapter.complete(LLMRequest(system=None, prompt="list funcs"))

    assert response.text == "Here are the functions."
    assert response.usage is not None
    assert response.usage.cost_usd == 0.0021
    # The session id has no LLMResponse field but survives in raw for resume.
    assert response.raw is not None
    assert response.raw["session_id"] == "abc-123"
