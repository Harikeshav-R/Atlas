"""Backend health reporting for ``atlas doctor``.

``atlas doctor`` validates configuration and backend availability (PROJECT.md §9,
§5.15). This module holds the **pure, I/O-light logic** — building each configured
backend, checking whether it reports itself available, and (opt-in) attaching
capability-probe results — separated from the Typer command wiring in
:mod:`atlas.cli.main` so it is fully testable with fake providers (AGENTS.md §6.2).

It constructs each backend named in the config chain (``default_backend`` +
``failover``) and records its availability
(:meth:`~atlas.ai.base.LLMProvider.is_available`) plus any construction error.
When ``probe`` is requested it also runs the live capability probe
(:func:`atlas.ai.probe.probe_backend`) — reusing cached results
(:mod:`atlas.ai.probe_cache`) unless refreshed — since that makes billable calls;
by default it only surfaces cached capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel
from rich.console import Group
from rich.table import Table
from rich.text import Text

from atlas.ai.base import LLMError
from atlas.ai.cli.runner import SubprocessRunner, default_subprocess_runner
from atlas.ai.probe import BackendCapabilities, ProbeResult, probe_backend
from atlas.ai.probe_cache import load_probe_cache, save_probe_cache
from atlas.ai.router import build_named_provider
from atlas.discovery.aggregators import (
    AGGREGATOR_TYPES,
    aggregator_requires_key,
    build_aggregator,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rich.console import RenderableType

    from atlas.ai.base import LLMProvider
    from atlas.config.schema import AggregatorsConfig, AiConfig
    from atlas.config.secrets import SecretStore

__all__ = [
    "AggregatorHealth",
    "BackendStatus",
    "DoctorReport",
    "build_aggregator_health",
    "render_report",
    "run_doctor",
]


class _ProbeFn(Protocol):
    """Callable that probes a provider — the seam tests inject a fake through."""

    def __call__(self, provider: LLMProvider, /) -> ProbeResult:
        """Return the probe result for ``provider``."""


class _CacheLoadFn(Protocol):
    """Callable that loads the probe cache (injected in tests)."""

    def __call__(self) -> dict[str, ProbeResult]:
        """Return cached results keyed by backend name."""


class _CacheSaveFn(Protocol):
    """Callable that saves the probe cache (injected in tests)."""

    def __call__(self, results: Mapping[str, ProbeResult], /) -> None:
        """Persist ``results`` keyed by backend name."""


class BackendStatus(BaseModel):
    """The health of a single configured AI backend.

    Attributes:
        name: The backend name as it appears in the config (e.g. ``"claude_code"``).
        role: Its role in the chain — ``"default"`` for ``default_backend`` or
            ``"failover"`` for a name from the ``failover`` list.
        available: Whether the backend constructed and reports itself available;
            ``False`` if construction failed or ``is_available()`` returned
            ``False``.
        detail: A short human-readable status line (never leaks secrets, paths,
            or vendor diagnostics).
        capabilities: The probed capabilities when known (from a live probe or
            the cache), else ``None``.
        capabilities_cached: Whether :attr:`capabilities` came from the cache
            (``True``) rather than a live probe this run (``False``).
    """

    name: str
    role: str
    available: bool
    detail: str
    capabilities: BackendCapabilities | None = None
    capabilities_cached: bool = False


class AggregatorHealth(BaseModel):
    """The configuration health of one aggregator job source (PROJECT.md §5.4-B).

    Attributes:
        name: The aggregator name (e.g. ``"adzuna"``).
        requires_key: Whether the provider is key-gated.
        active: Whether the provider is usable now — a free feed, or a key-gated
            provider that is enabled with its credential present.
        detail: A short status line (``"active"`` / ``"needs API key"`` /
            ``"disabled"``); never leaks the secret.
    """

    name: str
    requires_key: bool
    active: bool
    detail: str


class DoctorReport(BaseModel):
    """The full ``atlas doctor`` result.

    Attributes:
        backends: One :class:`BackendStatus` per configured backend, in chain
            order (default first, then failover).
        healthy: ``True`` iff at least one backend is available (so Atlas can run
            at all). Aggregators do not affect it — they are optional job sources.
        aggregators: One :class:`AggregatorHealth` per registered aggregator, in
            name order.
    """

    backends: list[BackendStatus]
    healthy: bool
    aggregators: list[AggregatorHealth] = []


def _ordered_backends(config: AiConfig) -> list[tuple[str, str]]:
    """Return ``(name, role)`` pairs in chain order (default first, then failover)."""
    pairs: list[tuple[str, str]] = [(config.default_backend, "default")]
    pairs += [(name, "failover") for name in config.failover]
    return pairs


def run_doctor(
    config: AiConfig,
    store: SecretStore,
    *,
    runner: SubprocessRunner = default_subprocess_runner,
    probe: bool = False,
    refresh: bool = False,
    probe_fn: _ProbeFn = probe_backend,
    cache_load: _CacheLoadFn = load_probe_cache,
    cache_save: _CacheSaveFn = save_probe_cache,
) -> DoctorReport:
    """Build and inspect every configured backend, returning a :class:`DoctorReport`.

    Each backend is constructed and checked independently: a backend that fails
    to build (unknown name, missing bare-mode key, …) is recorded as unavailable
    with a generic reason rather than aborting the whole report, so ``doctor``
    can show the user the full picture.

    Capability reporting is opt-in because a live probe makes billable calls:

    - ``probe=False`` (default): no live calls; attach cached capabilities when a
      cache entry exists for the backend.
    - ``probe=True``: run the live probe for backends missing from the cache (or
      for all backends when ``refresh=True``), reuse cached results otherwise,
      and persist the merged cache.

    Args:
        config: The ``[ai]`` configuration (backend selection + settings).
        store: The secret store passed to each backend factory.
        runner: The subprocess boundary for CLI backends; defaults to the real
            runner and is replaced by a fake in tests.
        probe: Whether to run/attach the live capability probe.
        refresh: When probing, re-probe every backend instead of reusing cached
            results.
        probe_fn: The probe callable (injected in tests to avoid live calls).
        cache_load: Loads the probe cache (injected in tests).
        cache_save: Saves the probe cache (injected in tests).

    Returns:
        The report over all configured backends.
    """
    cache = cache_load()
    updated: dict[str, ProbeResult] = dict(cache)
    statuses: list[BackendStatus] = []
    for name, role in _ordered_backends(config):
        status = _probe_backend(
            name,
            role,
            config,
            store,
            runner=runner,
            probe=probe,
            refresh=refresh,
            probe_fn=probe_fn,
            cache=cache,
            updated=updated,
        )
        statuses.append(status)
    if probe:
        cache_save(updated)
    healthy = any(status.available for status in statuses)
    return DoctorReport(backends=statuses, healthy=healthy)


def build_aggregator_health(
    config: AggregatorsConfig, store: SecretStore
) -> list[AggregatorHealth]:
    """Report each registered aggregator's configuration health.

    Free feeds are always ``active``. A key-gated provider is ``active`` when it
    builds (enabled + credential present), ``"disabled"`` when turned off in
    config, and ``"needs API key"`` when enabled but its credential is missing —
    mirroring the backend build→availability→detail shape, and never leaking the
    secret. Aggregators are optional, so this never affects ``DoctorReport.healthy``.
    """
    health: list[AggregatorHealth] = []
    for name in AGGREGATOR_TYPES:
        requires_key = aggregator_requires_key(name)
        if not requires_key:
            health.append(
                AggregatorHealth(name=name, requires_key=False, active=True, detail="active")
            )
            continue
        adapter = build_aggregator(name, config=config, store=store)
        if adapter is not None:
            detail = "active"
        elif _aggregator_enabled(config, name):
            detail = "needs API key"
        else:
            detail = "disabled"
        health.append(
            AggregatorHealth(
                name=name, requires_key=True, active=adapter is not None, detail=detail
            )
        )
    return health


def _aggregator_enabled(config: AggregatorsConfig, name: str) -> bool:
    """Return whether the aggregator ``name`` is enabled in ``config``."""
    section = getattr(config, name)
    return bool(section.enabled)


def _probe_backend(
    name: str,
    role: str,
    config: AiConfig,
    store: SecretStore,
    *,
    runner: SubprocessRunner,
    probe: bool,
    refresh: bool,
    probe_fn: _ProbeFn,
    cache: Mapping[str, ProbeResult],
    updated: dict[str, ProbeResult],
) -> BackendStatus:
    """Build one backend and return its :class:`BackendStatus`.

    Catches :class:`~atlas.ai.base.LLMError` from construction (e.g. an unknown
    backend name or a missing bare-mode key) so one misconfigured backend does
    not sink the whole report. Messages stay generic — no secrets or paths.

    When ``probe`` is set, runs the live probe (unless a fresh cached result
    exists and ``refresh`` is not set) and records the result in ``updated`` so
    the caller can persist the merged cache.
    """
    try:
        provider = build_named_provider(name, config, store, runner=runner)
    except LLMError as exc:
        return BackendStatus(name=name, role=role, available=False, detail=f"not configured: {exc}")

    available, detail = _availability(provider)

    capabilities, cached = _capabilities_for(
        name,
        provider,
        probe=probe,
        refresh=refresh,
        probe_fn=probe_fn,
        cache=cache,
        updated=updated,
    )
    return BackendStatus(
        name=name,
        role=role,
        available=available,
        detail=detail,
        capabilities=capabilities,
        capabilities_cached=cached,
    )


def _availability(provider: LLMProvider) -> tuple[bool, str]:
    """Return ``(available, detail)`` for a backend.

    CLI adapters expose :meth:`~atlas.ai.cli.base.CliAdapter.check_availability`,
    which carries a specific reason (e.g. a version floor); use it when present so
    ``atlas doctor`` shows *why* a backend is unavailable. Other providers (the API
    backend) fall back to the plain ``is_available()`` boolean.
    """
    check = getattr(provider, "check_availability", None)
    if callable(check):
        result = check()
        return result.available, result.reason
    if provider.is_available():
        return True, "available"
    return False, "unavailable (binary missing, or no API key / login)"


def _capabilities_for(
    name: str,
    provider: LLMProvider,
    *,
    probe: bool,
    refresh: bool,
    probe_fn: _ProbeFn,
    cache: Mapping[str, ProbeResult],
    updated: dict[str, ProbeResult],
) -> tuple[BackendCapabilities | None, bool]:
    """Return ``(capabilities, from_cache)`` for one backend.

    Without ``probe`` this only surfaces a cached result (if any). With ``probe``
    it reuses a cached result unless ``refresh`` is set, otherwise runs the live
    probe and stores it in ``updated`` for persistence.
    """
    cached_result = cache.get(name)
    if not probe:
        if cached_result is not None:
            return cached_result.capabilities, True
        return None, False
    if cached_result is not None and not refresh:
        return cached_result.capabilities, True
    result = probe_fn(provider)
    updated[name] = result
    return result.capabilities, False


# Column order for the compact capability line, with short labels.
_CAPABILITY_LABELS = (
    ("json_output", "json"),
    ("json_schema", "schema"),
    ("streaming", "stream"),
    ("system_prompt", "sys"),
    ("model_override", "model"),
)


def _render_capabilities(status: BackendStatus) -> Text:
    """Render one backend's capabilities as a compact, themed glyph line.

    ``✓``/``✗`` per capability when known; a muted hint otherwise. A cached
    result is tagged so the user knows it was not probed live this run.
    """
    if status.capabilities is None:
        return Text("not probed", style="muted")
    line = Text()
    for index, (field, label) in enumerate(_CAPABILITY_LABELS):
        if index:
            line.append("  ")
        supported = getattr(status.capabilities, field)
        line.append("✓" if supported else "✗", style="ok" if supported else "bad")
        line.append(f" {label}", style="muted")
    if status.capabilities_cached:
        line.append("  (cached)", style="muted")
    return line


def render_report(report: DoctorReport) -> RenderableType:
    """Render ``report`` as a styled Rich renderable for the terminal.

    Produces a table of backends (status mark, name, role, detail, capabilities)
    followed by an overall summary line, using the shared semantic theme styles
    (so it matches the rest of the CLI). The command layer prints the returned
    renderable through the shared console. JSON output for scripting is produced
    separately via :meth:`DoctorReport.model_dump_json`.
    """
    table = Table(title="AI backends", title_style="heading", title_justify="left")
    table.add_column("", no_wrap=True)  # status glyph
    table.add_column("Backend", style="accent", no_wrap=True)
    table.add_column("Role", no_wrap=True)
    table.add_column("Status")
    table.add_column("Capabilities")
    for status in report.backends:
        glyph = Text("●", style="ok") if status.available else Text("●", style="bad")
        detail_style = "success" if status.available else "error"
        table.add_row(
            glyph,
            status.name,
            Text(status.role, style="muted"),
            Text(status.detail, style=detail_style),
            _render_capabilities(status),
        )
    if report.healthy:
        summary = Text("✓ At least one backend is usable.", style="success")
    else:
        summary = Text("✗ No usable backend configured.", style="error")
    renderables: list[RenderableType] = [table, Text(), summary]
    if report.aggregators:
        renderables.extend([Text(), _render_aggregators(report.aggregators)])
    return Group(*renderables)


def _render_aggregators(aggregators: list[AggregatorHealth]) -> RenderableType:
    """Render the aggregator job sources as a styled Rich table."""
    table = Table(title="Aggregator sources", title_style="heading", title_justify="left")
    table.add_column("", no_wrap=True)  # status glyph
    table.add_column("Aggregator", style="accent", no_wrap=True)
    table.add_column("Key", no_wrap=True)
    table.add_column("Status")
    for item in aggregators:
        glyph = Text("●", style="ok") if item.active else Text("●", style="bad")
        detail_style = "success" if item.active else ("warning" if item.requires_key else "muted")
        table.add_row(
            glyph,
            item.name,
            Text("required" if item.requires_key else "free", style="muted"),
            Text(item.detail, style=detail_style),
        )
    return table
