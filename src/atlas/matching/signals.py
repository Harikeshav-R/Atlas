"""Deterministic fit signals computed locally from a posting + profile.

Per PROJECT.md §5.6, Atlas computes a handful of deterministic signals — salary
fit, location fit, work-authorization compatibility, and deal-breaker hits — from
the stored :class:`~atlas.db.models.JobPosting` and the profile's
:class:`~atlas.profiles.preferences.ProfilePreferences`. These are **passed into
the scoring prompt as context and shown as badges**; they inform and annotate the
AI score but never pre-discard a posting (the AI scores everything, §5.6).

Everything here is pure (no I/O), and every signal degrades to ``UNKNOWN`` when the
posting or the profile lacks the data to decide — a conservative default that never
manufactures a mismatch from missing information.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas.matching.structure import DeterministicSignals, SalaryFit, SignalStatus
from atlas.profiles.preferences import RemoteType

if TYPE_CHECKING:
    from atlas.db.models import JobPosting
    from atlas.profiles.preferences import ProfilePreferences

__all__ = ["compute_signals"]

#: Keys in a posting's free-form ``salary`` JSON that hold the upper-bound figure,
#: in preference order (the most representative of "what this role pays").
_SALARY_MAX_KEYS = ("max", "maximum", "upper", "amount", "value", "min", "minimum")

#: Keys that hold the lower-bound figure, in preference order.
_SALARY_MIN_KEYS = ("min", "minimum", "amount", "value", "max", "maximum")


def compute_signals(posting: JobPosting, preferences: ProfilePreferences) -> DeterministicSignals:
    """Compute the deterministic fit signals for ``posting`` against ``preferences``.

    Args:
        posting: The stored job posting to evaluate.
        preferences: The active profile's typed preferences.

    Returns:
        A :class:`DeterministicSignals` with each signal set or left ``UNKNOWN``
        when the inputs don't support a decision.
    """
    return DeterministicSignals(
        salary=_salary_fit(posting.salary, preferences),
        location=_location_fit(posting, preferences),
        work_auth=_work_auth_fit(posting, preferences),
        dealbreakers=_dealbreaker_hits(posting, preferences),
    )


def _coerce_amount(value: Any) -> int | None:
    """Return ``value`` as a positive int if it looks like a salary figure, else ``None``.

    Accepts ints/floats and digit-bearing strings (stripping ``$``, commas, and
    spaces); rejects non-positive or unparseable values.
    """
    if isinstance(value, bool):  # bool is an int subclass — never a salary figure.
        return None
    if isinstance(value, int | float):
        amount = int(value)
        return amount if amount > 0 else None
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").replace(" ", "")
        try:
            amount = int(float(cleaned))
        except ValueError:
            return None
        return amount if amount > 0 else None
    return None


def _first_amount(salary: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    """Return the first parseable positive amount among ``keys`` in ``salary``."""
    for key in keys:
        if key in salary:
            amount = _coerce_amount(salary[key])
            if amount is not None:
                return amount
    return None


def _salary_fit(salary: dict[str, Any], preferences: ProfilePreferences) -> SalaryFit:
    """Compare a posting's stated pay to the profile's floor/target.

    Uses the profile's ``salary_target`` when set, else its ``salary_floor``, as
    the reference point; ``ABOVE``/``WITHIN``/``BELOW`` is decided from the
    posting's upper figure against that reference (with the floor as a lower gate).
    Returns ``UNKNOWN`` when either side lacks a figure.
    """
    comp = preferences.compensation
    reference = comp.salary_target if comp.salary_target is not None else comp.salary_floor
    if reference is None:
        return SalaryFit.UNKNOWN
    posting_high = _first_amount(salary, _SALARY_MAX_KEYS)
    if posting_high is None:
        return SalaryFit.UNKNOWN
    floor = comp.salary_floor
    if floor is not None and posting_high < floor:
        return SalaryFit.BELOW
    if posting_high < reference:
        return SalaryFit.BELOW
    if posting_high > reference:
        return SalaryFit.ABOVE
    return SalaryFit.WITHIN


def _location_fit(posting: JobPosting, preferences: ProfilePreferences) -> SignalStatus:
    """Decide whether the posting's location/remote posture is acceptable.

    A posting whose ``remote_type`` is among the profile's acceptable
    ``remote_types`` matches; a remote-role profile that lists no on-site option
    mismatches an explicitly on-site posting; a city named in the profile that
    appears in the posting's location matches. Returns ``UNKNOWN`` when the
    profile expresses no location preference or the posting states no location.
    """
    loc = preferences.location
    remote_type = (posting.remote_type or "").strip().lower()
    if loc.remote_types and remote_type:
        accepted = {value.value for value in loc.remote_types}
        if remote_type in accepted:
            return SignalStatus.MATCH
        # An explicit on-site posting mismatches a purely remote profile that is
        # not willing to relocate; otherwise leave it to the AI.
        if (
            remote_type == RemoteType.ONSITE.value
            and RemoteType.ONSITE.value not in accepted
            and not loc.willing_to_relocate
        ):
            return SignalStatus.MISMATCH
    if loc.cities and posting.location:
        haystack = posting.location.lower()
        if any(city.strip().lower() in haystack for city in loc.cities if city.strip()):
            return SignalStatus.MATCH
    return SignalStatus.UNKNOWN


#: Phrases that signal a posting will not sponsor a visa.
_NO_SPONSORSHIP_PHRASES = (
    "no sponsorship",
    "not able to sponsor",
    "unable to sponsor",
    "cannot sponsor",
    "without sponsorship",
    "do not provide sponsorship",
    "does not provide sponsorship",
    "no visa sponsorship",
    "us citizen",
    "u.s. citizen",
    "citizenship required",
    "security clearance",
)


def _work_auth_fit(posting: JobPosting, preferences: ProfilePreferences) -> SignalStatus:
    """Decide work-authorization compatibility from the posting text.

    Only meaningful when the profile needs sponsorship: a posting that states it
    will not sponsor (or requires citizenship/clearance) mismatches; otherwise
    ``MATCH``. When the profile does not need sponsorship, this is ``UNKNOWN``
    (nothing to gate on).
    """
    if not preferences.work_authorization.needs_sponsorship:
        return SignalStatus.UNKNOWN
    haystack = _posting_text(posting)
    if any(phrase in haystack for phrase in _NO_SPONSORSHIP_PHRASES):
        return SignalStatus.MISMATCH
    return SignalStatus.MATCH


def _dealbreaker_hits(posting: JobPosting, preferences: ProfilePreferences) -> list[str]:
    """Return the profile deal-breakers whose text appears in the posting.

    A case-insensitive substring match of each non-empty deal-breaker against the
    posting's description + requirements text. Preserves the profile's order and
    de-duplicates.
    """
    haystack = _posting_text(posting)
    hits: list[str] = []
    for raw in preferences.deal_breakers:
        needle = raw.strip()
        if needle and needle.lower() in haystack and needle not in hits:
            hits.append(needle)
    return hits


def _posting_text(posting: JobPosting) -> str:
    """Return the posting's searchable text (description + requirements) lowercased."""
    parts: list[str] = [posting.description]
    requirements = posting.requirements
    for key in ("must", "nice"):
        value = requirements.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return "\n".join(parts).lower()
