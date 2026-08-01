"""End-to-end seam test: a CLI adapter feeding :func:`complete_json`.

Proves that a Claude-shaped JSON envelope flows through a ``CliAdapter`` and then
through the structured-output recovery ladder to a validated Pydantic model,
without spawning any real subprocess. This de-risks the concrete Claude Code
adapter that follows.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from atlas.ai import LLMRequest, LLMResponse, Usage, complete_json
from atlas.ai.cli import CliAdapter, RunResult
from tests.conftest import FakeSubprocessRunner


class Extraction(BaseModel):
    """The structured result the caller wants back."""

    functions: list[str]


class _EnvelopeAdapter(CliAdapter):
    """Adapter that parses a Claude-Code-shaped stdout envelope.

    Mirrors the mapping the real Claude adapter will use: ``structured_output``
    to :attr:`~atlas.ai.base.LLMResponse.structured`, ``result`` to ``text``,
    the whole envelope to ``raw``, and ``total_cost_usd`` to ``Usage.cost_usd``.
    """

    name = "claude_like"

    def _build_argv(self, request: LLMRequest) -> list[str]:
        argv = [self._command, "-p", request.prompt, "--output-format", "json"]
        if request.response_schema is not None:
            argv += ["--json-schema", json.dumps(request.response_schema)]
        return argv

    def _parse_response(self, result: RunResult, request: LLMRequest) -> LLMResponse:
        envelope = json.loads(result.stdout)
        usage = Usage(cost_usd=envelope.get("total_cost_usd"))
        return LLMResponse(
            text=envelope.get("result", ""),
            structured=envelope.get("structured_output"),
            raw=envelope,
            usage=usage,
            model=envelope.get("model", "unknown"),
            backend=self.name,
        )


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
    adapter = _EnvelopeAdapter(command="claude", runner=runner)

    result = complete_json(adapter, LLMRequest(system=None, prompt="list funcs"), Extraction)

    assert result == Extraction(functions=["main", "parse"])
    # complete_json injected the schema, so the adapter emitted --json-schema.
    assert "--json-schema" in runner.calls[0].argv


def test_adapter_maps_cost_and_keeps_raw_envelope() -> None:
    runner = FakeSubprocessRunner(RunResult(returncode=0, stdout=_envelope_stdout(), stderr=""))
    adapter = _EnvelopeAdapter(command="claude", runner=runner)

    response = adapter.complete(LLMRequest(system=None, prompt="list funcs"))

    assert response.text == "Here are the functions."
    assert response.usage is not None
    assert response.usage.cost_usd == 0.0021
    # The session id has no LLMResponse field but survives in raw for resume.
    assert response.raw is not None
    assert response.raw["session_id"] == "abc-123"
