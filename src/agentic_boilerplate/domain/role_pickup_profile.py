"""Role-specific Jira pickup profile policy.

The scheduler owns Jira polling and converts eligible Jira issues into durable
assignments. Role workers use these profiles to explain which issues are
eligible, skipped, or blocked without improvising their own status rules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from agentic_boilerplate.domain.po_inbox import AgentRole


READY_TO_START = "READY TO START"
DEV_COMPLETED = "DEV COMPLETED"
IN_TESTING = "IN TESTING"
TEST_COMPLETED = "TEST COMPLETED"
FUNNEL = "FUNNEL"
ACCEPTED_DONE = "ACCEPTED/DONE"


class PickupArtifactKind(str, Enum):
    """Artifacts that must be visible before a role can pick a story."""

    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    DEVELOPMENT_EVIDENCE = "development_evidence"
    DESIGN_REFERENCE = "design_reference"
    MERGE_SHA = "merge_sha"
    PR_BRANCH = "pr_branch"
    PR_HEAD_SHA = "pr_head_sha"
    PR_URL = "pr_url"
    PUBLICATION_TARGET = "publication_target"
    REGRESSION_MANIFEST = "regression_manifest"
    SECURITY_SCOPE = "security_scope"
    TEST_REQUEST = "test_request"


class PickupGateKind(str, Enum):
    """Reusable gates evaluated before assignment creation."""

    ACTIVE_SPRINT = "active_sprint"
    ASSIGNMENT_UNLOCKED = "assignment_unlocked"
    CI_SUCCESS = "ci_success"
    CODEX_LIMIT_AVAILABLE = "codex_limit_available"
    DEFINITION_OF_READY = "definition_of_ready"
    DEPENDENCIES_CLEAR = "dependencies_clear"
    DEPENDENCY_GRAPH_CLEAR = "dependency_graph_clear"
    DESIGN_ACCEPTED = "design_accepted"
    EVIDENCE_AVAILABLE = "evidence_available"
    MERGEABILITY_CLEAN = "mergeability_clean"
    MERGED_TO_MAIN = "merged_to_main"
    NO_BLOCKING_BUGS = "no_blocking_bugs"
    NO_SECRET_EXPOSURE = "no_secret_exposure"
    PR_HANDOFF_COMPLETE = "pr_handoff_complete"
    PUBLICATION_TARGET_ENABLED = "publication_target_enabled"
    REGRESSION_MANIFEST_READY = "regression_manifest_ready"
    RETRO_READY = "retro_ready"
    REWORK_SIGNAL = "rework_signal"
    SECURITY_SCOPE_DEFINED = "security_scope_defined"
    SPRINT_DELIVERY_READY = "sprint_delivery_ready"
    TEST_REQUEST_RECORDED = "test_request_recorded"


class PickupDecisionKind(str, Enum):
    """Role pickup decision for one Jira candidate."""

    PICK = "pick"
    SKIP = "skip"
    BLOCKED = "blocked"


class PickupSkipReason(str, Enum):
    """Machine-readable reason why a candidate was not picked."""

    ACTIVE_LOCK = "active_lock"
    BLOCKING_BUG = "blocking_bug"
    CI_NOT_SUCCESS = "ci_not_success"
    CODEX_LIMIT_BLOCKED = "codex_limit_blocked"
    DEPENDENCY_GRAPH_BLOCKED = "dependency_graph_blocked"
    DIRTY_MERGEABILITY = "dirty_mergeability"
    DOR_FAILED = "definition_of_ready_failed"
    EXCLUDED_ISSUE_TYPE = "excluded_issue_type"
    EXCLUDED_LABEL = "excluded_label"
    EXPLICIT_RETEST_NOT_REQUESTED = "explicit_retest_not_requested"
    FUTURE_SPRINT = "future_sprint"
    MISSING_ACCEPTANCE_CRITERIA = "missing_acceptance_criteria"
    MISSING_ARTIFACT = "missing_artifact"
    MISSING_DESIGN_REFERENCE = "missing_design_reference"
    MISSING_PUBLICATION_TARGET = "missing_publication_target"
    MISSING_REQUIRED_LABEL = "missing_required_label"
    MISSING_REWORK_SIGNAL = "missing_rework_signal"
    MISSING_SECURITY_SCOPE = "missing_security_scope"
    MISSING_TEST_REQUEST = "missing_test_request"
    PROJECT_MISMATCH = "project_mismatch"
    PR_NOT_OPEN = "pr_not_open"
    REGRESSION_MANIFEST_MISSING = "regression_manifest_missing"
    RETRO_NOT_READY = "retro_not_ready"
    SECRET_EXPOSURE = "secret_exposure"
    SPRINT_DELIVERY_NOT_READY = "sprint_delivery_not_ready"
    STALE_PR_METADATA = "stale_pr_metadata"
    UNMERGED_MAIN = "unmerged_main"
    UNRESOLVED_DEPENDENCY = "unresolved_dependency"
    UNSUPPORTED_ROLE = "unsupported_role"
    UNSUPPORTED_STATUS = "unsupported_status"


@dataclass(frozen=True)
class RolePickupProfile:
    """Configured Jira pickup policy for one role in one project."""

    role: AgentRole
    project_key: str
    eligible_statuses: tuple[str, ...]
    issue_types: tuple[str, ...]
    gates: tuple[PickupGateKind, ...]
    required_artifacts: tuple[PickupArtifactKind, ...] = ()
    required_labels: tuple[str, ...] = ()
    excluded_labels: tuple[str, ...] = ()
    jql_labels: tuple[str, ...] = ()
    active_sprint_required: bool = True
    result_event: str = "assignment_ready"
    handoff_target_role: AgentRole | None = None
    description: str = ""


@dataclass(frozen=True)
class PickupCandidate:
    """Jira issue snapshot evaluated against a role pickup profile."""

    issue_key: str
    project_key: str
    issue_type: str
    status: str
    labels: tuple[str, ...] = ()
    sprint_names: tuple[str, ...] = ()
    dependency_passed: bool = True
    dependency_graph_passed: bool = True
    assignment_locked: bool = False
    codex_limit_allowed: bool = True
    definition_ready: bool = True
    blocking_bug_keys: tuple[str, ...] = ()
    review_change_requested: bool = False
    linked_testing_bug_keys: tuple[str, ...] = ()
    pr_url: str = ""
    pr_branch: str = ""
    pr_head_sha: str = ""
    pr_open: bool = True
    pr_metadata_current: bool = True
    development_evidence_path: str = ""
    ci_state: str = ""
    mergeable_state: str = ""
    merged_sha: str = ""
    test_request_recorded: bool = False
    acceptance_criteria_available: bool = False
    regression_manifest_ready: bool = False
    sprint_delivery_ready: bool = False
    retro_ready: bool = False
    publication_target_enabled: bool = False
    evidence_path: str = ""
    design_reference_accepted: bool = False
    security_scope_defined: bool = False
    secret_exposure_detected: bool = False
    explicit_retest: bool = False


@dataclass(frozen=True)
class PickupDecision:
    """Decision and trace for a role/candidate evaluation."""

    role: AgentRole
    issue_key: str
    decision: PickupDecisionKind
    reasons: tuple[PickupSkipReason, ...]
    status: str
    project_key: str
    message: str


@dataclass(frozen=True)
class JiraPickupSearchPlan:
    """Concrete Jira search request generated from a pickup profile."""

    role: AgentRole
    project_key: str
    jql: str
    statuses: tuple[str, ...]
    issue_types: tuple[str, ...]
    labels: tuple[str, ...]
    active_sprint_name: str = ""


def default_role_pickup_profiles(project_key: str = "AGENT") -> tuple[RolePickupProfile, ...]:
    """Return default Release 1.2 role pickup profiles for one Jira project."""

    project = project_key.strip().upper()
    delivery_types = ("Story", "Bug", "Task")
    planning_types = ("Epic", "Story", "Bug", "Task")
    test_types = ("Story", "Bug", "Task", "Test")

    developer_gates = (
        PickupGateKind.ACTIVE_SPRINT,
        PickupGateKind.DEPENDENCY_GRAPH_CLEAR,
        PickupGateKind.DEPENDENCIES_CLEAR,
        PickupGateKind.ASSIGNMENT_UNLOCKED,
        PickupGateKind.CODEX_LIMIT_AVAILABLE,
        PickupGateKind.DEFINITION_OF_READY,
        PickupGateKind.NO_BLOCKING_BUGS,
        PickupGateKind.REWORK_SIGNAL,
    )
    return (
        RolePickupProfile(
            role=AgentRole.PRODUCT_PLANNING,
            project_key=project,
            eligible_statuses=(FUNNEL, READY_TO_START),
            issue_types=planning_types,
            gates=(
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.ASSIGNMENT_UNLOCKED,
            ),
            active_sprint_required=False,
            result_event="backlog_or_context_update_ready",
            handoff_target_role=AgentRole.ARCHITECTURE,
            description="Creates and updates stories, dependencies, sprint candidates, and context packs from approved product input.",
        ),
        RolePickupProfile(
            role=AgentRole.ARCHITECTURE,
            project_key=project,
            eligible_statuses=(FUNNEL, READY_TO_START),
            issue_types=planning_types,
            gates=(
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.ASSIGNMENT_UNLOCKED,
                PickupGateKind.NO_SECRET_EXPOSURE,
            ),
            active_sprint_required=False,
            result_event="architecture_context_ready",
            handoff_target_role=AgentRole.PRODUCT_PLANNING,
            description="Prepares architecture decisions, NFRs, dependencies, and implementation guidance.",
        ),
        RolePickupProfile(
            role=AgentRole.UI_UX,
            project_key=project,
            eligible_statuses=(READY_TO_START,),
            issue_types=("Story", "Task"),
            gates=(
                PickupGateKind.ACTIVE_SPRINT,
                PickupGateKind.ASSIGNMENT_UNLOCKED,
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.NO_SECRET_EXPOSURE,
            ),
            result_event="design_assignment_ready",
            handoff_target_role=AgentRole.FRONTEND,
            description="Creates reviewable design artifacts that must be accepted before frontend implementation starts.",
        ),
        RolePickupProfile(
            role=AgentRole.DEVELOPER,
            project_key=project,
            eligible_statuses=(READY_TO_START, DEV_COMPLETED),
            issue_types=delivery_types,
            gates=developer_gates,
            result_event="development_assignment_ready",
            handoff_target_role=AgentRole.REVIEW,
            description="Implements ready delivery issues and narrowly scoped review/test rework.",
        ),
        RolePickupProfile(
            role=AgentRole.FRONTEND,
            project_key=project,
            eligible_statuses=(READY_TO_START, DEV_COMPLETED),
            issue_types=delivery_types,
            gates=developer_gates + (PickupGateKind.DESIGN_ACCEPTED,),
            required_artifacts=(PickupArtifactKind.DESIGN_REFERENCE,),
            result_event="frontend_assignment_ready",
            handoff_target_role=AgentRole.REVIEW,
            description="Implements UI stories only after accepted design evidence is linked.",
        ),
        RolePickupProfile(
            role=AgentRole.REVIEW,
            project_key=project,
            eligible_statuses=(DEV_COMPLETED,),
            issue_types=delivery_types,
            gates=(
                PickupGateKind.ACTIVE_SPRINT,
                PickupGateKind.ASSIGNMENT_UNLOCKED,
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.PR_HANDOFF_COMPLETE,
                PickupGateKind.CI_SUCCESS,
                PickupGateKind.MERGEABILITY_CLEAN,
            ),
            required_artifacts=(
                PickupArtifactKind.PR_URL,
                PickupArtifactKind.PR_BRANCH,
                PickupArtifactKind.PR_HEAD_SHA,
                PickupArtifactKind.DEVELOPMENT_EVIDENCE,
            ),
            result_event="review_assignment_ready",
            handoff_target_role=AgentRole.TESTER,
            description="Reviews diff-first PRs only when the PR handoff and CI state are available.",
        ),
        RolePickupProfile(
            role=AgentRole.TESTER,
            project_key=project,
            eligible_statuses=(DEV_COMPLETED, TEST_COMPLETED),
            issue_types=test_types,
            gates=(
                PickupGateKind.ACTIVE_SPRINT,
                PickupGateKind.ASSIGNMENT_UNLOCKED,
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.MERGED_TO_MAIN,
                PickupGateKind.TEST_REQUEST_RECORDED,
                PickupGateKind.EVIDENCE_AVAILABLE,
            ),
            required_artifacts=(
                PickupArtifactKind.MERGE_SHA,
                PickupArtifactKind.TEST_REQUEST,
                PickupArtifactKind.DEVELOPMENT_EVIDENCE,
                PickupArtifactKind.ACCEPTANCE_CRITERIA,
            ),
            result_event="testing_assignment_ready",
            handoff_target_role=AgentRole.RELEASE_MANAGER,
            description="Tests merged work on main and handles explicit regression or retest requests.",
        ),
        RolePickupProfile(
            role=AgentRole.RELEASE_MANAGER,
            project_key=project,
            eligible_statuses=(READY_TO_START, TEST_COMPLETED),
            issue_types=test_types,
            gates=(
                PickupGateKind.ACTIVE_SPRINT,
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.SPRINT_DELIVERY_READY,
                PickupGateKind.NO_BLOCKING_BUGS,
                PickupGateKind.REGRESSION_MANIFEST_READY,
            ),
            required_artifacts=(PickupArtifactKind.REGRESSION_MANIFEST,),
            result_event="release_manager_assignment_ready",
            description="Runs regression, retro, and closure only after sprint delivery is tested and unblocked.",
        ),
        RolePickupProfile(
            role=AgentRole.DOCS_CONFLUENCE,
            project_key=project,
            eligible_statuses=(READY_TO_START,),
            issue_types=("Story", "Task"),
            gates=(
                PickupGateKind.ACTIVE_SPRINT,
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.PUBLICATION_TARGET_ENABLED,
                PickupGateKind.EVIDENCE_AVAILABLE,
            ),
            required_artifacts=(PickupArtifactKind.PUBLICATION_TARGET,),
            result_event="documentation_publication_ready",
            description="Publishes approved evidence and docs to the configured human-readable documentation target.",
        ),
        RolePickupProfile(
            role=AgentRole.SECURITY,
            project_key=project,
            eligible_statuses=(READY_TO_START, DEV_COMPLETED),
            issue_types=delivery_types,
            gates=(
                PickupGateKind.ACTIVE_SPRINT,
                PickupGateKind.CODEX_LIMIT_AVAILABLE,
                PickupGateKind.SECURITY_SCOPE_DEFINED,
                PickupGateKind.NO_SECRET_EXPOSURE,
            ),
            required_artifacts=(PickupArtifactKind.SECURITY_SCOPE,),
            result_event="security_assignment_ready",
            description="Runs scoped threat modeling or routine security review when explicitly requested.",
        ),
    )


def profile_for_role(role: AgentRole, project_key: str = "AGENT") -> RolePickupProfile:
    """Return the default profile for one role and project."""

    for profile in default_role_pickup_profiles(project_key):
        if profile.role == role:
            return profile
    raise ValueError(f"Unsupported pickup profile role: {role.value}")


def with_required_labels(profile: RolePickupProfile, *labels: str) -> RolePickupProfile:
    """Return a profile variant that requires project-specific labels."""

    normalized = tuple(label.strip() for label in labels if label.strip())
    return replace(profile, required_labels=normalized, jql_labels=normalized)


def build_role_pickup_jql(
    profile: RolePickupProfile,
    *,
    active_sprint_name: str = "",
    extra_labels: tuple[str, ...] = (),
) -> str:
    """Build the Jira JQL a scheduler should use for a role profile."""

    clauses = [f'project = "{_escape_jql(profile.project_key)}"']
    clauses.append(f"status in ({_jql_list(profile.eligible_statuses)})")
    clauses.append(f"issuetype in ({_jql_list(profile.issue_types)})")

    labels = tuple(dict.fromkeys(profile.jql_labels + extra_labels))
    if labels:
        clauses.append(f"labels in ({_jql_list(labels)})")
    if profile.excluded_labels:
        clauses.append(f"(labels not in ({_jql_list(profile.excluded_labels)}) OR labels is EMPTY)")
    if active_sprint_name:
        clauses.append(f'sprint = "{_escape_jql(active_sprint_name)}"')
    elif profile.active_sprint_required:
        clauses.append("sprint in openSprints()")

    return " AND ".join(clauses) + " ORDER BY priority DESC, updated ASC"


def build_pickup_search_plan(
    profile: RolePickupProfile,
    *,
    active_sprint_name: str = "",
    extra_labels: tuple[str, ...] = (),
) -> JiraPickupSearchPlan:
    """Create a traceable Jira search plan from a role profile."""

    labels = tuple(dict.fromkeys(profile.jql_labels + extra_labels))
    return JiraPickupSearchPlan(
        role=profile.role,
        project_key=profile.project_key,
        jql=build_role_pickup_jql(profile, active_sprint_name=active_sprint_name, extra_labels=extra_labels),
        statuses=profile.eligible_statuses,
        issue_types=profile.issue_types,
        labels=labels,
        active_sprint_name=active_sprint_name,
    )


def evaluate_role_pickup_candidate(
    profile: RolePickupProfile,
    candidate: PickupCandidate,
    *,
    active_sprint_name: str = "",
) -> PickupDecision:
    """Explain whether one Jira candidate is eligible for a role worker."""

    reasons: list[PickupSkipReason] = []
    skip_reasons: set[PickupSkipReason] = set()

    if candidate.project_key.strip().upper() != profile.project_key.strip().upper():
        _add_reason(reasons, skip_reasons, PickupSkipReason.PROJECT_MISMATCH, skip=True)
    if not _contains_normalized(profile.eligible_statuses, candidate.status):
        _add_reason(reasons, skip_reasons, PickupSkipReason.UNSUPPORTED_STATUS, skip=True)
    if not _contains_normalized(profile.issue_types, candidate.issue_type):
        _add_reason(reasons, skip_reasons, PickupSkipReason.EXCLUDED_ISSUE_TYPE, skip=True)
    if profile.active_sprint_required and not _candidate_in_active_sprint(candidate, active_sprint_name):
        _add_reason(reasons, skip_reasons, PickupSkipReason.FUTURE_SPRINT, skip=True)

    labels = {_normalize_label(label) for label in candidate.labels}
    for label in profile.required_labels:
        if _normalize_label(label) not in labels:
            _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_REQUIRED_LABEL, skip=True)
    for label in profile.excluded_labels:
        if _normalize_label(label) in labels:
            _add_reason(reasons, skip_reasons, PickupSkipReason.EXCLUDED_LABEL, skip=True)
    if _tester_needs_explicit_retest(profile, candidate):
        _add_reason(reasons, skip_reasons, PickupSkipReason.EXPLICIT_RETEST_NOT_REQUESTED, skip=True)

    if reasons and all(reason in skip_reasons for reason in reasons):
        return _pickup_decision(profile, candidate, PickupDecisionKind.SKIP, reasons)

    if PickupGateKind.DEPENDENCY_GRAPH_CLEAR in profile.gates and not candidate.dependency_graph_passed:
        _add_reason(reasons, skip_reasons, PickupSkipReason.DEPENDENCY_GRAPH_BLOCKED)
    if PickupGateKind.DEPENDENCIES_CLEAR in profile.gates and not candidate.dependency_passed:
        _add_reason(reasons, skip_reasons, PickupSkipReason.UNRESOLVED_DEPENDENCY)
    if PickupGateKind.ASSIGNMENT_UNLOCKED in profile.gates and candidate.assignment_locked:
        _add_reason(reasons, skip_reasons, PickupSkipReason.ACTIVE_LOCK)
    if PickupGateKind.CODEX_LIMIT_AVAILABLE in profile.gates and not candidate.codex_limit_allowed:
        _add_reason(reasons, skip_reasons, PickupSkipReason.CODEX_LIMIT_BLOCKED)
    if PickupGateKind.DEFINITION_OF_READY in profile.gates and not candidate.definition_ready:
        _add_reason(reasons, skip_reasons, PickupSkipReason.DOR_FAILED)
    if PickupGateKind.NO_BLOCKING_BUGS in profile.gates and _blocking_bugs_block_candidate(profile, candidate):
        _add_reason(reasons, skip_reasons, PickupSkipReason.BLOCKING_BUG)
    if PickupGateKind.REWORK_SIGNAL in profile.gates and _requires_rework_signal(profile, candidate):
        _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_REWORK_SIGNAL)
    if PickupGateKind.DESIGN_ACCEPTED in profile.gates and not candidate.design_reference_accepted:
        _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_DESIGN_REFERENCE)
    if PickupGateKind.PR_HANDOFF_COMPLETE in profile.gates:
        _require_artifact(candidate.pr_url, reasons, skip_reasons)
        _require_artifact(candidate.pr_branch, reasons, skip_reasons)
        _require_artifact(candidate.pr_head_sha, reasons, skip_reasons)
        _require_artifact(candidate.development_evidence_path, reasons, skip_reasons)
        if not candidate.pr_open:
            _add_reason(reasons, skip_reasons, PickupSkipReason.PR_NOT_OPEN)
        if not candidate.pr_metadata_current:
            _add_reason(reasons, skip_reasons, PickupSkipReason.STALE_PR_METADATA)
    if PickupGateKind.CI_SUCCESS in profile.gates and _normalize_state(candidate.ci_state) not in {"success", "passed"}:
        _add_reason(reasons, skip_reasons, PickupSkipReason.CI_NOT_SUCCESS)
    if PickupGateKind.MERGEABILITY_CLEAN in profile.gates and _normalize_state(candidate.mergeable_state) not in {"clean", "mergeable"}:
        _add_reason(reasons, skip_reasons, PickupSkipReason.DIRTY_MERGEABILITY)
    if PickupGateKind.MERGED_TO_MAIN in profile.gates and not candidate.merged_sha.strip():
        _add_reason(reasons, skip_reasons, PickupSkipReason.UNMERGED_MAIN)
    if PickupGateKind.TEST_REQUEST_RECORDED in profile.gates and not candidate.test_request_recorded:
        _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_TEST_REQUEST)
    if PickupGateKind.EVIDENCE_AVAILABLE in profile.gates and not _has_evidence(candidate):
        _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_ARTIFACT)
    if PickupGateKind.REGRESSION_MANIFEST_READY in profile.gates and not candidate.regression_manifest_ready:
        _add_reason(reasons, skip_reasons, PickupSkipReason.REGRESSION_MANIFEST_MISSING)
    if PickupGateKind.SPRINT_DELIVERY_READY in profile.gates and not candidate.sprint_delivery_ready:
        _add_reason(reasons, skip_reasons, PickupSkipReason.SPRINT_DELIVERY_NOT_READY)
    if PickupGateKind.RETRO_READY in profile.gates and not candidate.retro_ready:
        _add_reason(reasons, skip_reasons, PickupSkipReason.RETRO_NOT_READY)
    if PickupGateKind.PUBLICATION_TARGET_ENABLED in profile.gates and not candidate.publication_target_enabled:
        _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_PUBLICATION_TARGET)
    if PickupGateKind.SECURITY_SCOPE_DEFINED in profile.gates and not candidate.security_scope_defined:
        _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_SECURITY_SCOPE)
    if PickupGateKind.NO_SECRET_EXPOSURE in profile.gates and candidate.secret_exposure_detected:
        _add_reason(reasons, skip_reasons, PickupSkipReason.SECRET_EXPOSURE)

    _evaluate_required_artifacts(profile, candidate, reasons, skip_reasons)

    if not reasons:
        return _pickup_decision(profile, candidate, PickupDecisionKind.PICK, reasons)
    if all(reason in skip_reasons for reason in reasons):
        return _pickup_decision(profile, candidate, PickupDecisionKind.SKIP, reasons)
    return _pickup_decision(profile, candidate, PickupDecisionKind.BLOCKED, reasons)


def render_pickup_decision_log(decision: PickupDecision) -> str:
    """Render a durable assignment decision log line."""

    reasons = ",".join(reason.value for reason in decision.reasons) or "none"
    return (
        f"role={decision.role.value} issue={decision.issue_key} project={decision.project_key} "
        f"status={decision.status} decision={decision.decision.value} reasons={reasons}"
    )


def _pickup_decision(
    profile: RolePickupProfile,
    candidate: PickupCandidate,
    decision: PickupDecisionKind,
    reasons: list[PickupSkipReason],
) -> PickupDecision:
    if decision is PickupDecisionKind.PICK:
        message = f"{profile.role.value} can pick {candidate.issue_key}."
    elif decision is PickupDecisionKind.SKIP:
        message = f"{profile.role.value} skipped {candidate.issue_key}: {_reason_text(reasons)}."
    else:
        message = f"{profile.role.value} blocked on {candidate.issue_key}: {_reason_text(reasons)}."
    return PickupDecision(
        role=profile.role,
        issue_key=candidate.issue_key,
        decision=decision,
        reasons=tuple(reasons),
        status=candidate.status,
        project_key=candidate.project_key,
        message=message,
    )


def _evaluate_required_artifacts(
    profile: RolePickupProfile,
    candidate: PickupCandidate,
    reasons: list[PickupSkipReason],
    skip_reasons: set[PickupSkipReason],
) -> None:
    artifact_values = {
        PickupArtifactKind.ACCEPTANCE_CRITERIA: candidate.acceptance_criteria_available,
        PickupArtifactKind.DEVELOPMENT_EVIDENCE: bool(candidate.development_evidence_path.strip()),
        PickupArtifactKind.DESIGN_REFERENCE: candidate.design_reference_accepted,
        PickupArtifactKind.MERGE_SHA: bool(candidate.merged_sha.strip()),
        PickupArtifactKind.PR_BRANCH: bool(candidate.pr_branch.strip()),
        PickupArtifactKind.PR_HEAD_SHA: bool(candidate.pr_head_sha.strip()),
        PickupArtifactKind.PR_URL: bool(candidate.pr_url.strip()),
        PickupArtifactKind.PUBLICATION_TARGET: candidate.publication_target_enabled,
        PickupArtifactKind.REGRESSION_MANIFEST: candidate.regression_manifest_ready,
        PickupArtifactKind.SECURITY_SCOPE: candidate.security_scope_defined,
        PickupArtifactKind.TEST_REQUEST: candidate.test_request_recorded,
    }
    for artifact in profile.required_artifacts:
        if artifact_values.get(artifact, False):
            continue
        if artifact is PickupArtifactKind.ACCEPTANCE_CRITERIA:
            _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_ACCEPTANCE_CRITERIA)
        elif artifact is PickupArtifactKind.DESIGN_REFERENCE:
            _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_DESIGN_REFERENCE)
        elif artifact is PickupArtifactKind.PUBLICATION_TARGET:
            _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_PUBLICATION_TARGET)
        elif artifact is PickupArtifactKind.SECURITY_SCOPE:
            _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_SECURITY_SCOPE)
        elif artifact is PickupArtifactKind.TEST_REQUEST:
            _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_TEST_REQUEST)
        elif artifact is PickupArtifactKind.MERGE_SHA:
            _add_reason(reasons, skip_reasons, PickupSkipReason.UNMERGED_MAIN)
        elif artifact is PickupArtifactKind.REGRESSION_MANIFEST:
            _add_reason(reasons, skip_reasons, PickupSkipReason.REGRESSION_MANIFEST_MISSING)
        else:
            _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_ARTIFACT)


def _blocking_bugs_block_candidate(profile: RolePickupProfile, candidate: PickupCandidate) -> bool:
    if not candidate.blocking_bug_keys:
        return False
    if profile.role in {AgentRole.DEVELOPER, AgentRole.FRONTEND} and candidate.linked_testing_bug_keys:
        return False
    return True


def _requires_rework_signal(profile: RolePickupProfile, candidate: PickupCandidate) -> bool:
    if profile.role not in {AgentRole.DEVELOPER, AgentRole.FRONTEND}:
        return False
    if not _status_matches(candidate.status, DEV_COMPLETED):
        return False
    return not (candidate.review_change_requested or candidate.linked_testing_bug_keys)


def _tester_needs_explicit_retest(profile: RolePickupProfile, candidate: PickupCandidate) -> bool:
    if profile.role is not AgentRole.TESTER:
        return False
    if not _status_matches(candidate.status, TEST_COMPLETED):
        return False
    return not candidate.explicit_retest


def _candidate_in_active_sprint(candidate: PickupCandidate, active_sprint_name: str) -> bool:
    if active_sprint_name:
        return _contains_normalized(candidate.sprint_names, active_sprint_name)
    return bool(candidate.sprint_names)


def _has_evidence(candidate: PickupCandidate) -> bool:
    return bool(candidate.evidence_path.strip() or candidate.development_evidence_path.strip())


def _require_artifact(
    value: str,
    reasons: list[PickupSkipReason],
    skip_reasons: set[PickupSkipReason],
) -> None:
    if not value.strip():
        _add_reason(reasons, skip_reasons, PickupSkipReason.MISSING_ARTIFACT)


def _add_reason(
    reasons: list[PickupSkipReason],
    skip_reasons: set[PickupSkipReason],
    reason: PickupSkipReason,
    *,
    skip: bool = False,
) -> None:
    if reason not in reasons:
        reasons.append(reason)
    if skip:
        skip_reasons.add(reason)


def _contains_normalized(values: tuple[str, ...], target: str) -> bool:
    normalized_target = _normalize_text(target)
    return any(_normalize_text(value) == normalized_target for value in values)


def _status_matches(status: str, expected: str) -> bool:
    return _normalize_text(status) == _normalize_text(expected)


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().casefold().replace("/", " ").split())


def _normalize_label(value: str) -> str:
    return value.strip().casefold()


def _normalize_state(value: str) -> str:
    return value.strip().casefold().replace("_", "-").replace(" ", "-")


def _jql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f'"{_escape_jql(value)}"' for value in values)


def _escape_jql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _reason_text(reasons: tuple[PickupSkipReason, ...] | list[PickupSkipReason]) -> str:
    return ", ".join(reason.value for reason in reasons)
