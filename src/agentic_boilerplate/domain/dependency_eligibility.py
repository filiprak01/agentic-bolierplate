"""Scheduler dependency eligibility rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agentic_boilerplate.integrations.jira import JiraIssueDependencyLinks, JiraLinkedIssue


DEFAULT_DEPENDENCY_SATISFIED_STATUSES = ("TEST COMPLETED", "ACCEPTED/DONE")
DEFAULT_BUG_RESOLVED_STATUSES = ("TEST COMPLETED", "ACCEPTED/DONE")
DEFAULT_SUPPORT_TASK_LABELS = ("support-task",)


class DependencyBlockerKind(str, Enum):
    """Reasons that make an issue ineligible for assignment."""

    INCOMPLETE_PREREQUISITE = "incomplete_prerequisite"
    UNKNOWN_PREREQUISITE_STATUS = "unknown_prerequisite_status"
    UNRESOLVED_LINKED_BUG = "unresolved_linked_bug"


class DependencyGraphIssueKind(str, Enum):
    """Sprint dependency graph issues that block assignment or closure."""

    CYCLE = "cycle"
    RECIPROCAL_BLOCKS_LINK = "reciprocal_blocks_link"


@dataclass(frozen=True)
class DependencyBlocker:
    """One blocker that prevents normal scheduler assignment."""

    issue_key: str
    kind: DependencyBlockerKind
    status: str = ""
    issue_type: str = ""
    summary: str = ""


@dataclass(frozen=True)
class DependencyGraphEdge:
    """One canonical Jira Blocks relationship represented as blocker -> blocked."""

    blocker_key: str
    blocked_key: str
    source_issue_key: str = ""
    jira_link_id: str = ""

    @property
    def notation(self) -> str:
        return f"{self.blocker_key} -> {self.blocked_key}"


@dataclass(frozen=True)
class DependencyGraphIssue:
    """One dependency graph problem that must be resolved before continuation."""

    kind: DependencyGraphIssueKind
    issue_keys: tuple[str, ...]
    edge_notations: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class DependencyGraphAuditResult:
    """Whole-sprint dependency graph safety result."""

    edges: tuple[DependencyGraphEdge, ...]
    issues: tuple[DependencyGraphIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def blocked_issue_keys(self) -> tuple[str, ...]:
        keys = {key for issue in self.issues for key in issue.issue_keys}
        return tuple(sorted(keys))


@dataclass(frozen=True)
class DependencyEligibilityResult:
    """Dependency check result recorded before scheduler assignment."""

    issue_key: str
    eligible: bool
    overridden: bool
    blockers: tuple[DependencyBlocker, ...]
    satisfied_prerequisites: tuple[JiraLinkedIssue, ...]
    support_task_prerequisites: tuple[JiraLinkedIssue, ...]
    downstream_blocked_issue_keys: tuple[str, ...]
    reasons: tuple[str, ...]
    override_reason: str | None = None


def check_dependency_eligibility(
    links: JiraIssueDependencyLinks,
    *,
    satisfied_statuses: tuple[str, ...] = DEFAULT_DEPENDENCY_SATISFIED_STATUSES,
    resolved_bug_statuses: tuple[str, ...] = DEFAULT_BUG_RESOLVED_STATUSES,
    support_task_labels: tuple[str, ...] = DEFAULT_SUPPORT_TASK_LABELS,
    allow_override: bool = False,
    override_reason: str | None = None,
) -> DependencyEligibilityResult:
    """Evaluate whether a Jira story can be assigned to a worker."""

    normalized_satisfied = _normalize_statuses(satisfied_statuses)
    normalized_resolved_bugs = _normalize_statuses(resolved_bug_statuses)
    normalized_support_task_labels = _normalize_labels(support_task_labels)
    blocker_issues = _blocker_issue_snapshots(links)
    blockers: list[DependencyBlocker] = []
    satisfied: list[JiraLinkedIssue] = []
    support_tasks: list[JiraLinkedIssue] = []

    for issue in blocker_issues:
        normalized_status = _normalize_status(issue.status)
        if _has_any_label(issue, normalized_support_task_labels):
            support_tasks.append(issue)
            continue
        if not normalized_status:
            blockers.append(
                DependencyBlocker(
                    issue_key=issue.key,
                    kind=DependencyBlockerKind.UNKNOWN_PREREQUISITE_STATUS,
                    status=issue.status,
                    issue_type=issue.issue_type,
                    summary=issue.summary,
                )
            )
        elif normalized_status in normalized_satisfied:
            satisfied.append(issue)
        else:
            blockers.append(
                DependencyBlocker(
                    issue_key=issue.key,
                    kind=DependencyBlockerKind.INCOMPLETE_PREREQUISITE,
                    status=issue.status,
                    issue_type=issue.issue_type,
                    summary=issue.summary,
                )
            )

    for bug in links.linked_bugs:
        if _normalize_status(bug.status) not in normalized_resolved_bugs:
            blockers.append(
                DependencyBlocker(
                    issue_key=bug.key,
                    kind=DependencyBlockerKind.UNRESOLVED_LINKED_BUG,
                    status=bug.status,
                    issue_type=bug.issue_type,
                    summary=bug.summary,
                )
            )

    has_blockers = bool(blockers)
    overridden = has_blockers and allow_override and bool((override_reason or "").strip())
    eligible = not has_blockers or overridden
    return DependencyEligibilityResult(
        issue_key=links.issue_key,
        eligible=eligible,
        overridden=overridden,
        blockers=tuple(blockers),
        satisfied_prerequisites=tuple(satisfied),
        support_task_prerequisites=tuple(support_tasks),
        downstream_blocked_issue_keys=links.blocked,
        reasons=_eligibility_reasons(eligible, overridden, blockers, satisfied, support_tasks, override_reason),
        override_reason=override_reason.strip() if overridden and override_reason else None,
    )


def build_dependency_graph_audit(
    dependency_links: tuple[JiraIssueDependencyLinks, ...],
) -> DependencyGraphAuditResult:
    """Audit Jira Blocks links across a sprint or release scope.

    Jira dependency direction is canonicalized as ``blocker -> blocked``. If a
    story ``X`` depends on ``Y``, the graph edge must be ``Y -> X``.
    """

    edges = _dependency_graph_edges(dependency_links)
    issues = _reciprocal_link_issues(edges) + _cycle_issues(edges)
    return DependencyGraphAuditResult(edges=edges, issues=_dedupe_graph_issues(issues))


def render_dependency_graph_audit(result: DependencyGraphAuditResult) -> str:
    """Render a sprint dependency graph audit note for Jira or durable evidence."""

    lines = [
        "# Dependency Graph Audit",
        "",
        f"- Passed: {'yes' if result.passed else 'no'}",
        f"- Edges checked: {len(result.edges)}",
        f"- Blocking graph issues: {len(result.issues)}",
        "",
        "## Canonical Edges",
    ]
    if result.edges:
        lines.extend(f"- {edge.notation}" for edge in result.edges)
    else:
        lines.append("- None")
    lines.extend(["", "## Graph Issues"])
    if result.issues:
        for issue in result.issues:
            lines.append(f"- {issue.kind.value}: {issue.message}")
            if issue.edge_notations:
                lines.append(f"  Edges: {', '.join(issue.edge_notations)}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def render_dependency_eligibility_note(result: DependencyEligibilityResult) -> str:
    """Render a durable scheduler assignment note in Markdown."""

    lines = [
        f"# Dependency Eligibility - {result.issue_key}",
        "",
        f"- Eligible: {'yes' if result.eligible else 'no'}",
        f"- Override used: {'yes' if result.overridden else 'no'}",
    ]
    if result.override_reason:
        lines.append(f"- Override reason: {result.override_reason}")
    lines.extend(["", "## Reasons"])
    lines.extend(f"- {reason}" for reason in result.reasons)
    lines.extend(["", "## Blocking Items"])
    if result.blockers:
        for blocker in result.blockers:
            status = blocker.status or "unknown status"
            lines.append(f"- {blocker.issue_key}: {blocker.kind.value} ({status})")
    else:
        lines.append("- None")
    lines.extend(["", "## Satisfied Prerequisites"])
    if result.satisfied_prerequisites:
        for issue in result.satisfied_prerequisites:
            lines.append(f"- {issue.key}: {issue.status}")
    else:
        lines.append("- None")
    lines.extend(["", "## Support Task Link Warnings"])
    if result.support_task_prerequisites:
        for issue in result.support_task_prerequisites:
            label_suffix = f" [{', '.join(issue.labels)}]" if issue.labels else ""
            lines.append(
                f"- {issue.key}: support-task Blocks link treated as closure sequencing, not delivery prerequisite{label_suffix}"
            )
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _dependency_graph_edges(dependency_links: tuple[JiraIssueDependencyLinks, ...]) -> tuple[DependencyGraphEdge, ...]:
    by_pair: dict[tuple[str, str], DependencyGraphEdge] = {}
    for links in dependency_links:
        current_key = links.issue_key.strip()
        if not current_key:
            continue
        for blocker_key in links.blockers:
            blocker = blocker_key.strip()
            if blocker:
                by_pair.setdefault(
                    (blocker, current_key),
                    DependencyGraphEdge(blocker_key=blocker, blocked_key=current_key, source_issue_key=current_key),
                )
        for blocked_key in links.blocked:
            blocked = blocked_key.strip()
            if blocked:
                by_pair.setdefault(
                    (current_key, blocked),
                    DependencyGraphEdge(blocker_key=current_key, blocked_key=blocked, source_issue_key=current_key),
                )
    return tuple(by_pair[key] for key in sorted(by_pair))


def _reciprocal_link_issues(edges: tuple[DependencyGraphEdge, ...]) -> tuple[DependencyGraphIssue, ...]:
    pairs = {(edge.blocker_key, edge.blocked_key): edge for edge in edges}
    issues: list[DependencyGraphIssue] = []
    seen: set[frozenset[str]] = set()
    for edge in edges:
        reverse = pairs.get((edge.blocked_key, edge.blocker_key))
        if reverse is None:
            continue
        pair_key = frozenset((edge.blocker_key, edge.blocked_key))
        if pair_key in seen:
            continue
        seen.add(pair_key)
        issues.append(
            DependencyGraphIssue(
                kind=DependencyGraphIssueKind.RECIPROCAL_BLOCKS_LINK,
                issue_keys=tuple(sorted(pair_key)),
                edge_notations=(edge.notation, reverse.notation),
                message=(
                    f"Reciprocal Blocks links exist between {edge.blocker_key} and {edge.blocked_key}; "
                    "Product Owner or Release Manager must confirm the intended dependency direction."
                ),
            )
        )
    return tuple(issues)


def _cycle_issues(edges: tuple[DependencyGraphEdge, ...]) -> tuple[DependencyGraphIssue, ...]:
    adjacency: dict[str, tuple[str, ...]] = {}
    for edge in edges:
        adjacency.setdefault(edge.blocker_key, ())
        adjacency.setdefault(edge.blocked_key, ())
    mutable_adjacency: dict[str, list[str]] = {key: [] for key in adjacency}
    for edge in edges:
        mutable_adjacency[edge.blocker_key].append(edge.blocked_key)
    adjacency = {key: tuple(sorted(values)) for key, values in mutable_adjacency.items()}

    issues: list[DependencyGraphIssue] = []
    seen_cycles: set[tuple[str, ...]] = set()
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(issue_key: str) -> None:
        if issue_key in visiting:
            start = visiting.index(issue_key)
            cycle_nodes = visiting[start:] + [issue_key]
            canonical = _canonical_cycle_key(cycle_nodes)
            if canonical not in seen_cycles:
                seen_cycles.add(canonical)
                issue_nodes = tuple(dict.fromkeys(cycle_nodes[:-1]))
                edge_notations = tuple(
                    f"{cycle_nodes[index]} -> {cycle_nodes[index + 1]}" for index in range(len(cycle_nodes) - 1)
                )
                issues.append(
                    DependencyGraphIssue(
                        kind=DependencyGraphIssueKind.CYCLE,
                        issue_keys=tuple(sorted(issue_nodes)),
                        edge_notations=edge_notations,
                        message=(
                            "Dependency cycle detected: "
                            + " -> ".join(cycle_nodes)
                            + ". Scheduler and sprint closure must stop until the graph is corrected."
                        ),
                    )
                )
            return
        if issue_key in visited:
            return
        visiting.append(issue_key)
        for next_key in adjacency.get(issue_key, ()):
            visit(next_key)
        visiting.pop()
        visited.add(issue_key)

    for issue_key in sorted(adjacency):
        visit(issue_key)
    return tuple(issues)


def _dedupe_graph_issues(issues: tuple[DependencyGraphIssue, ...]) -> tuple[DependencyGraphIssue, ...]:
    seen: set[tuple[DependencyGraphIssueKind, tuple[str, ...], tuple[str, ...]]] = set()
    deduped: list[DependencyGraphIssue] = []
    for issue in issues:
        key = (issue.kind, issue.issue_keys, issue.edge_notations)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return tuple(deduped)


def _canonical_cycle_key(cycle_nodes: list[str]) -> tuple[str, ...]:
    unique = cycle_nodes[:-1]
    rotations = [tuple(unique[index:] + unique[:index]) for index in range(len(unique))]
    reversed_unique = list(reversed(unique))
    rotations.extend(tuple(reversed_unique[index:] + reversed_unique[:index]) for index in range(len(reversed_unique)))
    return min(rotations)


def _blocker_issue_snapshots(links: JiraIssueDependencyLinks) -> tuple[JiraLinkedIssue, ...]:
    if links.blocker_issues:
        return links.blocker_issues
    return tuple(JiraLinkedIssue(key=key) for key in links.blockers)


def _eligibility_reasons(
    eligible: bool,
    overridden: bool,
    blockers: list[DependencyBlocker],
    satisfied: list[JiraLinkedIssue],
    support_tasks: list[JiraLinkedIssue],
    override_reason: str | None,
) -> tuple[str, ...]:
    if overridden:
        return (
            "Dependency blockers exist but assignment was allowed by explicit override.",
            f"Override reason: {override_reason.strip()}",
        )
    if blockers:
        return tuple(f"{blocker.issue_key} blocks assignment: {blocker.kind.value}" for blocker in blockers)
    if satisfied:
        reasons = ["All prerequisite dependency links are satisfied."]
        if support_tasks:
            reasons.append(_support_task_reason(support_tasks))
        return tuple(reasons)
    if eligible:
        if support_tasks:
            return (_support_task_reason(support_tasks),)
        return ("No blocking dependency links were found.",)
    return ("Dependency eligibility could not be determined.",)


def _normalize_statuses(statuses: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalize_status(status) for status in statuses if _normalize_status(status))


def _normalize_status(status: str) -> str:
    return " ".join(status.replace("/", " / ").split()).casefold()


def _normalize_labels(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(label.strip().casefold() for label in labels if label.strip())


def _has_any_label(issue: JiraLinkedIssue, labels: frozenset[str]) -> bool:
    if not labels:
        return False
    return any(label.strip().casefold() in labels for label in issue.labels)


def _support_task_reason(support_tasks: list[JiraLinkedIssue]) -> str:
    keys = ", ".join(issue.key for issue in support_tasks)
    return (
        "Support-task Blocks links were flagged as closure sequencing warnings, "
        f"not delivery prerequisites: {keys}."
    )