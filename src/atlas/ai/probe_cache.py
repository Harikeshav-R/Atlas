"""Persistence for capability-probe results.

The capability probe (:mod:`atlas.ai.probe`) makes live, billable calls, so its
results are cached to disk and reused: ``atlas doctor`` shows the last-known
capabilities without calling anything, and only ``--probe``/``--refresh`` run a
fresh probe. Results live as a single JSON file under the platformdirs **cache
dir** (disposable by nature — losing it just means re-probing).

Read/write mirror the config loader idiom (:mod:`atlas.config.loader`): the path
defaults from a helper, writes create the parent directory and dump
``model_dump(mode="json")``, and reads guard on existence. A missing *or*
unreadable/corrupt cache is treated as **empty** rather than an error — the probe
simply re-runs — so a stale or hand-mangled cache file can never crash the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from atlas.ai.probe import ProbeResult
from atlas.config.paths import cache_dir

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["load_probe_cache", "probe_cache_file", "save_probe_cache"]

#: Name of the probe-cache file within the cache dir.
_CACHE_FILENAME = "capabilities.json"


def probe_cache_file() -> Path:
    """Return the path to the probe-result cache inside the cache dir."""
    return cache_dir() / _CACHE_FILENAME


def load_probe_cache(path: Path | None = None) -> dict[str, ProbeResult]:
    """Load cached probe results keyed by backend name.

    A missing file, unreadable bytes, invalid JSON, or a payload that no longer
    matches :class:`~atlas.ai.probe.ProbeResult` all yield an empty mapping (the
    cache is disposable — the caller just re-probes), never an exception.

    Args:
        path: The cache file to read; defaults to :func:`probe_cache_file`.

    Returns:
        A mapping of backend name to its cached :class:`ProbeResult` (empty when
        the cache is absent or unusable).
    """
    target = path if path is not None else probe_cache_file()
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return {name: ProbeResult.model_validate(value) for name, value in raw.items()}
    except (OSError, ValueError, ValidationError, AttributeError):
        # Corrupt/mangled cache — treat as empty so the CLI never crashes on it.
        return {}


def save_probe_cache(results: Mapping[str, ProbeResult], path: Path | None = None) -> None:
    """Write ``results`` (keyed by backend name) to the cache as JSON.

    Creates the cache directory if needed (:func:`cache_dir` does not), matching
    the config-writer idiom.

    Args:
        results: Mapping of backend name to its :class:`ProbeResult`.
        path: The destination file; defaults to :func:`probe_cache_file`.
    """
    target = path if path is not None else probe_cache_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {name: result.model_dump(mode="json") for name, result in results.items()}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
