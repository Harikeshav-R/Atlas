"""Backend health reporting for ``atlas doctor``.

``atlas doctor`` validates configuration and backend availability (PROJECT.md §9,
§5.15). This module holds the **pure, I/O-light logic** — building each configured
backend and checking whether it reports itself available — separated from the
Typer command wiring in :mod:`atlas.cli.app` so it is fully testable with fake
providers (AGENTS.md §6.2).

This is the v1 report: it constructs each backend named in the config chain
(``default_backend`` + ``failover``) and records its availability
(:meth:`~atlas.ai.base.LLMProvider.is_available`) plus any construction error. It
does **not** yet run the live "reply OK as JSON" capability round-trip — that
probe (and where its results cache) arrives in a later phase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from rich.console import Group
from rich.table import Table
from rich.text import Text

from atlas.ai.base import LLMError
from atlas.ai.cli.runner import SubprocessRunner, default_subprocess_runner
from atlas.ai.router import build_named_provider

if TYPE_CHECKING:
    from rich.console import RenderableType

    from atlas.config.schema import AiConfig
    from atlas.config.secrets import SecretStore

__all__ = ["BackendStatus", "DoctorReport", "render_report", "run_doctor"]


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
    """

    name: str
    role: str
    available: bool
    detail: str


class DoctorReport(BaseModel):
    """The full ``atlas doctor`` result.

    Attributes:
        backends: One :class:`BackendStatus` per configured backend, in chain
            order (default first, then failover).
        healthy: ``True`` iff at least one backend is available (so Atlas can run
            at all).
    """

    backends: list[BackendStatus]
    healthy: bool


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
) -> DoctorReport:
    """Build and inspect every configured backend, returning a :class:`DoctorReport`.

    Each backend is constructed and checked independently: a backend that fails
    to build (unknown name, missing bare-mode key, …) is recorded as unavailable
    with a generic reason rather than aborting the whole report, so ``doctor``
    can show the user the full picture.

    Args:
        config: The ``[ai]`` configuration (backend selection + settings).
        store: The secret store passed to each backend factory.
        runner: The subprocess boundary for CLI backends; defaults to the real
            runner and is replaced by a fake in tests.

    Returns:
        The report over all configured backends.
    """
    statuses: list[BackendStatus] = []
    for name, role in _ordered_backends(config):
        statuses.append(_probe_backend(name, role, config, store, runner=runner))
    healthy = any(status.available for status in statuses)
    return DoctorReport(backends=statuses, healthy=healthy)


def _probe_backend(
    name: str,
    role: str,
    config: AiConfig,
    store: SecretStore,
    *,
    runner: SubprocessRunner,
) -> BackendStatus:
    """Build one backend and return its :class:`BackendStatus`.

    Catches :class:`~atlas.ai.base.LLMError` from construction (e.g. an unknown
    backend name or a missing bare-mode key) so one misconfigured backend does
    not sink the whole report. Messages stay generic — no secrets or paths.
    """
    try:
        provider = build_named_provider(name, config, store, runner=runner)
    except LLMError as exc:
        return BackendStatus(name=name, role=role, available=False, detail=f"not configured: {exc}")
    if provider.is_available():
        return BackendStatus(name=name, role=role, available=True, detail="available")
    return BackendStatus(
        name=name,
        role=role,
        available=False,
        detail="unavailable (binary missing, or no API key / login)",
    )


def render_report(report: DoctorReport) -> RenderableType:
    """Render ``report`` as a styled Rich renderable for the terminal.

    Produces a table of backends (status mark, name, role, detail) followed by an
    overall summary line, using the shared semantic theme styles (so it matches
    the rest of the CLI). The command layer prints the returned renderable
    through the shared console. JSON output for scripting is produced separately
    via :meth:`DoctorReport.model_dump_json`.
    """
    table = Table(title="AI backends", title_style="heading", title_justify="left")
    table.add_column("", no_wrap=True)  # status glyph
    table.add_column("Backend", style="accent", no_wrap=True)
    table.add_column("Role", no_wrap=True)
    table.add_column("Status")
    for status in report.backends:
        glyph = Text("●", style="ok") if status.available else Text("●", style="bad")
        detail_style = "success" if status.available else "error"
        table.add_row(
            glyph,
            status.name,
            Text(status.role, style="muted"),
            Text(status.detail, style=detail_style),
        )
    if report.healthy:
        summary = Text("✓ At least one backend is usable.", style="success")
    else:
        summary = Text("✗ No usable backend configured.", style="error")
    return Group(table, Text(), summary)
