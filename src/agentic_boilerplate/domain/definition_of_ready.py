"""Machine-checkable Definition of Ready gate for worker assignment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


READY_TO_START_STATUS = "READY TO START"


class DefinitionOfReadyBlockerKind(str, Enum):
    """Machine-readable reasons a story cannot be assigned."""

    STATUS_NOT_READY = "status_not_ready"
    MISSING_RELEASE_OR_SPRINT = "missing_release_or_sprint"
    MISSING_ACCEPTANCE_CRITERIA = "missing_acceptance_criteria"
    MISSING_CONTEXT_PACK = "missing_context_pack"
    MISSING_ROLE_ROUTE = "missing_role_route"
    MISSING_MODEL_ROUTE = "missing_model_route"
    MISSING_TARGET_REPOSITORY = "missing_target_repository"
    MISSING_TARGET_WORKSPACE = "missing_target_workspace"
    UNRESOLVED_DEPENDENCY = "unresolved_dependency"
    UNRESOLVED_LINKED_BUG = "unresolved_linked_bug"
    MISSING_SETUP_VALIDATION = "missing_setup_validation"
    STALE_LIMIT_STATE = "stale_limit_state"
    MISSING_DESIGN_REFERENCE = "missing_design_reference"
    MISSING_DESIGN_DEPENDENCY = "missing_design_dependency"
    MISSING_MULTI_REPO_CHANGE_MAP = "missing_multi_repo_change_map"


@dataclass(frozen=True)
class DefinitionOfReadyInput:
    """Inputs required before a worker assignment can be created."""

    issue_key: str
    issue_type: str
    status: str
    labels: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    context_pack_path: str
    role_route: str
    model: str
    reasoning: str
    target_repositories: tuple[str, ...]
    target_workspace_path: str
    sprint_name: str = ""
    dependency_gate_passed: bool = True
    unresolved_dependency_keys: tuple[str, ...] = ()
    unresolved_linked_bug_keys: tuple[str, ...] = ()
    setup_validation_passed: bool = True
    limit_state_fresh: bool = True
    ui_facing: bool = False
    accepted_design_reference: str = ""
    design_dependency_key: str = ""
    repository_change_map: tuple[str, ...] = ()


@dataclass(frozen=True)
class DefinitionOfReadyBlocker:
    """One PO-visible and machine-readable readiness blocker."""

    kind: DefinitionOfReadyBlockerKind
    field: str
    message: str
    related_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DefinitionOfReadyDecision:
    """Definition of Ready pass/fail result for scheduler assignment."""

    issue_key: str
    ready: bool
    blockers: tuple[DefinitionOfReadyBlocker, ...]
    reasons: tuple[str, ...]


def evaluate_definition_of_ready(candidate: DefinitionOfReadyInput) -> DefinitionOfReadyDecision:
    """Evaluate whether a Jira story is assignable to a worker."""

    blockers: list[DefinitionOfReadyBlocker] = []
    labels = _normalize_labels(candidate.labels)

    if _normalize_status(candidate.status) != _normalize_status(READY_TO_START_STATUS):
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.STATUS_NOT_READY,
                "status",
                f"Story must be {READY_TO_START_STATUS} before assignment.",
            )
        )
    if not _has_release_and_sprint_context(labels, candidate.sprint_name):
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_RELEASE_OR_SPRINT,
                "labels",
                "Story must have release/sprint labels or Jira sprint membership.",
            )
        )
    if not candidate.acceptance_criteria:
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_ACCEPTANCE_CRITERIA,
                "acceptance_criteria",
                "At least one acceptance criterion is required.",
            )
        )
    if not candidate.context_pack_path.strip():
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_CONTEXT_PACK,
                "context_pack_path",
                "Approved context pack path is required.",
            )
        )
    if not candidate.role_route.strip():
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_ROLE_ROUTE,
                "role_route",
                "Role route is required.",
            )
        )
    if not candidate.model.strip() or not candidate.reasoning.strip():
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_MODEL_ROUTE,
                "model_reasoning",
                "Model and reasoning route are required.",
            )
        )
    if not candidate.target_repositories:
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_TARGET_REPOSITORY,
                "target_repositories",
                "At least one target repository is required.",
            )
        )
    if not candidate.target_workspace_path.strip():
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_TARGET_WORKSPACE,
                "target_workspace_path",
                "Target workspace path is required.",
            )
        )
    if not candidate.dependency_gate_passed or candidate.unresolved_dependency_keys:
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.UNRESOLVED_DEPENDENCY,
                "dependency_gate",
                "Dependency gate must pass before assignment.",
                candidate.unresolved_dependency_keys,
            )
        )
    if candidate.unresolved_linked_bug_keys:
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.UNRESOLVED_LINKED_BUG,
                "linked_bugs",
                "Linked bugs must be resolved and retested before assignment.",
                candidate.unresolved_linked_bug_keys,
            )
        )
    if not candidate.setup_validation_passed:
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_SETUP_VALIDATION,
                "setup_validation",
                "Integration and local setup validation must pass before assignment.",
            )
        )
    if not candidate.limit_state_fresh:
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.STALE_LIMIT_STATE,
                "limit_state",
                "Codex limit state must be fresh enough to start the assignment.",
            )
        )
    if candidate.ui_facing and not candidate.accepted_design_reference.strip():
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_DESIGN_REFERENCE,
                "accepted_design_reference",
                "UI-facing implementation requires an accepted design reference.",
            )
        )
    if candidate.ui_facing and not candidate.design_dependency_key.strip():
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_DESIGN_DEPENDENCY,
                "design_dependency_key",
                "UI-facing implementation requires a blocking dependency to the design story.",
            )
        )
    if len(candidate.target_repositories) > 1 and not candidate.repository_change_map:
        blockers.append(
            _blocker(
                DefinitionOfReadyBlockerKind.MISSING_MULTI_REPO_CHANGE_MAP,
                "repository_change_map",
                "Multi-repo stories must identify which change belongs to each repository.",
            )
        )

    ready = not blockers
    return DefinitionOfReadyDecision(
        issue_key=candidate.issue_key,
        ready=ready,
        blockers=tuple(blockers),
        reasons=_reasons(candidate, blockers),
    )


def render_definition_of_ready_explanation(decision: DefinitionOfReadyDecision) -> str:
    """Render a PO-visible Definition of Ready explanation."""

    lines = [
        f"# Definition of Ready - {decision.issue_key}",
        "",
        f"- Ready: {'yes' if decision.ready else 'no'}",
        "",
        "## Reasons",
    ]
    lines.extend(f"- {reason}" for reason in decision.reasons)
    lines.extend(["", "## Blockers"])
    if decision.blockers:
        for blocker in decision.blockers:
            suffix = f" ({', '.join(blocker.related_keys)})" if blocker.related_keys else ""
            lines.append(f"- {blocker.kind.value}: {blocker.message}{suffix}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _blocker(
    kind: DefinitionOfReadyBlockerKind,
    field: str,
    message: str,
    related_keys: tuple[str, ...] = (),
) -> DefinitionOfReadyBlocker:
    return DefinitionOfReadyBlocker(kind=kind, field=field, message=message, related_keys=related_keys)


def _has_release_and_sprint_context(labels: frozenset[str], sprint_name: str) -> bool:
    if sprint_name.strip():
        return True
    has_release_label = any(label.startswith("release-") for label in labels)
    has_sprint_label = any(label.startswith("sprint-") for label in labels)
    return has_release_label and has_sprint_label


def _normalize_labels(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(label.strip().casefold() for label in labels if label.strip())


def _normalize_status(status: str) -> str:
    return " ".join(status.replace("/", " / ").split()).casefold()


def _reasons(candidate: DefinitionOfReadyInput, blockers: list[DefinitionOfReadyBlocker]) -> tuple[str, ...]:
    if blockers:
        return tuple(f"{blocker.kind.value}: {blocker.message}" for blocker in blockers)
    return (
        f"{candidate.issue_key} is READY TO START with executable context.",
        "Acceptance criteria, context pack, routing, repository/workspace, dependency, setup, and limits gates passed.",
    )
