from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ContextBranchClass(str, Enum):
    """Known branch classes used by agentic workers."""

    DELIVERY = "delivery"
    CONTEXT = "context"
    DOCS = "docs"
    PROCESS = "process"
    UNKNOWN = "unknown"


class ContextPackValidationIssueKind(str, Enum):
    """Validation failures that block context pack assignment."""

    INVALID_BRANCH = "invalid_branch"
    PROJECT_MISMATCH = "project_mismatch"
    ROLE_MISMATCH = "role_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    MISSING_REVISION = "missing_revision"
    MISSING_BASELINE_REVISION = "missing_baseline_revision"
    MISSING_CONTEXT_HASH = "missing_context_hash"
    MISSING_SOURCE_DOCUMENT = "missing_source_document"
    SECRET_LIKE_CONTENT = "secret_like_content"
    UNRESOLVED_ASSUMPTION = "unresolved_assumption"
    STALE_CONTEXT = "stale_context"
    CROSS_PROJECT_MEMORY = "cross_project_memory"


@dataclass(frozen=True)
class ContextBranchPolicy:
    """Classification and Jira-visibility decision for one branch name."""

    branch_name: str
    branch_class: ContextBranchClass
    jira_delivery_visible: bool
    requires_jira_issue: bool
    context_project_key: str = ""
    context_agent_role: str = ""
    context_scope: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ContextSourceDocument:
    """One approved source document included in a context pack."""

    path: str
    description: str = ""
    required: bool = True
    revision: str = ""
    project_key: str = ""


@dataclass(frozen=True)
class ContextPackReference:
    """Published context pack artifact reference passed to workers."""

    project_key: str
    agent_role: str
    sprint_or_story: str
    branch_name: str
    revision: str
    context_pack_hash: str
    source_documents: tuple[ContextSourceDocument, ...]
    generated_from_main_sha: str
    unresolved_assumptions: tuple[str, ...] = ()
    memory_project_key: str = ""


@dataclass(frozen=True)
class ContextPackValidationIssue:
    """One context pack reference validation failure."""

    kind: ContextPackValidationIssueKind
    field: str
    message: str


@dataclass(frozen=True)
class ContextPackValidationResult:
    """Context pack reference validation result."""

    allowed: bool
    branch_policy: ContextBranchPolicy
    issues: tuple[ContextPackValidationIssue, ...]


_FEATURE_RE = re.compile(r"^feature/[A-Z][A-Z0-9]+-\d+-[a-z0-9][a-z0-9-]*$")
_CONTEXT_RE = re.compile(
    r"^context/(?P<project>[A-Z][A-Z0-9]*)/(?P<role>[a-z][a-z0-9_-]*)/(?P<scope>[A-Za-z0-9._-]+)$"
)
_DOCS_RE = re.compile(r"^docs/[A-Za-z0-9._-]+$")
_PROCESS_RE = re.compile(r"^process/[A-Z][A-Z0-9]+-\d+-[a-z0-9][a-z0-9-]*$")
_REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|secret|password|api[_-]?key|client[_-]?secret|private[_-]?key)\b\s*[:=]\s*([^\s,;]+)"
)
_TOKEN_VALUE_RE = re.compile(r"\b(?:ghp|github_pat|sk|xox[baprs])[-_][-A-Za-z0-9_]{12,}\b")


SECRET_REDACTION = "<redacted>"


def classify_context_branch(branch_name: str) -> ContextBranchPolicy:
    """Classify a branch name and decide whether it should appear as delivery work in Jira."""

    normalized = branch_name.strip()
    if _FEATURE_RE.match(normalized):
        return ContextBranchPolicy(
            branch_name=normalized,
            branch_class=ContextBranchClass.DELIVERY,
            jira_delivery_visible=True,
            requires_jira_issue=True,
            reason="feature branches are delivery branches linked to one Jira issue",
        )
    if match := _CONTEXT_RE.match(normalized):
        return ContextBranchPolicy(
            branch_name=normalized,
            branch_class=ContextBranchClass.CONTEXT,
            jira_delivery_visible=False,
            requires_jira_issue=False,
            context_project_key=match.group("project"),
            context_agent_role=match.group("role"),
            context_scope=match.group("scope"),
            reason="context branches publish non-delivery context pack artifacts",
        )
    if _DOCS_RE.match(normalized):
        return ContextBranchPolicy(
            branch_name=normalized,
            branch_class=ContextBranchClass.DOCS,
            jira_delivery_visible=False,
            requires_jira_issue=False,
            reason="docs branches publish documentation artifacts and are not story delivery PRs by default",
        )
    if _PROCESS_RE.match(normalized):
        return ContextBranchPolicy(
            branch_name=normalized,
            branch_class=ContextBranchClass.PROCESS,
            jira_delivery_visible=True,
            requires_jira_issue=True,
            reason="process branches are delivery-visible only when a Jira issue tracks the process change",
        )
    return ContextBranchPolicy(
        branch_name=normalized,
        branch_class=ContextBranchClass.UNKNOWN,
        jira_delivery_visible=False,
        requires_jira_issue=False,
        reason="branch name does not match a supported agentic branch class",
    )


def context_branch_name(project_key: str, agent_role: str, sprint_or_story: str) -> str:
    """Build the deterministic non-delivery context branch name."""

    return f"context/{project_key.strip().upper()}/{_normalize_role(agent_role)}/{_normalize_scope(sprint_or_story)}"


def is_delivery_visible_in_jira(branch_name: str) -> bool:
    """Return whether a branch should be treated as a Jira story delivery PR by default."""

    return classify_context_branch(branch_name).jira_delivery_visible


