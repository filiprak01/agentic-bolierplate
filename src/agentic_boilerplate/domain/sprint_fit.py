"""Sprint fit planning and complexity warning model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.domain.release_scope import ReleaseScope, ScopeIssue, SprintRing
from agentic_boilerplate.domain.story_complexity import (
    DEFAULT_COMPLEXITY_ROUTING,
    ComplexityLevel,
)


class SprintFitError(ValueError):
    """Raised when sprint fit planning input is incomplete."""


class SprintFitWarningType(str, Enum):
    """Types of sprint-fit warnings."""

    COMPLEXITY_LIMIT = "complexity_limit"
    STORY_COUNT_LIMIT = "story_count_limit"


@dataclass(frozen=True)
class SprintFitCapacity:
    """Configured working-window limits for a sprint ring."""

    codex_window: str
    max_complexity_points: int
    max_story_count: int


@dataclass(frozen=True)
class SprintFitWarning:
    """Warning emitted without automatically splitting coherent scope."""

    warning_type: SprintFitWarningType
    message: str
    actual: int
    limit: int


@dataclass(frozen=True)
class SprintIssueLabelPlan:
    """Labels that should be applied to an included story."""

    issue_key: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class SprintFitPlan:
    """Sprint-fit decision for one sprint ring."""

    release_scope_key: str
    sprint_ring_number: int
    coherent_deliverable_scope: str
    codex_window: str
    story_count: int
    complexity_total: int
    likely_fits_codex_window: bool
    override_reason: str | None
    warnings: tuple[SprintFitWarning, ...]
    issue_label_plans: tuple[SprintIssueLabelPlan, ...]


def complexity_warning_points(complexity: ComplexityLevel) -> int:
    """Return numeric warning points for a story complexity level."""

    return DEFAULT_COMPLEXITY_ROUTING[complexity].points


def scope_issue_from_complexity(
    *,
    key: str,
    title: str,
    issue_type: str,
    complexity: ComplexityLevel,
    status: str = "",
) -> ScopeIssue:
    """Create a scope issue using the shared complexity routing points."""

    return ScopeIssue(
        key=_require_text("key", key),
        title=_require_text("title", title),
        issue_type=_require_text("issue_type", issue_type),
        complexity_points=complexity_warning_points(complexity),
        status=status.strip(),
    )


def build_sprint_fit_plan(
    release_scope: ReleaseScope,
    *,
    sprint_ring_number: int,
    coherent_deliverable_scope: str,
    capacity: SprintFitCapacity,
    release_label: str,
    allow_capacity_override: bool = False,
    override_reason: str | None = None,
) -> SprintFitPlan:
    """Evaluate sprint fit without automatically splitting coherent scope."""

    _require_text("coherent_deliverable_scope", coherent_deliverable_scope)
    _require_text("release_label", release_label)
    _validate_capacity(capacity)
    if allow_capacity_override:
        _require_text("override_reason", override_reason or "")

    ring = _sprint_ring_by_number(release_scope, sprint_ring_number)
    warnings = _build_warnings(ring, capacity)
    likely_fits = not warnings or allow_capacity_override
    labels = tuple(
        SprintIssueLabelPlan(
            issue_key=issue.key,
            labels=sprint_scope_labels(
                release_label=release_label,
                sprint_ring_number=ring.number,
                capacity_warning=bool(warnings),
            ),
        )
        for issue in ring.included_issues
    )

    return SprintFitPlan(
        release_scope_key=release_scope.key,
        sprint_ring_number=ring.number,
        coherent_deliverable_scope=coherent_deliverable_scope.strip(),
        codex_window=capacity.codex_window,
        story_count=len(ring.included_issues),
        complexity_total=ring.complexity_total,
        likely_fits_codex_window=likely_fits,
        override_reason=override_reason.strip() if override_reason else None,
        warnings=warnings,
        issue_label_plans=labels,
    )


def sprint_scope_labels(
    *,
    release_label: str,
    sprint_ring_number: int,
    capacity_warning: bool = False,
) -> tuple[str, ...]:
    """Return release and sprint-ring labels for planned stories."""

    _require_text("release_label", release_label)
    _require_positive_int("sprint_ring_number", sprint_ring_number)

    labels = [
        release_label.strip(),
        f"sprint-ring-{str(sprint_ring_number).zfill(2)}",
        f"mvp-sprint-{str(sprint_ring_number).zfill(2)}",
    ]
    if capacity_warning:
        labels.append("sprint-fit-warning")
    return tuple(labels)


def _build_warnings(
    ring: SprintRing,
    capacity: SprintFitCapacity,
) -> tuple[SprintFitWarning, ...]:
    warnings: list[SprintFitWarning] = []
    if ring.complexity_total > capacity.max_complexity_points:
        warnings.append(
            SprintFitWarning(
                warning_type=SprintFitWarningType.COMPLEXITY_LIMIT,
                message="Sprint complexity exceeds the configured working-window target.",
                actual=ring.complexity_total,
                limit=capacity.max_complexity_points,
            )
        )
    story_count = len(ring.included_issues)
    if story_count > capacity.max_story_count:
        warnings.append(
            SprintFitWarning(
                warning_type=SprintFitWarningType.STORY_COUNT_LIMIT,
                message="Sprint story count exceeds the configured working-window target.",
                actual=story_count,
                limit=capacity.max_story_count,
            )
        )
    return tuple(warnings)


def _sprint_ring_by_number(release_scope: ReleaseScope, number: int) -> SprintRing:
    for ring in release_scope.sprint_rings:
        if ring.number == number:
            return ring
    raise SprintFitError(f"sprint ring {number} was not found")


def _validate_capacity(capacity: SprintFitCapacity) -> None:
    _require_text("capacity.codex_window", capacity.codex_window)
    _require_positive_int("capacity.max_complexity_points", capacity.max_complexity_points)
    _require_positive_int("capacity.max_story_count", capacity.max_story_count)


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SprintFitError(f"{name} is required")
    return value.strip()


def _require_positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SprintFitError(f"{name} must be a positive integer")
