"""Sprint working path resolver for parallel and stacked PR planning."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any


COMPLETED_STORY_STATUSES = ("TEST COMPLETED", "ACCEPTED/DONE")


class SprintWorkingPathKind(str, Enum):
    """Resolved execution path for one sprint story."""

    INDEPENDENT_PARALLEL = "independent-parallel"
    STACKED_DEPENDENT = "stacked-dependent"
    SEQUENTIAL_ONLY = "sequential-only"
    BLOCKED_NEEDS_PO = "blocked-needs-po"


class SprintDependencyKind(str, Enum):
    """Dependency type used by the sprint path resolver."""

    IMPLEMENTATION = "implementation"
    BUSINESS_DECISION = "business-decision"
    DESIGN = "design"
    CREDENTIAL = "credential"
    CROSS_REPO = "cross-repo"
    UNKNOWN = "unknown"


class SprintTestabilityTiming(str, Enum):
    """When Tester/Release Manager can validate a story."""

    AFTER_STORY_MERGE = "after-story-merge"
    AFTER_STACK_LAYER_MERGE = "after-stack-layer-merge"
    AFTER_PREREQUISITES_MERGE = "after-prerequisites-merge"
    AFTER_PO_DECISION = "after-po-decision"


@dataclass(frozen=True)
class SprintPathDependency:
    """A dependency where blocker_key must be considered before the story."""

    blocker_key: str
    kind: SprintDependencyKind = SprintDependencyKind.IMPLEMENTATION
    status: str = ""
    repository: str = ""
    trunk_branch: str = ""
    in_same_sprint: bool = True


@dataclass(frozen=True)
class SprintPathCandidate:
    """Story snapshot used by the resolver before worker assignment."""

    issue_key: str
    summary: str
    status: str
    next_agent_role: str
    repository: str
    trunk_branch: str
    sprint_label: str
    acceptance_criteria: tuple[str, ...]
    context_pack_path: str
    dependencies: tuple[SprintPathDependency, ...] = ()
    labels: tuple[str, ...] = ()
    requires_credentials: bool = False
    credentials_ready: bool = True
    ui_facing: bool = False
    accepted_design_reference: str = ""
    target_repositories: tuple[str, ...] = ()


@dataclass(frozen=True)
class SprintResolvedStoryPath:
    """Resolved deterministic path for one sprint story."""

    issue_key: str
    path_kind: SprintWorkingPathKind
    lane_id: str
    stack_id: str
    order: int
    blockers: tuple[str, ...]
    next_agent_role: str
    testability_timing: SprintTestabilityTiming
    prerequisite_keys: tuple[str, ...]
    downstream_issue_keys: tuple[str, ...]


@dataclass(frozen=True)
class SprintWorkingPathResolution:
    """Durable sprint path artifact."""

    sprint_label: str
    stories: tuple[SprintResolvedStoryPath, ...]
    guardrail: str


def resolve_sprint_working_paths(
    candidates: tuple[SprintPathCandidate, ...],
    *,
    sprint_label: str,
    completed_statuses: tuple[str, ...] = COMPLETED_STORY_STATUSES,
) -> SprintWorkingPathResolution:
    """Classify sprint stories into deterministic worker pickup paths."""

    sprint_label = _require_text("sprint_label", sprint_label)
    if not candidates:
        raise ValueError("candidates is required")
    _validate_unique_keys(candidates)
    normalized_completed = {_normalize_status(status) for status in completed_statuses}
    candidate_by_key = {_require_text("candidate.issue_key", candidate.issue_key): candidate for candidate in candidates}
    downstream_by_blocker = _downstream_by_blocker(candidates, normalized_completed)
    implementation_components = _implementation_components(candidates, normalized_completed)
    component_by_key = {
        key: component
        for component in implementation_components
        for key in component
    }
    orders_by_component = {
        component[0]: _topological_order(component, candidates, normalized_completed)
        for component in implementation_components
    }
    component_root_by_key = {
        key: component[0]
        for component in implementation_components
        for key in component
    }
    resolved: list[SprintResolvedStoryPath] = []
    for candidate in sorted(candidates, key=lambda item: item.issue_key):
        blockers = list(_candidate_gate_blockers(candidate))
        dependency_decision = _dependency_decision(candidate, candidate_by_key, normalized_completed)
        blockers.extend(dependency_decision["po_blockers"])
        component = component_by_key.get(candidate.issue_key, (candidate.issue_key,))
        component_root = component_root_by_key.get(candidate.issue_key, candidate.issue_key)
        component_order = orders_by_component.get(component_root, (candidate.issue_key,))
        component_has_cycle = set(component_order) != set(component)
        component_same_trunk = _component_has_same_repository_trunk(component, candidate_by_key)
        if component_has_cycle:
            blockers.append("Implementation dependency cycle requires Product Owner or Release Manager correction.")

        if blockers:
            path_kind = SprintWorkingPathKind.BLOCKED_NEEDS_PO
            lane_id = f"blocked-{_slug(candidate.issue_key)}"
            stack_id = f"stack-{_slug(component_root)}" if len(component) > 1 and component_same_trunk else ""
            order = 0
            next_agent_role = "product_owner"
            testability = SprintTestabilityTiming.AFTER_PO_DECISION
        elif dependency_decision["sequential_blockers"] or (len(component) > 1 and not component_same_trunk):
            path_kind = SprintWorkingPathKind.SEQUENTIAL_ONLY
            lane_id = f"sequential-{_slug(component_root)}"
            stack_id = ""
            order = _order_for(candidate.issue_key, component_order)
            next_agent_role = "scheduler"
            testability = SprintTestabilityTiming.AFTER_PREREQUISITES_MERGE
            blockers.extend(dependency_decision["sequential_blockers"])
            if len(component) > 1 and not component_same_trunk:
                blockers.append("Stack spans multiple repositories or trunk branches and must stay sequential.")
        elif len(component) > 1:
            path_kind = SprintWorkingPathKind.STACKED_DEPENDENT
            lane_id = f"stack-lane-{_slug(component_root)}"
            stack_id = f"stack-{_slug(component_root)}"
            order = _order_for(candidate.issue_key, component_order)
            next_agent_role = candidate.next_agent_role.strip()
            testability = SprintTestabilityTiming.AFTER_STACK_LAYER_MERGE
        else:
            path_kind = SprintWorkingPathKind.INDEPENDENT_PARALLEL
            lane_id = f"parallel-{_slug(candidate.issue_key)}"
            stack_id = ""
            order = 1
            next_agent_role = candidate.next_agent_role.strip()
            testability = SprintTestabilityTiming.AFTER_STORY_MERGE

        resolved.append(
            SprintResolvedStoryPath(
                issue_key=candidate.issue_key,
                path_kind=path_kind,
                lane_id=lane_id,
                stack_id=stack_id,
                order=order,
                blockers=tuple(blockers),
                next_agent_role=next_agent_role,
                testability_timing=testability,
                prerequisite_keys=_active_prerequisite_keys(candidate, normalized_completed),
                downstream_issue_keys=tuple(sorted(downstream_by_blocker.get(candidate.issue_key, ()))),
            )
        )
    return SprintWorkingPathResolution(
        sprint_label=sprint_label,
        stories=tuple(resolved),
        guardrail=(
            "Agents must follow the resolved lane, stack id, order, blockers, next role, and testability timing. "
            "If the artifact is missing or conflicts with Jira, stop and create a Product Owner inbox question."
        ),
    )


def sprint_working_path_resolution_to_dict(resolution: SprintWorkingPathResolution) -> dict[str, Any]:
    """Convert a sprint path resolution into a durable JSON-compatible artifact."""

    return {
        "sprint_label": resolution.sprint_label,
        "guardrail": resolution.guardrail,
        "stories": [
            {
                "issue_key": story.issue_key,
                "path_kind": story.path_kind.value,
                "lane_id": story.lane_id,
                "stack_id": story.stack_id,
                "order": story.order,
                "blockers": list(story.blockers),
                "next_agent_role": story.next_agent_role,
                "testability_timing": story.testability_timing.value,
                "prerequisite_keys": list(story.prerequisite_keys),
                "downstream_issue_keys": list(story.downstream_issue_keys),
            }
            for story in resolution.stories
        ],
    }


def render_sprint_working_path_markdown(resolution: SprintWorkingPathResolution) -> str:
    """Render a sprint path artifact for Jira comments, docs, or logs."""

    lines = [
        f"# Sprint Working Path - {resolution.sprint_label}",
        "",
        f"Guardrail: {resolution.guardrail}",
        "",
        "| Issue | Path | Lane | Stack | Order | Blockers | Next agent | Testability | Downstream |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for story in resolution.stories:
        lines.append(
            "| "
            + " | ".join(
                (
                    story.issue_key,
                    story.path_kind.value,
                    story.lane_id,
                    story.stack_id or "-",
                    str(story.order),
                    ", ".join(story.blockers) if story.blockers else "-",
                    story.next_agent_role,
                    story.testability_timing.value,
                    ", ".join(story.downstream_issue_keys) if story.downstream_issue_keys else "-",
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _dependency_decision(
    candidate: SprintPathCandidate,
    candidate_by_key: dict[str, SprintPathCandidate],
    completed: set[str],
) -> dict[str, list[str]]:
    po_blockers: list[str] = []
    sequential_blockers: list[str] = []
    for dependency in candidate.dependencies:
        if _dependency_is_completed(dependency, completed):
            continue
        if dependency.kind in {
            SprintDependencyKind.BUSINESS_DECISION,
            SprintDependencyKind.CREDENTIAL,
            SprintDependencyKind.DESIGN,
            SprintDependencyKind.UNKNOWN,
        }:
            po_blockers.append(
                f"{dependency.blocker_key} is an unresolved {dependency.kind.value} dependency."
            )
            continue
        if dependency.kind is SprintDependencyKind.CROSS_REPO:
            sequential_blockers.append(f"{dependency.blocker_key} is a cross-repo dependency.")
            continue
        if not dependency.in_same_sprint:
            sequential_blockers.append(f"{dependency.blocker_key} is not co-scheduled in this sprint.")
            continue
        blocker = candidate_by_key.get(dependency.blocker_key)
        if blocker is None:
            sequential_blockers.append(f"{dependency.blocker_key} is missing from the sprint path input.")
            continue
        if not _same_repository_trunk(candidate, blocker):
            sequential_blockers.append(f"{dependency.blocker_key} uses a different repository or trunk branch.")
    return {"po_blockers": po_blockers, "sequential_blockers": sequential_blockers}


def _candidate_gate_blockers(candidate: SprintPathCandidate) -> tuple[str, ...]:
    blockers: list[str] = []
    if not _require_text("candidate.issue_key", candidate.issue_key):
        blockers.append("Issue key is missing.")
    if not candidate.acceptance_criteria:
        blockers.append("Acceptance criteria are missing or unclear.")
    if not candidate.context_pack_path.strip():
        blockers.append("Context pack path is missing.")
    if candidate.requires_credentials and not candidate.credentials_ready:
        blockers.append("Required credentials or integration readiness are missing.")
    if candidate.ui_facing and not candidate.accepted_design_reference.strip():
        blockers.append("Accepted UI design reference is missing.")
    if not candidate.repository.strip() or not candidate.trunk_branch.strip():
        blockers.append("Repository and trunk branch are required for sprint path resolution.")
    if len(_target_repositories(candidate)) > 1:
        blockers.append("Multiple target repositories require sequential-only routing or PO-approved split.")
    return tuple(blockers)


def _implementation_components(
    candidates: tuple[SprintPathCandidate, ...],
    completed: set[str],
) -> tuple[tuple[str, ...], ...]:
    keys = {candidate.issue_key for candidate in candidates}
    adjacency = {key: set() for key in keys}
    for candidate in candidates:
        for dependency in candidate.dependencies:
            if dependency.kind is not SprintDependencyKind.IMPLEMENTATION:
                continue
            if _dependency_is_completed(dependency, completed) or dependency.blocker_key not in keys:
                continue
            adjacency[candidate.issue_key].add(dependency.blocker_key)
            adjacency[dependency.blocker_key].add(candidate.issue_key)
    components: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for key in sorted(keys):
        if key in seen or not adjacency[key]:
            continue
        stack = [key]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(sorted(adjacency[current] - component))
        seen.update(component)
        if len(component) > 1:
            components.append(tuple(sorted(component)))
    return tuple(components)


def _topological_order(
    component: tuple[str, ...],
    candidates: tuple[SprintPathCandidate, ...],
    completed: set[str],
) -> tuple[str, ...]:
    component_set = set(component)
    blockers_by_dependent: dict[str, set[str]] = {key: set() for key in component}
    for candidate in candidates:
        if candidate.issue_key not in component_set:
            continue
        for dependency in candidate.dependencies:
            if dependency.kind is SprintDependencyKind.IMPLEMENTATION and dependency.blocker_key in component_set:
                if not _dependency_is_completed(dependency, completed):
                    blockers_by_dependent[candidate.issue_key].add(dependency.blocker_key)
    ordered: list[str] = []
    remaining = set(component)
    while remaining:
        ready = sorted(
            key
            for key in remaining
            if not blockers_by_dependent[key].intersection(remaining)
        )
        if not ready:
            return tuple(ordered)
        for key in ready:
            remaining.remove(key)
            ordered.append(key)
    return tuple(ordered)


def _component_has_same_repository_trunk(
    component: tuple[str, ...],
    candidate_by_key: dict[str, SprintPathCandidate],
) -> bool:
    repositories = {_normalized_text(candidate_by_key[key].repository) for key in component}
    trunks = {_normalized_text(candidate_by_key[key].trunk_branch) for key in component}
    return len(repositories) == 1 and "" not in repositories and len(trunks) == 1 and "" not in trunks


def _downstream_by_blocker(
    candidates: tuple[SprintPathCandidate, ...],
    completed: set[str],
) -> dict[str, set[str]]:
    downstream: dict[str, set[str]] = {}
    for candidate in candidates:
        for dependency in candidate.dependencies:
            if _dependency_is_completed(dependency, completed):
                continue
            downstream.setdefault(dependency.blocker_key, set()).add(candidate.issue_key)
    return downstream


def _active_prerequisite_keys(candidate: SprintPathCandidate, completed: set[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            dependency.blocker_key
            for dependency in candidate.dependencies
            if not _dependency_is_completed(dependency, completed)
        )
    )


def _dependency_is_completed(dependency: SprintPathDependency, completed: set[str]) -> bool:
    return _normalize_status(dependency.status) in completed


def _order_for(issue_key: str, order: tuple[str, ...]) -> int:
    try:
        return order.index(issue_key) + 1
    except ValueError:
        return 0


def _same_repository_trunk(candidate: SprintPathCandidate, blocker: SprintPathCandidate) -> bool:
    return (
        _normalized_text(candidate.repository) == _normalized_text(blocker.repository)
        and _normalized_text(candidate.trunk_branch) == _normalized_text(blocker.trunk_branch)
    )


def _target_repositories(candidate: SprintPathCandidate) -> tuple[str, ...]:
    targets = candidate.target_repositories or ((candidate.repository,) if candidate.repository else ())
    return tuple(sorted({_normalized_text(target) for target in targets if _normalized_text(target)}))


def _validate_unique_keys(candidates: tuple[SprintPathCandidate, ...]) -> None:
    seen: set[str] = set()
    for candidate in candidates:
        key = _require_text("candidate.issue_key", candidate.issue_key)
        if key in seen:
            raise ValueError(f"Duplicate sprint path candidate: {key}")
        seen.add(key)


def _require_text(field: str, value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _normalize_status(status: str) -> str:
    return " ".join(str(status).replace("/", " / ").split()).casefold()


def _normalized_text(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def _slug(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-").replace("/", "-")
