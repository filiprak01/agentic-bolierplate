"""Worker execution context pack schema."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agentic_boilerplate.domain.po_inbox import AgentRole, InboxMessageType, InboxStatus, POInboxItem
from agentic_boilerplate.domain.story_complexity import ReasoningLevel, RoutingSource


@dataclass(frozen=True)
class ContextPackDocumentationReference:
    """One approved documentation source included in a context pack."""

    path: str
    description: str = ""
    required: bool = True


@dataclass(frozen=True)
class ContextPackDesignReference:
    """One approved UI/UX or Figma source included in a context pack."""

    source_type: str
    url: str = ""
    frame: str = ""
    artifact_path: str = ""
    description: str = ""
    required: bool = True


@dataclass(frozen=True)
class ContextPackDependency:
    """One Jira dependency snapshot used during worker assignment."""

    issue_key: str
    status: str
    summary: str = ""
    satisfied: bool = False


@dataclass(frozen=True)
class ContextPackStackMetadata:
    """Resolved stacked PR path data copied into a worker context pack."""

    stack_id: str = ""
    lane_id: str = ""
    stack_trunk: str = ""
    stack_layer: int = 0
    parent_story_key: str = ""
    child_story_keys: tuple[str, ...] = field(default_factory=tuple)
    parent_branch: str = ""
    base_branch: str = ""
    pull_request_number: int = 0
    pull_request_url: str = ""
    testability_state: str = ""


@dataclass(frozen=True)
class ContextPackOutputPaths:
    """Durable output paths a worker should use for this assignment."""

    context_pack_markdown: str
    context_pack_json: str
    codex_job: str = ""
    result: str = ""
    evidence: str = ""


@dataclass(frozen=True)
class ContextPackRouting:
    """Model and effort routing copied from story planning metadata."""

    model: str
    reasoning: ReasoningLevel
    speed: str
    complexity: str = ""
    effort_mode: str = ""
    rationale: str = ""
    routing_source: RoutingSource = RoutingSource.COMPLEXITY_FALLBACK
    role_instruction_path: str = ""
    role_instruction_version: str = ""
    role_routing_override_reason: str = ""
    manual_switch_required: bool = False
    manual_switch_prompt: str = ""


@dataclass(frozen=True)
class RoleSpecificContext:
    """Instructions scoped to one worker role."""

    role: AgentRole
    instructions: tuple[str, ...]


@dataclass(frozen=True)
class ContextPack:
    """Approved issue context packaged for a worker execution."""

    issue_key: str
    summary: str
    issue_type: str
    status: str
    sprint: str
    role: AgentRole
    branch_name: str
    target_repo_path: str
    created_at: str
    routing: ContextPackRouting
    output_paths: ContextPackOutputPaths
    labels: tuple[str, ...] = field(default_factory=tuple)
    acceptance_criteria: tuple[str, ...] = field(default_factory=tuple)
    dependencies: tuple[ContextPackDependency, ...] = field(default_factory=tuple)
    stack_metadata: ContextPackStackMetadata = field(default_factory=ContextPackStackMetadata)
    documentation_references: tuple[ContextPackDocumentationReference, ...] = field(default_factory=tuple)
    design_references: tuple[ContextPackDesignReference, ...] = field(default_factory=tuple)
    shared_context: tuple[str, ...] = field(default_factory=tuple)
    role_specific_context: tuple[RoleSpecificContext, ...] = field(default_factory=tuple)
    test_expectations: tuple[str, ...] = field(default_factory=tuple)
    open_questions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContextPackBuildInput:
    """Approved source data used to build a context pack."""

    issue_key: str
    summary: str
    issue_type: str
    status: str
    sprint: str
    role: AgentRole
    branch_name: str
    target_repo_path: str
    created_at: str
    routing: ContextPackRouting
    labels: tuple[str, ...] = field(default_factory=tuple)
    acceptance_criteria: tuple[str, ...] = field(default_factory=tuple)
    dependencies: tuple[ContextPackDependency, ...] = field(default_factory=tuple)
    stack_metadata: ContextPackStackMetadata = field(default_factory=ContextPackStackMetadata)
    documentation_references: tuple[ContextPackDocumentationReference, ...] = field(default_factory=tuple)
    design_references: tuple[ContextPackDesignReference, ...] = field(default_factory=tuple)
    shared_context: tuple[str, ...] = field(default_factory=tuple)
    role_specific_context: tuple[RoleSpecificContext, ...] = field(default_factory=tuple)
    test_expectations: tuple[str, ...] = field(default_factory=tuple)
    open_questions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContextPackSchemaIssue:
    """Validation issue for a context pack."""

    field: str
    message: str


class ContextPackSchemaError(ValueError):
    """Raised when a context pack is not executable."""

    def __init__(self, issues: list[ContextPackSchemaIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_context_pack_schema_issues(issues))


def validate_context_pack(context_pack: ContextPack) -> list[ContextPackSchemaIssue]:
    """Return executable-context validation issues."""

    issues: list[ContextPackSchemaIssue] = []
    _require_text(issues, "issue_key", context_pack.issue_key)
    _require_text(issues, "summary", context_pack.summary)
    _require_text(issues, "issue_type", context_pack.issue_type)
    _require_text(issues, "status", context_pack.status)
    _require_text(issues, "sprint", context_pack.sprint)
    _require_text(issues, "branch_name", context_pack.branch_name)
    _require_text(issues, "target_repo_path", context_pack.target_repo_path)
    _require_text(issues, "created_at", context_pack.created_at)
    _validate_routing(issues, context_pack.routing)
    _validate_output_paths(issues, context_pack.output_paths)

    if not context_pack.acceptance_criteria:
        issues.append(ContextPackSchemaIssue("acceptance_criteria", "At least one acceptance criterion is required."))
    if not context_pack.documentation_references:
        issues.append(
            ContextPackSchemaIssue("documentation_references", "At least one approved documentation reference is required.")
        )
    if context_pack.open_questions:
        issues.append(ContextPackSchemaIssue("open_questions", "Open PO questions must be resolved before execution."))

    for index, dependency in enumerate(context_pack.dependencies):
        _require_text(issues, f"dependencies[{index}].issue_key", dependency.issue_key)
        _require_text(issues, f"dependencies[{index}].status", dependency.status)
        if not dependency.satisfied:
            issues.append(
                ContextPackSchemaIssue(
                    f"dependencies[{index}].satisfied",
                    "Dependency must be satisfied before worker execution.",
                )
            )

    _validate_stack_metadata(issues, context_pack.stack_metadata)

    for index, reference in enumerate(context_pack.documentation_references):
        _require_text(issues, f"documentation_references[{index}].path", reference.path)

    for index, reference in enumerate(context_pack.design_references):
        _require_text(issues, f"design_references[{index}].source_type", reference.source_type)
        if not reference.url.strip() and not reference.artifact_path.strip():
            issues.append(
                ContextPackSchemaIssue(
                    f"design_references[{index}]",
                    "Design references require either a URL or a local artifact path.",
                )
            )

    for index, role_context in enumerate(context_pack.role_specific_context):
        if not role_context.instructions:
            issues.append(
                ContextPackSchemaIssue(
                    f"role_specific_context[{index}].instructions",
                    "Role-specific context must include at least one instruction.",
                )
            )

    return issues


def require_valid_context_pack(context_pack: ContextPack) -> ContextPack:
    """Return the context pack or raise a safe validation error."""

    issues = validate_context_pack(context_pack)
    if issues:
        raise ContextPackSchemaError(issues)
    return context_pack


def build_missing_context_questions(
    context_pack: ContextPack,
    *,
    created_at: str,
    agent_id: str = "context-pack-generator",
) -> tuple[POInboxItem, ...]:
    """Build PO inbox questions for missing context instead of guessing."""

    questions: list[POInboxItem] = []
    for issue in validate_context_pack(context_pack):
        questions.append(
            POInboxItem(
                id=f"{context_pack.issue_key}-{_safe_question_id(issue.field)}",
                message_type=InboxMessageType.BLOCKING_QUESTION,
                status=InboxStatus.OPEN,
                title=f"Missing context for {context_pack.issue_key}: {issue.field}",
                message=issue.message,
                agent_role=AgentRole.DEVELOPER,
                created_at=created_at,
                agent_id=agent_id,
                jira_issue_key=context_pack.issue_key,
                context_pack_path=context_pack.output_paths.context_pack_markdown,
                business_impact="Worker execution may proceed from incomplete or guessed requirements.",
                recommendation="Update Jira or documentation, then regenerate the context pack before implementation.",
            )
        )
    return tuple(questions)


def build_context_pack(
    source: ContextPackBuildInput,
    *,
    context_pack_root: str = "data/context-packs",
    codex_jobs_root: str = "data/codex-jobs",
    codex_results_root: str = "data/codex-results",
) -> ContextPack:
    """Build a context pack with standard durable output paths."""

    issue_key = source.issue_key.strip()
    issue_root = f"{context_pack_root.rstrip('/')}/{issue_key}" if issue_key else context_pack_root.rstrip("/")
    return ContextPack(
        issue_key=source.issue_key,
        summary=source.summary,
        issue_type=source.issue_type,
        status=source.status,
        sprint=source.sprint,
        role=source.role,
        branch_name=source.branch_name,
        target_repo_path=source.target_repo_path,
        created_at=source.created_at,
        routing=source.routing,
        output_paths=ContextPackOutputPaths(
            context_pack_markdown=f"{issue_root}/context-pack.md",
            context_pack_json=f"{issue_root}/context-pack.json",
            codex_job=f"{codex_jobs_root.rstrip('/')}/{issue_key}/job.json" if issue_key else "",
            result=f"{codex_results_root.rstrip('/')}/{issue_key}/result.json" if issue_key else "",
        ),
        labels=source.labels,
        acceptance_criteria=source.acceptance_criteria,
        dependencies=source.dependencies,
        stack_metadata=source.stack_metadata,
        documentation_references=source.documentation_references,
        design_references=source.design_references,
        shared_context=source.shared_context,
        role_specific_context=source.role_specific_context,
        test_expectations=source.test_expectations,
        open_questions=source.open_questions,
    )


def context_pack_build_input_from_dict(data: Mapping[str, Any]) -> ContextPackBuildInput:
    """Load approved source data for context pack generation."""

    try:
        routing_data = _mapping(data.get("routing"), "routing")
        return ContextPackBuildInput(
            issue_key=_string(data.get("issue_key")),
            summary=_string(data.get("summary")),
            issue_type=_string(data.get("issue_type")),
            status=_string(data.get("status")),
            sprint=_string(data.get("sprint")),
            role=AgentRole(_string(data.get("role"))),
            branch_name=_string(data.get("branch_name")),
            target_repo_path=_string(data.get("target_repo_path")),
            created_at=_string(data.get("created_at")),
            routing=ContextPackRouting(
                model=_string(routing_data.get("model")),
                reasoning=ReasoningLevel(_string(routing_data.get("reasoning"))),
                speed=_string(routing_data.get("speed")),
                complexity=_string(routing_data.get("complexity")),
                effort_mode=_string(routing_data.get("effort_mode")),
                rationale=_string(routing_data.get("rationale")),
                routing_source=RoutingSource(_string(routing_data.get("routing_source") or RoutingSource.COMPLEXITY_FALLBACK.value)),
                role_instruction_path=_string(routing_data.get("role_instruction_path")),
                role_instruction_version=_string(routing_data.get("role_instruction_version")),
                role_routing_override_reason=_string(routing_data.get("role_routing_override_reason")),
                manual_switch_required=bool(routing_data.get("manual_switch_required", False)),
                manual_switch_prompt=_string(routing_data.get("manual_switch_prompt")),
            ),
            labels=_tuple_of_strings(data.get("labels")),
            acceptance_criteria=_tuple_of_strings(data.get("acceptance_criteria")),
            dependencies=tuple(_dependency_from_dict(item) for item in _sequence(data.get("dependencies"))),
            stack_metadata=_stack_metadata_from_dict(data.get("stack_metadata")),
            documentation_references=tuple(
                _documentation_reference_from_dict(item) for item in _sequence(data.get("documentation_references"))
            ),
            design_references=tuple(_design_reference_from_dict(item) for item in _sequence(data.get("design_references"))),
            shared_context=_tuple_of_strings(data.get("shared_context")),
            role_specific_context=tuple(_role_context_from_dict(item) for item in _sequence(data.get("role_specific_context"))),
            test_expectations=_tuple_of_strings(data.get("test_expectations")),
            open_questions=_tuple_of_strings(data.get("open_questions")),
        )
    except ValueError as error:
        raise ContextPackSchemaError([ContextPackSchemaIssue("context_pack_input", f"Unsupported value: {error}")]) from error


def context_pack_to_dict(context_pack: ContextPack) -> dict[str, Any]:
    """Convert a context pack into JSON-compatible data."""

    return {
        "issue_key": context_pack.issue_key,
        "summary": context_pack.summary,
        "issue_type": context_pack.issue_type,
        "status": context_pack.status,
        "sprint": context_pack.sprint,
        "role": context_pack.role.value,
        "branch_name": context_pack.branch_name,
        "target_repo_path": context_pack.target_repo_path,
        "created_at": context_pack.created_at,
        "routing": {
            "model": context_pack.routing.model,
            "reasoning": context_pack.routing.reasoning.value,
            "speed": context_pack.routing.speed,
            "complexity": context_pack.routing.complexity,
            "effort_mode": context_pack.routing.effort_mode,
            "rationale": context_pack.routing.rationale,
            "routing_source": context_pack.routing.routing_source.value,
            "role_instruction_path": context_pack.routing.role_instruction_path,
            "role_instruction_version": context_pack.routing.role_instruction_version,
            "role_routing_override_reason": context_pack.routing.role_routing_override_reason,
            "manual_switch_required": context_pack.routing.manual_switch_required,
            "manual_switch_prompt": context_pack.routing.manual_switch_prompt,
        },
        "output_paths": {
            "context_pack_markdown": context_pack.output_paths.context_pack_markdown,
            "context_pack_json": context_pack.output_paths.context_pack_json,
            "codex_job": context_pack.output_paths.codex_job,
            "result": context_pack.output_paths.result,
            "evidence": context_pack.output_paths.evidence,
        },
        "labels": list(context_pack.labels),
        "acceptance_criteria": list(context_pack.acceptance_criteria),
        "dependencies": [
            {
                "issue_key": dependency.issue_key,
                "status": dependency.status,
                "summary": dependency.summary,
                "satisfied": dependency.satisfied,
            }
            for dependency in context_pack.dependencies
        ],
        "stack_metadata": {
            "stack_id": context_pack.stack_metadata.stack_id,
            "lane_id": context_pack.stack_metadata.lane_id,
            "stack_trunk": context_pack.stack_metadata.stack_trunk,
            "stack_layer": context_pack.stack_metadata.stack_layer,
            "parent_story_key": context_pack.stack_metadata.parent_story_key,
            "child_story_keys": list(context_pack.stack_metadata.child_story_keys),
            "parent_branch": context_pack.stack_metadata.parent_branch,
            "base_branch": context_pack.stack_metadata.base_branch,
            "pull_request_number": context_pack.stack_metadata.pull_request_number,
            "pull_request_url": context_pack.stack_metadata.pull_request_url,
            "testability_state": context_pack.stack_metadata.testability_state,
        },
        "documentation_references": [
            {
                "path": reference.path,
                "description": reference.description,
                "required": reference.required,
            }
            for reference in context_pack.documentation_references
        ],
        "design_references": [
            {
                "source_type": reference.source_type,
                "url": reference.url,
                "frame": reference.frame,
                "artifact_path": reference.artifact_path,
                "description": reference.description,
                "required": reference.required,
            }
            for reference in context_pack.design_references
        ],
        "shared_context": list(context_pack.shared_context),
        "role_specific_context": [
            {
                "role": role_context.role.value,
                "instructions": list(role_context.instructions),
            }
            for role_context in context_pack.role_specific_context
        ],
        "test_expectations": list(context_pack.test_expectations),
        "open_questions": list(context_pack.open_questions),
    }


def context_pack_from_dict(data: Mapping[str, Any]) -> ContextPack:
    """Load a context pack from JSON-compatible data."""

    try:
        routing_data = _mapping(data.get("routing"), "routing")
        output_data = _mapping(data.get("output_paths"), "output_paths")
        return ContextPack(
            issue_key=_string(data.get("issue_key")),
            summary=_string(data.get("summary")),
            issue_type=_string(data.get("issue_type")),
            status=_string(data.get("status")),
            sprint=_string(data.get("sprint")),
            role=AgentRole(_string(data.get("role"))),
            branch_name=_string(data.get("branch_name")),
            target_repo_path=_string(data.get("target_repo_path")),
            created_at=_string(data.get("created_at")),
            routing=ContextPackRouting(
                model=_string(routing_data.get("model")),
                reasoning=ReasoningLevel(_string(routing_data.get("reasoning"))),
                speed=_string(routing_data.get("speed")),
                complexity=_string(routing_data.get("complexity")),
                effort_mode=_string(routing_data.get("effort_mode")),
                rationale=_string(routing_data.get("rationale")),
                routing_source=RoutingSource(_string(routing_data.get("routing_source") or RoutingSource.COMPLEXITY_FALLBACK.value)),
                role_instruction_path=_string(routing_data.get("role_instruction_path")),
                role_instruction_version=_string(routing_data.get("role_instruction_version")),
                role_routing_override_reason=_string(routing_data.get("role_routing_override_reason")),
                manual_switch_required=bool(routing_data.get("manual_switch_required", False)),
                manual_switch_prompt=_string(routing_data.get("manual_switch_prompt")),
            ),
            output_paths=ContextPackOutputPaths(
                context_pack_markdown=_string(output_data.get("context_pack_markdown")),
                context_pack_json=_string(output_data.get("context_pack_json")),
                codex_job=_string(output_data.get("codex_job")),
                result=_string(output_data.get("result")),
                evidence=_string(output_data.get("evidence")),
            ),
            labels=_tuple_of_strings(data.get("labels")),
            acceptance_criteria=_tuple_of_strings(data.get("acceptance_criteria")),
            dependencies=tuple(_dependency_from_dict(item) for item in _sequence(data.get("dependencies"))),
            stack_metadata=_stack_metadata_from_dict(data.get("stack_metadata")),
            documentation_references=tuple(
                _documentation_reference_from_dict(item) for item in _sequence(data.get("documentation_references"))
            ),
            design_references=tuple(_design_reference_from_dict(item) for item in _sequence(data.get("design_references"))),
            shared_context=_tuple_of_strings(data.get("shared_context")),
            role_specific_context=tuple(_role_context_from_dict(item) for item in _sequence(data.get("role_specific_context"))),
            test_expectations=_tuple_of_strings(data.get("test_expectations")),
            open_questions=_tuple_of_strings(data.get("open_questions")),
        )
    except ValueError as error:
        raise ContextPackSchemaError([ContextPackSchemaIssue("context_pack", f"Unsupported value: {error}")]) from error


def render_context_pack_markdown(context_pack: ContextPack) -> str:
    """Render a PO-readable worker context pack."""

    lines = [
        f"# Context Pack - {context_pack.issue_key}",
        "",
        "## Issue",
        "",
        f"- Summary: {context_pack.summary}",
        f"- Type: {context_pack.issue_type}",
        f"- Status: {context_pack.status}",
        f"- Sprint: {context_pack.sprint}",
        f"- Worker role: {context_pack.role.value}",
        f"- Branch: {context_pack.branch_name}",
        "",
        "## Routing",
        "",
        f"- Model: {context_pack.routing.model}",
        f"- Reasoning: {context_pack.routing.reasoning.value}",
        f"- Speed: {context_pack.routing.speed}",
        f"- Complexity: {context_pack.routing.complexity or 'not specified'}",
        f"- Routing source: {context_pack.routing.routing_source.value}",
        f"- Routing rationale: {context_pack.routing.rationale or 'not specified'}",
        f"- Role instruction: {context_pack.routing.role_instruction_path or 'not specified'}",
        f"- Role instruction version: {context_pack.routing.role_instruction_version or 'not specified'}",
        f"- Role routing override: {context_pack.routing.role_routing_override_reason or 'not specified'}",
        "",
        "## Acceptance Criteria",
        "",
        *_bullet_lines(context_pack.acceptance_criteria),
        "",
        "## Dependencies",
        "",
        *_dependency_lines(context_pack.dependencies),
        "",
        "## Stacked PR Metadata",
        "",
        *_stack_metadata_lines(context_pack.stack_metadata),
        "",
        "## Documentation References",
        "",
        *_documentation_lines(context_pack.documentation_references),
        "",
        "## Design References",
        "",
        *_design_reference_lines(context_pack.design_references),
        "",
        "## Shared Context",
        "",
        *_bullet_lines(context_pack.shared_context),
        "",
        "## Role-Specific Context",
        "",
        *_role_context_lines(context_pack.role_specific_context),
        "",
        "## Test Expectations",
        "",
        *_bullet_lines(context_pack.test_expectations),
        "",
        "## Durable Outputs",
        "",
        f"- Markdown: {context_pack.output_paths.context_pack_markdown}",
        f"- JSON: {context_pack.output_paths.context_pack_json}",
        f"- Codex job: {context_pack.output_paths.codex_job or 'not specified'}",
        f"- Result: {context_pack.output_paths.result or 'not specified'}",
        f"- Evidence: {context_pack.output_paths.evidence or 'not specified'}",
    ]
    if context_pack.routing.manual_switch_required:
        lines.extend(
            [
                "",
                "## Codex Switch Checkpoint",
                "",
                f"- Required: yes",
                f"- Prompt: {context_pack.routing.manual_switch_prompt}",
            ]
        )
    if context_pack.open_questions:
        lines.extend(["", "## Open Questions", "", *_bullet_lines(context_pack.open_questions)])
    return "\n".join(lines).rstrip() + "\n"


def format_context_pack_schema_issues(issues: list[ContextPackSchemaIssue]) -> str:
    """Format validation issues without leaking prompt or PO answer content."""

    return "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _validate_routing(issues: list[ContextPackSchemaIssue], routing: ContextPackRouting) -> None:
    _require_text(issues, "routing.model", routing.model)
    _require_text(issues, "routing.speed", routing.speed)
    _require_text(issues, "routing.role_instruction_path", routing.role_instruction_path)
    _require_text(issues, "routing.role_instruction_version", routing.role_instruction_version)
    if routing.manual_switch_required:
        _require_text(issues, "routing.manual_switch_prompt", routing.manual_switch_prompt)


def _validate_output_paths(issues: list[ContextPackSchemaIssue], output_paths: ContextPackOutputPaths) -> None:
    _require_text(issues, "output_paths.context_pack_markdown", output_paths.context_pack_markdown)
    _require_text(issues, "output_paths.context_pack_json", output_paths.context_pack_json)


def _validate_stack_metadata(issues: list[ContextPackSchemaIssue], metadata: ContextPackStackMetadata) -> None:
    if not _stack_metadata_is_present(metadata):
        return
    _require_text(issues, "stack_metadata.stack_id", metadata.stack_id)
    _require_text(issues, "stack_metadata.lane_id", metadata.lane_id)
    _require_text(issues, "stack_metadata.stack_trunk", metadata.stack_trunk)
    _require_text(issues, "stack_metadata.base_branch", metadata.base_branch)
    _require_text(issues, "stack_metadata.testability_state", metadata.testability_state)
    if metadata.stack_layer < 1:
        issues.append(ContextPackSchemaIssue("stack_metadata.stack_layer", "Stack layer must be 1 or greater."))
    if metadata.pull_request_number < 0:
        issues.append(ContextPackSchemaIssue("stack_metadata.pull_request_number", "PR number cannot be negative."))


def _require_text(issues: list[ContextPackSchemaIssue], field: str, value: str) -> None:
    if not value.strip():
        issues.append(ContextPackSchemaIssue(field, "Required field is missing."))


def _dependency_from_dict(data: Any) -> ContextPackDependency:
    item = _mapping(data, "dependency")
    return ContextPackDependency(
        issue_key=_string(item.get("issue_key")),
        status=_string(item.get("status")),
        summary=_string(item.get("summary")),
        satisfied=bool(item.get("satisfied", False)),
    )


def _stack_metadata_from_dict(data: Any) -> ContextPackStackMetadata:
    if data is None:
        return ContextPackStackMetadata()
    item = _mapping(data, "stack_metadata")
    return ContextPackStackMetadata(
        stack_id=_string(item.get("stack_id")),
        lane_id=_string(item.get("lane_id")),
        stack_trunk=_string(item.get("stack_trunk")),
        stack_layer=_int(item.get("stack_layer", 0)),
        parent_story_key=_string(item.get("parent_story_key")),
        child_story_keys=_tuple_of_strings(item.get("child_story_keys")),
        parent_branch=_string(item.get("parent_branch")),
        base_branch=_string(item.get("base_branch")),
        pull_request_number=_int(item.get("pull_request_number", 0)),
        pull_request_url=_string(item.get("pull_request_url")),
        testability_state=_string(item.get("testability_state")),
    )


def _documentation_reference_from_dict(data: Any) -> ContextPackDocumentationReference:
    item = _mapping(data, "documentation_reference")
    return ContextPackDocumentationReference(
        path=_string(item.get("path")),
        description=_string(item.get("description")),
        required=bool(item.get("required", True)),
    )


def _design_reference_from_dict(data: Any) -> ContextPackDesignReference:
    item = _mapping(data, "design_reference")
    return ContextPackDesignReference(
        source_type=_string(item.get("source_type")),
        url=_string(item.get("url")),
        frame=_string(item.get("frame")),
        artifact_path=_string(item.get("artifact_path")),
        description=_string(item.get("description")),
        required=bool(item.get("required", True)),
    )


def _role_context_from_dict(data: Any) -> RoleSpecificContext:
    item = _mapping(data, "role_specific_context")
    return RoleSpecificContext(
        role=AgentRole(_string(item.get("role"))),
        instructions=_tuple_of_strings(item.get("instructions")),
    )


def _safe_question_id(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def _bullet_lines(values: tuple[str, ...]) -> list[str]:
    return [f"- {value}" for value in values] if values else ["- None"]


def _dependency_lines(values: tuple[ContextPackDependency, ...]) -> list[str]:
    if not values:
        return ["- None"]
    return [
        f"- {dependency.issue_key}: {dependency.status} ({'satisfied' if dependency.satisfied else 'blocked'})"
        for dependency in values
    ]


def _stack_metadata_lines(metadata: ContextPackStackMetadata) -> list[str]:
    if not _stack_metadata_is_present(metadata):
        return ["- Not stacked"]
    return [
        f"- Stack ID: {metadata.stack_id}",
        f"- Lane ID: {metadata.lane_id}",
        f"- Trunk: {metadata.stack_trunk}",
        f"- Layer: {metadata.stack_layer}",
        f"- Parent story: {metadata.parent_story_key or 'none'}",
        f"- Child stories: {', '.join(metadata.child_story_keys) if metadata.child_story_keys else 'none'}",
        f"- Parent branch: {metadata.parent_branch or 'none'}",
        f"- Base branch: {metadata.base_branch}",
        f"- Pull request: {_pull_request_display(metadata)}",
        f"- Testability: {metadata.testability_state}",
    ]


def _stack_metadata_is_present(metadata: ContextPackStackMetadata) -> bool:
    return any(
        (
            metadata.stack_id.strip(),
            metadata.lane_id.strip(),
            metadata.stack_trunk.strip(),
            metadata.stack_layer,
            metadata.parent_story_key.strip(),
            metadata.child_story_keys,
            metadata.parent_branch.strip(),
            metadata.base_branch.strip(),
            metadata.pull_request_number,
            metadata.pull_request_url.strip(),
            metadata.testability_state.strip(),
        )
    )


def _pull_request_display(metadata: ContextPackStackMetadata) -> str:
    if metadata.pull_request_number and metadata.pull_request_url:
        return f"#{metadata.pull_request_number} {metadata.pull_request_url}"
    if metadata.pull_request_number:
        return f"#{metadata.pull_request_number}"
    return metadata.pull_request_url or "not available"


def _documentation_lines(values: tuple[ContextPackDocumentationReference, ...]) -> list[str]:
    if not values:
        return ["- None"]
    lines: list[str] = []
    for reference in values:
        suffix = f" - {reference.description}" if reference.description else ""
        required = "required" if reference.required else "optional"
        lines.append(f"- {reference.path} ({required}){suffix}")
    return lines


def _design_reference_lines(values: tuple[ContextPackDesignReference, ...]) -> list[str]:
    if not values:
        return ["- None"]
    lines: list[str] = []
    for reference in values:
        required = "required" if reference.required else "optional"
        location = reference.url or reference.artifact_path
        parts = [f"- {reference.source_type}: {location} ({required})"]
        if reference.frame:
            parts.append(f"frame={reference.frame}")
        if reference.description:
            parts.append(reference.description)
        lines.append(" - ".join(parts))
    return lines


def _role_context_lines(values: tuple[RoleSpecificContext, ...]) -> list[str]:
    if not values:
        return ["- None"]
    lines: list[str] = []
    for role_context in values:
        lines.append(f"- {role_context.role.value}")
        lines.extend(f"  - {instruction}" for instruction in role_context.instructions)
    return lines


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError("expected a list")
    return tuple(value)


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    return tuple(_string(item) for item in _sequence(value))


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""
