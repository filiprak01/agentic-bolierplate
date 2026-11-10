"""Documentation-to-backlog traceability audit contracts."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agentic_boilerplate.domain.po_inbox import (
    AgentRole,
    InboxMessageType,
    InboxOption,
    InboxStatus,
    POInboxItem,
    require_valid_inbox_item,
)


class DocumentationTraceabilityError(ValueError):
    """Raised when a traceability audit input is incomplete or unsafe."""


class DocumentationCommitmentKind(str, Enum):
    """Kind of actionable documentation commitment extracted from Markdown."""

    ROADMAP_ITEM = "roadmap-item"
    PROCESS_RULE = "process-rule"
    AGENT_RESPONSIBILITY = "agent-responsibility"
    OPERATOR_UI_REQUIREMENT = "operator-ui-requirement"
    INTEGRATION_REQUIREMENT = "integration-requirement"
    IMPROVEMENT_CANDIDATE = "improvement-candidate"
    RELEASE_SCOPE_DECISION = "release-scope-decision"


class DocumentationTraceabilityClassification(str, Enum):
    """Traceability classification for one documentation commitment."""

    COVERED_BY_JIRA = "covered-by-jira"
    COVERED_BY_DOC_ONLY = "covered-by-doc-only"
    DUPLICATE = "duplicate"
    DEFERRED_ROADMAP = "deferred-roadmap"
    REJECTED = "rejected"
    NEEDS_PO_DECISION = "needs-po-decision"
    MISSING_JIRA_REFLECTION = "missing-jira-reflection"


class TraceabilityFollowUpPolicy(str, Enum):
    """How missing implementation-worthy commitments should be routed."""

    DRAFT_BACKLOG_CANDIDATE = "draft-backlog-candidate"
    PO_INBOX_QUESTION = "po-inbox-question"
    REPORT_ONLY = "report-only"


@dataclass(frozen=True)
class DocumentationTraceabilityProject:
    """Project identity carried by every traceability row."""

    project_id: str
    project_name: str
    jira_project_key: str
    docs_roots: tuple[str, ...] = ()
    confluence_mirror_roots: tuple[str, ...] = ()
    confluence_space: str = ""
    release_target: str = ""


@dataclass(frozen=True)
class DocumentationTraceabilityAuditConfig:
    """Traceability audit configuration."""

    report_id: str
    created_at: str
    project: DocumentationTraceabilityProject


@dataclass(frozen=True)
class DocumentationSourceReference:
    """Stable source reference for an extracted commitment."""

    source_type: str
    path: str
    heading: str
    line: int
    anchor: str = ""


@dataclass(frozen=True)
class DocumentationCommitment:
    """One actionable documentation commitment."""

    id: str
    text: str
    normalized_id: str
    content_fingerprint: str
    kind: DocumentationCommitmentKind
    source: DocumentationSourceReference
    implementation_worthy: bool = True


@dataclass(frozen=True)
class DocumentationTraceabilityIssue:
    """Jira-like issue metadata used by the audit without live Jira calls."""

    key: str
    summary: str
    issue_type: str
    status: str
    labels: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class DocumentationBacklogCandidate:
    """Reviewable missing-Jira backlog candidate."""

    id: str
    title: str
    description: str
    source_commitment_id: str
    target_status: str
    project_id: str
    jira_project_key: str
    release_target: str
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentationTraceabilityRow:
    """Traceability result for one commitment."""

    commitment: DocumentationCommitment
    source: DocumentationSourceReference
    classification: DocumentationTraceabilityClassification
    matched_jira_keys: tuple[str, ...] = ()
    match_reasons: tuple[str, ...] = ()
    duplicate_of_commitment_id: str = ""
    project_id: str = ""
    project_name: str = ""
    jira_project_key: str = ""
    docs_root: str = ""
    confluence_space: str = ""
    release_target: str = ""


@dataclass(frozen=True)
class DocumentationTraceabilityReport:
    """Durable documentation-to-backlog traceability report."""

    id: str
    created_at: str
    project: DocumentationTraceabilityProject
    rows: tuple[DocumentationTraceabilityRow, ...]

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(row.classification.value for row in self.rows)
        return {classification.value: counts.get(classification.value, 0) for classification in DocumentationTraceabilityClassification}

    @property
    def has_missing_or_po_needed(self) -> bool:
        return any(
            row.classification
            in {
                DocumentationTraceabilityClassification.MISSING_JIRA_REFLECTION,
                DocumentationTraceabilityClassification.NEEDS_PO_DECISION,
            }
            for row in self.rows
        )


@dataclass(frozen=True)
class TraceabilityFollowUpPlan:
    """Follow-up artifacts for missing documentation traceability."""

    report_id: str
    policy: TraceabilityFollowUpPolicy
    created_at: str
    draft_candidates: tuple[DocumentationBacklogCandidate, ...] = ()
    po_inbox_questions: tuple[POInboxItem, ...] = ()


_ISSUE_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_ACTIONABLE_MARKERS = (
    "must",
    "should",
    "need",
    "needs",
    "required",
    "require",
    "requires",
    "shall",
    "add",
    "implement",
    "create",
    "support",
    "include",
    "keep",
    "replace",
    "roadmap",
    "future",
    "deferred",
    "todo",
    "improvement",
    "decide",
)
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


def audit_documentation_traceability(
    config: DocumentationTraceabilityAuditConfig,
    *,
    jira_issues: Sequence[DocumentationTraceabilityIssue],
) -> DocumentationTraceabilityReport:
    """Audit docs against Jira-like issue metadata."""

    _validate_config(config)
    commitments = extract_documentation_commitments(config.project)
    seen_fingerprints: dict[str, str] = {}
    rows: list[DocumentationTraceabilityRow] = []
    for commitment in commitments:
        duplicate_of = seen_fingerprints.get(commitment.content_fingerprint, "")
        if not duplicate_of:
            seen_fingerprints[commitment.content_fingerprint] = commitment.id
        matched, reasons = match_commitment_to_jira(commitment, jira_issues)
        classification = classify_commitment(commitment, matched, duplicate_of=duplicate_of)
        rows.append(
            DocumentationTraceabilityRow(
                commitment=commitment,
                source=commitment.source,
                classification=classification,
                matched_jira_keys=tuple(issue.key for issue in matched),
                match_reasons=tuple(reasons),
                duplicate_of_commitment_id=duplicate_of,
                project_id=config.project.project_id,
                project_name=config.project.project_name,
                jira_project_key=config.project.jira_project_key,
                docs_root=";".join(config.project.docs_roots),
                confluence_space=config.project.confluence_space,
                release_target=config.project.release_target,
            )
        )
    return DocumentationTraceabilityReport(
        id=config.report_id,
        created_at=config.created_at,
        project=config.project,
        rows=tuple(rows),
    )


def extract_documentation_commitments(project: DocumentationTraceabilityProject) -> tuple[DocumentationCommitment, ...]:
    """Extract actionable Markdown commitments from local docs and mirror roots."""

    commitments: list[DocumentationCommitment] = []
    for source_type, roots in (
        ("local_doc", project.docs_roots),
        ("confluence_mirror", project.confluence_mirror_roots),
    ):
        for root in roots:
            commitments.extend(_extract_from_root(Path(root), source_type=source_type, project_id=project.project_id))
    return tuple(commitments)


def match_commitment_to_jira(
    commitment: DocumentationCommitment,
    jira_issues: Sequence[DocumentationTraceabilityIssue],
) -> tuple[tuple[DocumentationTraceabilityIssue, ...], tuple[str, ...]]:
    """Match one commitment to Jira-like issues using explicit and fuzzy metadata."""

    matched: list[DocumentationTraceabilityIssue] = []
    reasons: list[str] = []
    explicit_keys = set(_ISSUE_KEY_RE.findall(commitment.text))
    commitment_tokens = _tokens(commitment.text)
    source_tokens = {
        commitment.normalized_id,
        commitment.content_fingerprint,
        _slug(commitment.source.path),
        _slug(commitment.source.anchor),
    }
    source_line_ref = f"{commitment.source.path}:{commitment.source.line}"

    for issue in jira_issues:
        issue_reasons: list[str] = []
        if issue.key in explicit_keys:
            issue_reasons.append(f"explicit issue key {issue.key}")
        label_tokens = {_normalize_text(label) for label in issue.labels}
        if label_tokens & source_tokens:
            issue_reasons.append("metadata label matched commitment source")
        description = _normalize_text(issue.description)
        if commitment.normalized_id in description or commitment.content_fingerprint in description:
            issue_reasons.append("issue description references commitment id")
        if _normalize_text(source_line_ref) in description:
            issue_reasons.append("issue description references source line")
        if not issue_reasons and _token_overlap(commitment_tokens, _tokens(issue.summary)) >= 0.72:
            issue_reasons.append("summary token overlap")
        if issue_reasons:
            matched.append(issue)
            reasons.extend(f"{issue.key}: {reason}" for reason in issue_reasons)

    return tuple(matched), tuple(reasons)


def classify_commitment(
    commitment: DocumentationCommitment,
    matched_issues: Sequence[DocumentationTraceabilityIssue],
    *,
    duplicate_of: str = "",
) -> DocumentationTraceabilityClassification:
    """Classify one commitment after Jira matching."""

    lowered = commitment.text.casefold()
    if duplicate_of:
        return DocumentationTraceabilityClassification.DUPLICATE
    if _has_marker(lowered, "doc-only"):
        return DocumentationTraceabilityClassification.COVERED_BY_DOC_ONLY
    if _has_marker(lowered, "deferred") or _has_marker(lowered, "future"):
        return DocumentationTraceabilityClassification.DEFERRED_ROADMAP
    if _has_marker(lowered, "rejected"):
        return DocumentationTraceabilityClassification.REJECTED
    if "?" in commitment.text or "decide with po" in lowered or "needs po" in lowered or "tbd" in lowered:
        return DocumentationTraceabilityClassification.NEEDS_PO_DECISION
    if len(matched_issues) > 1:
        return DocumentationTraceabilityClassification.DUPLICATE
    if len(matched_issues) == 1:
        return DocumentationTraceabilityClassification.COVERED_BY_JIRA
    if commitment.implementation_worthy:
        return DocumentationTraceabilityClassification.MISSING_JIRA_REFLECTION
    return DocumentationTraceabilityClassification.COVERED_BY_DOC_ONLY


def build_traceability_follow_up_plan(
    report: DocumentationTraceabilityReport,
    *,
    policy: TraceabilityFollowUpPolicy,
    created_at: str,
    agent_id: str = "documentation-traceability-audit",
) -> TraceabilityFollowUpPlan:
    """Create reviewable follow-up artifacts for missing traceability."""

    _require_text("created_at", created_at)
    missing_rows = tuple(
        row
        for row in report.rows
        if row.classification is DocumentationTraceabilityClassification.MISSING_JIRA_REFLECTION
    )
    candidates: list[DocumentationBacklogCandidate] = []
    questions: list[POInboxItem] = []
    for row in missing_rows:
        if policy is TraceabilityFollowUpPolicy.DRAFT_BACKLOG_CANDIDATE:
            candidates.append(_draft_candidate_for_row(row))
        elif policy is TraceabilityFollowUpPolicy.PO_INBOX_QUESTION:
            questions.append(_po_question_for_row(row, report=report, created_at=created_at, agent_id=agent_id))
    return TraceabilityFollowUpPlan(
        report_id=report.id,
        policy=policy,
        created_at=created_at,
        draft_candidates=tuple(candidates),
        po_inbox_questions=tuple(questions),
    )


def documentation_traceability_report_to_dict(report: DocumentationTraceabilityReport) -> dict[str, Any]:
    """Convert a traceability report into JSON-compatible data."""

    return {
        "id": report.id,
        "created_at": report.created_at,
        "project": _project_to_dict(report.project),
        "summary": report.summary,
        "rows": [_row_to_dict(row) for row in report.rows],
    }


def documentation_traceability_report_from_dict(data: Mapping[str, Any]) -> DocumentationTraceabilityReport:
    """Load a traceability report from JSON-compatible data."""

    project = _project_from_dict(_mapping(data.get("project")))
    return DocumentationTraceabilityReport(
        id=_text(data.get("id")),
        created_at=_text(data.get("created_at")),
        project=project,
        rows=tuple(_row_from_dict(item) for item in _list(data.get("rows"))),
    )


def traceability_follow_up_plan_to_dict(plan: TraceabilityFollowUpPlan) -> dict[str, Any]:
    """Convert follow-up plan into JSON-compatible data."""

    return {
        "report_id": plan.report_id,
        "policy": plan.policy.value,
        "created_at": plan.created_at,
        "draft_candidates": [_candidate_to_dict(candidate) for candidate in plan.draft_candidates],
        "po_inbox_questions": [
            {
                "id": item.id,
                "status": item.status.value,
                "message_type": item.message_type.value,
                "title": item.title,
                "project_id": item.project_id,
                "jira_project_key": item.jira_project_key,
            }
            for item in plan.po_inbox_questions
        ],
    }


def _extract_from_root(root: Path, *, source_type: str, project_id: str) -> tuple[DocumentationCommitment, ...]:
    if not root.exists():
        return ()
    files = (root,) if root.is_file() else tuple(sorted(root.rglob("*.md")))
    commitments: list[DocumentationCommitment] = []
    for path in files:
        commitments.extend(_extract_from_file(path, source_type=source_type, project_id=project_id, root=root))
    return tuple(commitments)


def _extract_from_file(
    path: Path,
    *,
    source_type: str,
    project_id: str,
    root: Path,
) -> tuple[DocumentationCommitment, ...]:
    heading = ""
    in_code_fence = False
    commitments: list[DocumentationCommitment] = []
    relative_path = _relative_source_path(path, root)
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            continue
        text = _clean_markdown_line(stripped)
        if not _is_actionable_text(text):
            continue
        source = DocumentationSourceReference(
            source_type=source_type,
            path=relative_path,
            heading=heading,
            line=line_number,
            anchor=_slug(heading),
        )
        commitments.append(_commitment_from_text(text, source=source, project_id=project_id))
    return tuple(commitments)


def _commitment_from_text(
    text: str,
    *,
    source: DocumentationSourceReference,
    project_id: str,
) -> DocumentationCommitment:
    normalized_text = _normalize_text(text)
    fingerprint = hashlib.sha1(normalized_text.encode("utf-8")).hexdigest()[:12]
    normalized_id = f"doc-{_slug(normalized_text)[:44].strip('-')}-{fingerprint}"
    seed = f"{project_id}:{source.source_type}:{source.path}:{source.line}:{normalized_text}"
    commitment_id = f"{normalized_id}-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:8]}"
    explicit_classification = _explicit_classification(normalized_text)
    implementation_worthy = explicit_classification not in {
        DocumentationTraceabilityClassification.COVERED_BY_DOC_ONLY,
        DocumentationTraceabilityClassification.REJECTED,
    }
    return DocumentationCommitment(
        id=commitment_id,
        text=text,
        normalized_id=normalized_id,
        content_fingerprint=fingerprint,
        kind=_commitment_kind(text),
        source=source,
        implementation_worthy=implementation_worthy,
    )


def _explicit_classification(normalized_text: str) -> DocumentationTraceabilityClassification | None:
    if "doc only" in normalized_text or "doc-only" in normalized_text:
        return DocumentationTraceabilityClassification.COVERED_BY_DOC_ONLY
    if "deferred" in normalized_text or "future" in normalized_text:
        return DocumentationTraceabilityClassification.DEFERRED_ROADMAP
    if "rejected" in normalized_text:
        return DocumentationTraceabilityClassification.REJECTED
    return None


def _draft_candidate_for_row(row: DocumentationTraceabilityRow) -> DocumentationBacklogCandidate:
    labels = (
        "created-from-doc-traceability",
        f"trace-{row.commitment.content_fingerprint}",
        row.release_target or "release-not-recorded",
    )
    source = f"{row.source.path}:{row.source.line}"
    return DocumentationBacklogCandidate(
        id=f"candidate-{row.commitment.content_fingerprint}",
        title=_candidate_title(row.commitment.text),
        description=(
            f"Documentation commitment needs Jira reflection.\n\n"
            f"Source: {source}\n"
            f"Heading: {row.source.heading or 'not recorded'}\n"
            f"Commitment: {row.commitment.text}\n"
            f"Normalized id: {row.commitment.normalized_id}"
        ),
        source_commitment_id=row.commitment.id,
        target_status="FUNNEL",
        project_id=row.project_id,
        jira_project_key=row.jira_project_key,
        release_target=row.release_target,
        labels=labels,
    )


def _po_question_for_row(
    row: DocumentationTraceabilityRow,
    *,
    report: DocumentationTraceabilityReport,
    created_at: str,
    agent_id: str,
) -> POInboxItem:
    source = f"{row.source.path}:{row.source.line}"
    return require_valid_inbox_item(
        POInboxItem(
            id=f"{report.id}-{row.commitment.content_fingerprint}-jira-reflection",
            message_type=InboxMessageType.BLOCKING_QUESTION,
            status=InboxStatus.OPEN,
            title=f"Decide Jira reflection for {row.commitment.content_fingerprint}",
            message=(
                "Should this documentation commitment become a Jira story/task, "
                "remain doc-only, be deferred, or be rejected?\n\n"
                f"Source: {source}\n"
                f"Commitment: {row.commitment.text}"
            ),
            agent_role=AgentRole.PRODUCT_PLANNING,
            created_at=created_at,
            agent_id=agent_id,
            project_id=row.project_id,
            project_name=row.project_name,
            jira_project_key=row.jira_project_key,
            context_pack_path=f"data/documentation-traceability-reports/{report.id}.json",
            business_impact="Implementation-worthy documentation can otherwise remain invisible in Jira.",
            recommendation="Create a FUNNEL backlog candidate unless the Product Owner marks it doc-only, deferred, or rejected.",
            options=(
                InboxOption(id="create_jira", label="Create Jira", description="Create a FUNNEL backlog item."),
                InboxOption(id="doc_only", label="Doc only", description="Keep this as documentation context only."),
                InboxOption(id="defer", label="Defer", description="Move this to a later roadmap decision."),
            ),
        )
    )


def _row_to_dict(row: DocumentationTraceabilityRow) -> dict[str, Any]:
    return {
        "commitment": _commitment_to_dict(row.commitment),
        "source": _source_to_dict(row.source),
        "classification": row.classification.value,
        "matched_jira_keys": list(row.matched_jira_keys),
        "match_reasons": list(row.match_reasons),
        "duplicate_of_commitment_id": row.duplicate_of_commitment_id,
        "project_id": row.project_id,
        "project_name": row.project_name,
        "jira_project_key": row.jira_project_key,
        "docs_root": row.docs_root,
        "confluence_space": row.confluence_space,
        "release_target": row.release_target,
    }


def _row_from_dict(data: Mapping[str, Any]) -> DocumentationTraceabilityRow:
    source = _source_from_dict(_mapping(data.get("source")))
    commitment = _commitment_from_dict(_mapping(data.get("commitment")))
    return DocumentationTraceabilityRow(
        commitment=commitment,
        source=source,
        classification=DocumentationTraceabilityClassification(_text(data.get("classification"))),
        matched_jira_keys=tuple(_text(item) for item in _list(data.get("matched_jira_keys"))),
        match_reasons=tuple(_text(item) for item in _list(data.get("match_reasons"))),
        duplicate_of_commitment_id=_text(data.get("duplicate_of_commitment_id")),
        project_id=_text(data.get("project_id")),
        project_name=_text(data.get("project_name")),
        jira_project_key=_text(data.get("jira_project_key")),
        docs_root=_text(data.get("docs_root")),
        confluence_space=_text(data.get("confluence_space")),
        release_target=_text(data.get("release_target")),
    )


def _commitment_to_dict(commitment: DocumentationCommitment) -> dict[str, Any]:
    return {
        "id": commitment.id,
        "text": commitment.text,
        "normalized_id": commitment.normalized_id,
        "content_fingerprint": commitment.content_fingerprint,
        "kind": commitment.kind.value,
        "source": _source_to_dict(commitment.source),
        "implementation_worthy": commitment.implementation_worthy,
    }


def _commitment_from_dict(data: Mapping[str, Any]) -> DocumentationCommitment:
    return DocumentationCommitment(
        id=_text(data.get("id")),
        text=_text(data.get("text")),
        normalized_id=_text(data.get("normalized_id")),
        content_fingerprint=_text(data.get("content_fingerprint")),
        kind=DocumentationCommitmentKind(_text(data.get("kind"))),
        source=_source_from_dict(_mapping(data.get("source"))),
        implementation_worthy=bool(data.get("implementation_worthy", True)),
    )


def _source_to_dict(source: DocumentationSourceReference) -> dict[str, Any]:
    return {
        "source_type": source.source_type,
        "path": source.path,
        "heading": source.heading,
        "line": source.line,
        "anchor": source.anchor,
    }


def _source_from_dict(data: Mapping[str, Any]) -> DocumentationSourceReference:
    return DocumentationSourceReference(
        source_type=_text(data.get("source_type")),
        path=_text(data.get("path")),
        heading=_text(data.get("heading")),
        line=_int(data.get("line")),
        anchor=_text(data.get("anchor")),
    )


def _project_to_dict(project: DocumentationTraceabilityProject) -> dict[str, Any]:
    return {
        "project_id": project.project_id,
        "project_name": project.project_name,
        "jira_project_key": project.jira_project_key,
        "docs_roots": list(project.docs_roots),
        "confluence_mirror_roots": list(project.confluence_mirror_roots),
        "confluence_space": project.confluence_space,
        "release_target": project.release_target,
    }


def _project_from_dict(data: Mapping[str, Any]) -> DocumentationTraceabilityProject:
    return DocumentationTraceabilityProject(
        project_id=_text(data.get("project_id")),
        project_name=_text(data.get("project_name")),
        jira_project_key=_text(data.get("jira_project_key")),
        docs_roots=tuple(_text(item) for item in _list(data.get("docs_roots"))),
        confluence_mirror_roots=tuple(_text(item) for item in _list(data.get("confluence_mirror_roots"))),
        confluence_space=_text(data.get("confluence_space")),
        release_target=_text(data.get("release_target")),
    )


def _candidate_to_dict(candidate: DocumentationBacklogCandidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "title": candidate.title,
        "description": candidate.description,
        "source_commitment_id": candidate.source_commitment_id,
        "target_status": candidate.target_status,
        "project_id": candidate.project_id,
        "jira_project_key": candidate.jira_project_key,
        "release_target": candidate.release_target,
        "labels": list(candidate.labels),
    }


def _commitment_kind(text: str) -> DocumentationCommitmentKind:
    lowered = text.casefold()
    if any(marker in lowered for marker in ("operator ui", "inbox ui", "dashboard", "frontend", "ui ")):
        return DocumentationCommitmentKind.OPERATOR_UI_REQUIREMENT
    if any(marker in lowered for marker in ("orchestrator", "developer agent", "tester agent", "review agent", "agent ")):
        return DocumentationCommitmentKind.AGENT_RESPONSIBILITY
    if any(marker in lowered for marker in ("github", "jira", "confluence", "agiletest", "figma", "integration")):
        return DocumentationCommitmentKind.INTEGRATION_REQUIREMENT
    if any(marker in lowered for marker in ("release", "roadmap", "future", "deferred")):
        return DocumentationCommitmentKind.ROADMAP_ITEM
    if any(marker in lowered for marker in ("must", "shall", "required", "process", "workflow")):
        return DocumentationCommitmentKind.PROCESS_RULE
    return DocumentationCommitmentKind.IMPROVEMENT_CANDIDATE


def _is_actionable_text(text: str) -> bool:
    lowered = text.casefold()
    return bool(text) and any(marker in lowered for marker in _ACTIONABLE_MARKERS)


def _clean_markdown_line(value: str) -> str:
    cleaned = re.sub(r"^[-*+]\s+", "", value)
    cleaned = re.sub(r"^\d+[.)]\s+", "", cleaned)
    return cleaned.strip()


def _candidate_title(text: str) -> str:
    stripped = re.sub(r"\[[^\]]+\]\s*", "", text).strip()
    return stripped[:90].rstrip(".") or "Documented backlog candidate"


def _relative_source_path(path: Path, root: Path) -> str:
    base = root if root.is_dir() else root.parent
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _normalize_text(value)) if token not in _STOP_WORDS}


def _token_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, min(len(left), len(right)))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", _normalize_text(value))).strip("-")


def _has_marker(text: str, marker: str) -> bool:
    return marker in text or marker.replace("-", " ") in text


def _validate_config(config: DocumentationTraceabilityAuditConfig) -> None:
    _require_text("report_id", config.report_id)
    _require_text("created_at", config.created_at)
    _require_text("project_id", config.project.project_id)
    _require_text("jira_project_key", config.project.jira_project_key)
    if not config.project.docs_roots and not config.project.confluence_mirror_roots:
        raise DocumentationTraceabilityError("at least one docs or Confluence mirror root is required")


def _require_text(field: str, value: str) -> None:
    if not value or not str(value).strip():
        raise DocumentationTraceabilityError(f"{field} is required")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