def validate_context_pack_reference(
    reference: ContextPackReference,
    *,
    current_main_sha: str | None = None,
) -> ContextPackValidationResult:
    """Validate that a context pack ref is safe to fetch into an isolated worker workspace."""

    policy = classify_context_branch(reference.branch_name)
    issues: list[ContextPackValidationIssue] = []

    if policy.branch_class is not ContextBranchClass.CONTEXT:
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.INVALID_BRANCH,
                "branch_name",
                "Context pack refs must use context/{PROJECT_KEY}/{agent-role}/{sprint-or-story} branches.",
            )
        )
    if policy.context_project_key and policy.context_project_key != reference.project_key.upper():
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.PROJECT_MISMATCH,
                "project_key",
                "Context branch project key does not match the assignment project key.",
            )
        )
    if policy.context_agent_role and policy.context_agent_role != _normalize_role(reference.agent_role):
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.ROLE_MISMATCH,
                "agent_role",
                "Context branch role does not match the assignment role.",
            )
        )
    if policy.context_scope and policy.context_scope != _normalize_scope(reference.sprint_or_story):
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.SCOPE_MISMATCH,
                "sprint_or_story",
                "Context branch sprint/story scope does not match the assignment scope.",
            )
        )
    if not _is_revision(reference.revision):
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.MISSING_REVISION,
                "revision",
                "Context pack ref must include a 7-40 character lowercase git revision hash.",
            )
        )
    if not _is_revision(reference.generated_from_main_sha):
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.MISSING_BASELINE_REVISION,
                "generated_from_main_sha",
                "Context pack ref must include the main revision used as the generation baseline.",
            )
        )
    elif current_main_sha and reference.generated_from_main_sha != current_main_sha:
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.STALE_CONTEXT,
                "generated_from_main_sha",
                "Context pack was generated from a different main revision than the current assignment baseline.",
            )
        )
    if not reference.context_pack_hash.strip():
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.MISSING_CONTEXT_HASH,
                "context_pack_hash",
                "Context pack ref must include the generated context artifact hash.",
            )
        )
    if not reference.source_documents:
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.MISSING_SOURCE_DOCUMENT,
                "source_documents",
                "Context packs must list at least one approved source document.",
            )
        )
    for index, document in enumerate(reference.source_documents):
        _validate_source_document(reference.project_key, index, document, issues)
    for index, assumption in enumerate(reference.unresolved_assumptions):
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.UNRESOLVED_ASSUMPTION,
                f"unresolved_assumptions[{index}]",
                "Context packs must not publish unresolved assumptions as executable context.",
            )
        )
        _append_secret_issue_if_needed(f"unresolved_assumptions[{index}]", assumption, issues)
    if reference.memory_project_key and reference.memory_project_key.upper() != reference.project_key.upper():
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.CROSS_PROJECT_MEMORY,
                "memory_project_key",
                "Context pack references memory from a different project.",
            )
        )
    return ContextPackValidationResult(
        allowed=not issues,
        branch_policy=policy,
        issues=tuple(issues),
    )


def redact_context_pack_text(text: str) -> str:
    """Redact obvious credential-like values before context material is stored or logged."""

    redacted = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={SECRET_REDACTION}", text)
    return _TOKEN_VALUE_RE.sub(SECRET_REDACTION, redacted)


def contains_secret_like_text(text: str) -> bool:
    """Return true when text contains values that should not be in a context pack."""

    return redact_context_pack_text(text) != text


def render_context_pack_artifact_note(reference: ContextPackReference) -> str:
    """Render a non-delivery context artifact reference for Jira comments or assignment logs."""

    source_lines = [f"- {doc.path}" for doc in reference.source_documents] or ["- None"]
    return "\n".join(
        [
            "# Context Pack Artifact",
            "",
            f"- Project: {reference.project_key}",
            f"- Role: {reference.agent_role}",
            f"- Scope: {reference.sprint_or_story}",
            f"- Branch: {reference.branch_name}",
            f"- Revision: {reference.revision}",
            f"- Context hash: {reference.context_pack_hash}",
            "",
            "## Source Documents",
            *source_lines,
        ]
    ) + "\n"


def _validate_source_document(
    project_key: str,
    index: int,
    document: ContextSourceDocument,
    issues: list[ContextPackValidationIssue],
) -> None:
    field = f"source_documents[{index}]"
    if document.required and not document.path.strip():
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.MISSING_SOURCE_DOCUMENT,
                f"{field}.path",
                "Required source document entries must include a path.",
            )
        )
    if document.project_key and document.project_key.upper() != project_key.upper():
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.CROSS_PROJECT_MEMORY,
                f"{field}.project_key",
                "Source document belongs to a different project.",
            )
        )
    _append_secret_issue_if_needed(f"{field}.path", document.path, issues)
    _append_secret_issue_if_needed(f"{field}.description", document.description, issues)


def _append_secret_issue_if_needed(
    field: str,
    value: str,
    issues: list[ContextPackValidationIssue],
) -> None:
    if contains_secret_like_text(value):
        issues.append(
            ContextPackValidationIssue(
                ContextPackValidationIssueKind.SECRET_LIKE_CONTENT,
                field,
                "Context pack material contains credential-like content and must be redacted or removed.",
            )
        )


def _is_revision(value: str) -> bool:
    return bool(_REVISION_RE.match(value.strip()))


def _normalize_role(role: str) -> str:
    return role.strip().lower().replace("_", "-")


def _normalize_scope(scope: str) -> str:
    normalized = scope.strip().lower().replace("_", "-").replace(" ", "-")
    return re.sub(r"[^a-z0-9._-]+", "-", normalized).strip("-")
