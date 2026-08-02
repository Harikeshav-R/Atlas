"""Tests for the model-capability seam in :mod:`atlas.ai.api.capabilities`."""

from __future__ import annotations

from atlas.ai.api import CapabilityFn, ModelCapabilities, default_capabilities


def test_model_capabilities_defaults_to_no_schema_support() -> None:
    assert ModelCapabilities().supports_response_schema is False


def test_default_capabilities_conforms_to_capability_fn() -> None:
    # ``default_capabilities`` is the production lookup; it must satisfy the seam
    # protocol without being called (calling it would import litellm — banned in
    # the hermetic suite per AGENTS.md §6.2).
    fn: CapabilityFn = default_capabilities
    assert callable(fn)
