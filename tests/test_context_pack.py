import json

import pytest

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import (
    AgentRole,
    ContextPack,
    ContextPackBuildInput,
    ContextPackDependency,
    ContextPackDesignReference,
    ContextPackDocumentationReference,
    ContextPackOutputPaths,
    ContextPackRouting,
    ContextPackSchemaError,
    ContextPackStackMetadata,
    ReasoningLevel,
    RoleSpecificContext,
    RoutingSource,
    build_context_pack,
    context_pack_build_input_from_dict,
    build_missing_context_questions,
    context_pack_from_dict,
    context_pack_to_dict,
    render_context_pack_markdown,
    require_valid_context_pack,
    validate_context_pack,
)
from agentic_boilerplate.storage import FileContextPackStore


def test_context_pack_round_trips_to_json_compatible_data() -> None:
    context_pack = _base_context_pack()

    require_valid_context_pack(context_pack)
    data = context_pack_to_dict(context_pack)
    restored = context_pack_from_dict(data)

    assert data["issue_key"] == "AGENT-42"
    assert data["routing"]["reasoning"] == "high"
    assert data["routing"]["role_instruction_path"] == "ai_agents/roles/developer.md"
    assert data["routing"]["role_instruction_version"] == "release-1.1"
    assert data["stack_metadata"]["stack_id"] == "stack-agent-41"
    assert data["stack_metadata"]["pull_request_number"] == 199
    assert data["design_references"][0]["source_type"] == "figma"
    assert data["role_specific_context"][0]["role"] == "developer"
    assert restored == context_pack
    json.dumps(data)


def test_legacy_context_pack_records_without_stack_metadata_still_load() -> None:
    data = context_pack_to_dict(_base_context_pack())
    data.pop("stack_metadata")

    restored = context_pack_from_dict(data)

    assert restored.stack_metadata == ContextPackStackMetadata()
    require_valid_context_pack(restored)


def test_missing_context_is_reported_without_prompt_or_secret_values() -> None:
    context_pack = ContextPack(
        **{
            **_base_context_pack().__dict__,
            "summary": "",
            "acceptance_criteria": (),
            "documentation_references": (),
            "open_questions": ("Should the worker use token=super-secret-value?",),
        }
    )

    with pytest.raises(ContextPackSchemaError) as exc_info:
        require_valid_context_pack(context_pack)

    message = str(exc_info.value)
    assert "summary" in message
    assert "acceptance_criteria" in message
    assert "documentation_references" in message
    assert "open_questions" in message
    assert "super-secret-value" not in message


def test_unsatisfied_dependencies_block_execution() -> None:
    context_pack = ContextPack(
        **{
            **_base_context_pack().__dict__,
            "dependencies": (
                ContextPackDependency(
                    issue_key="AGENT-41",
                    status="IN PROGRESS",
                    summary="Scheduler approved scope assignment",
                    satisfied=False,
                ),
            ),
        }
    )

    issues = validate_context_pack(context_pack)

    assert {issue.field for issue in issues} == {"dependencies[0].satisfied"}


def test_missing_context_questions_are_built_for_po_inbox() -> None:
    context_pack = ContextPack(
        **{
            **_base_context_pack().__dict__,
            "acceptance_criteria": (),
        }
    )

    questions = build_missing_context_questions(context_pack, created_at="2026-06-24T08:00:00Z")

    assert len(questions) == 1
    assert questions[0].jira_issue_key == "AGENT-42"
    assert questions[0].context_pack_path == "data/context-packs/AGENT-42/context-pack.md"
    assert "acceptance_criteria" in questions[0].title


def test_context_pack_markdown_is_po_readable() -> None:
    markdown = render_context_pack_markdown(_base_context_pack())

    assert "# Context Pack - AGENT-42" in markdown
    assert "- Branch: feature/AGENT-42-context-pack-generator" in markdown
    assert "- AGENT-41: Accepted/Done (satisfied)" in markdown
    assert "- docs/story-complexity-model.md (required)" in markdown
    assert "## Design References" in markdown
    assert "- figma: https://figma.example/file/agentic (required) - frame=Inbox compact view" in markdown
    assert "- Routing source: role" in markdown
    assert "- Role instruction: ai_agents/roles/developer.md" in markdown
    assert "- Role instruction version: release-1.1" in markdown
    assert "## Stacked PR Metadata" in markdown
    assert "- Stack ID: stack-agent-41" in markdown
    assert "- Pull request: #199 https://github.example/pr/199" in markdown
    assert "## Codex Switch Checkpoint" in markdown


def test_context_pack_builder_sets_standard_durable_paths() -> None:
    context_pack = build_context_pack(
        ContextPackBuildInput(
            issue_key="AGENT-42",
            summary="Implement Context Pack Generator",
            issue_type="Story",
            status="READY TO START",
            sprint="MVP S7 Developer",
            role=AgentRole.DEVELOPER,
            branch_name="feature/AGENT-42-context-pack-generator",
            target_repo_path="/workspace/sample-project",
            created_at="2026-06-24T08:00:00Z",
            routing=ContextPackRouting(
                model="gpt-5.5",
                reasoning=ReasoningLevel.HIGH,
                speed="normal",
                rationale="Architecture role routing selected this model.",
                routing_source=RoutingSource.ROLE,
                role_instruction_path="ai_agents/roles/architecture.md",
                role_instruction_version="release-1.1",
            ),
            acceptance_criteria=("Context packs are generated from approved Jira and docs.",),
            documentation_references=(ContextPackDocumentationReference(path="docs/story-complexity-model.md"),),
        )
    )

    assert context_pack.output_paths.context_pack_markdown == "data/context-packs/AGENT-42/context-pack.md"
    assert context_pack.output_paths.context_pack_json == "data/context-packs/AGENT-42/context-pack.json"
    assert context_pack.output_paths.codex_job == "data/codex-jobs/AGENT-42/job.json"
    assert context_pack.output_paths.result == "data/codex-results/AGENT-42/result.json"


def test_context_pack_source_accepts_expanded_roles_and_role_instruction_fields() -> None:
    data = _context_pack_source_data()
    data["role"] = "security"
    data["routing"]["model"] = "gpt-5.5"
    data["routing"]["reasoning"] = "xhigh"
    data["routing"]["role_instruction_path"] = "ai_agents/roles/security.md"
    data["routing"]["role_instruction_version"] = "release-1.1"
    data["routing"]["role_routing_override_reason"] = ""

    source = context_pack_build_input_from_dict(data)
    context_pack = build_context_pack(source)

    assert context_pack.role == AgentRole.SECURITY
    assert context_pack.routing.role_instruction_path == "ai_agents/roles/security.md"
    assert context_pack.routing.role_instruction_version == "release-1.1"
    assert context_pack.routing.role_routing_override_reason == ""


def test_context_pack_source_accepts_figma_design_references() -> None:
    data = _context_pack_source_data()
    data["role"] = "frontend"
    data["design_references"] = [
        {
            "source_type": "figma",
            "url": "https://figma.example/file/project?node-id=1-2",
            "frame": "Agent Status",
            "artifact_path": "docs/design/agent-status.png",
            "description": "Accepted operator dashboard frame.",
            "required": True,
        }
    ]

    source = context_pack_build_input_from_dict(data)
    context_pack = build_context_pack(source)

    assert context_pack.role == AgentRole.FRONTEND
    assert context_pack.design_references[0].source_type == "figma"
    assert context_pack.design_references[0].frame == "Agent Status"
    assert "Agent Status" in render_context_pack_markdown(context_pack)


def test_invalid_design_reference_requires_url_or_artifact_path() -> None:
    context_pack = ContextPack(
        **{
            **_base_context_pack().__dict__,
            "design_references": (
                ContextPackDesignReference(source_type="figma", url="", artifact_path=""),
            ),
        }
    )

    issues = validate_context_pack(context_pack)

    assert {issue.field for issue in issues} == {"design_references[0]"}


def test_invalid_stack_metadata_requires_complete_stacked_context() -> None:
    context_pack = ContextPack(
        **{
            **_base_context_pack().__dict__,
            "stack_metadata": ContextPackStackMetadata(stack_id="stack-agent-41"),
        }
    )

    issues = validate_context_pack(context_pack)

    assert {issue.field for issue in issues} == {
        "stack_metadata.lane_id",
        "stack_metadata.stack_trunk",
        "stack_metadata.base_branch",
        "stack_metadata.testability_state",
        "stack_metadata.stack_layer",
    }


def test_context_pack_store_writes_markdown_and_json(tmp_path) -> None:
    store = FileContextPackStore(tmp_path)

    location = store.write(_base_context_pack())

    assert location.markdown_path.read_text(encoding="utf-8").startswith("# Context Pack - AGENT-42")
    assert location.json_path.is_file()
    assert store.read("AGENT-42") == _base_context_pack()


def test_context_pack_cli_generates_durable_artifacts(tmp_path, capsys) -> None:
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(_context_pack_source_data()), encoding="utf-8")
    root = tmp_path / "context-packs"

    exit_code = main(
        (
            "--env-file",
            str(tmp_path / ".env"),
            "context-pack",
            "generate",
            "--input",
            str(source_path),
            "--context-pack-root",
            str(root),
        )
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "created\tAGENT-42" in output
    assert (root / "AGENT-42" / "context-pack.md").is_file()
    assert (root / "AGENT-42" / "context-pack.json").is_file()


def _base_context_pack() -> ContextPack:
    return ContextPack(
        issue_key="AGENT-42",
        summary="Implement Context Pack Generator",
        issue_type="Story",
        status="READY TO START",
        sprint="MVP S7 Developer",
        role=AgentRole.DEVELOPER,
        branch_name="feature/AGENT-42-context-pack-generator",
        target_repo_path="/workspace/sample-project",
        created_at="2026-06-24T08:00:00Z",
            routing=ContextPackRouting(
                model="gpt-5.4",
                reasoning=ReasoningLevel.HIGH,
                speed="normal",
                complexity="C3",
                effort_mode="complex",
                rationale="Development defaults to gpt-5.4 high from the role matrix.",
                routing_source=RoutingSource.ROLE,
                role_instruction_path="ai_agents/roles/developer.md",
                role_instruction_version="release-1.1",
                manual_switch_required=True,
                manual_switch_prompt="Before starting AGENT-42, switch Codex to gpt-5.4 with high reasoning and normal speed for the developer role.",
            ),
        output_paths=ContextPackOutputPaths(
            context_pack_markdown="data/context-packs/AGENT-42/context-pack.md",
            context_pack_json="data/context-packs/AGENT-42/context-pack.json",
            codex_job="data/codex-jobs/AGENT-42/job.json",
            result="data/codex-results/AGENT-42/result.json",
        ),
        labels=("execution-context-required", "context-pack-source-defined"),
        acceptance_criteria=("Context packs are generated from approved Jira and docs.",),
        dependencies=(
            ContextPackDependency(
                issue_key="AGENT-41",
                status="Accepted/Done",
                summary="Scheduler approved scope assignment",
                satisfied=True,
            ),
        ),
        stack_metadata=ContextPackStackMetadata(
            stack_id="stack-agent-41",
            lane_id="stack-lane-agent-41",
            stack_trunk="main",
            stack_layer=2,
            parent_story_key="AGENT-41",
            child_story_keys=("AGENT-43",),
            parent_branch="feature/AGENT-41-parent",
            base_branch="feature/AGENT-41-parent",
            pull_request_number=199,
            pull_request_url="https://github.example/pr/199",
            testability_state="after-stack-layer-merge",
        ),
        documentation_references=(
            ContextPackDocumentationReference(
                path="docs/story-complexity-model.md",
                description="Model and reasoning routing.",
            ),
        ),
        design_references=(
            ContextPackDesignReference(
                source_type="figma",
                url="https://figma.example/file/agentic",
                frame="Inbox compact view",
                artifact_path="docs/design/inbox.png",
                description="Accepted design frame.",
            ),
        ),
        shared_context=("Jira and docs remain the source of truth.",),
        role_specific_context=(
            RoleSpecificContext(
                role=AgentRole.DEVELOPER,
                instructions=("Create implementation subtasks before code changes.",),
            ),
        ),
        test_expectations=("Run focused unit tests for the context pack schema.",),
    )


def _context_pack_source_data() -> dict:
    data = context_pack_to_dict(_base_context_pack())
    data.pop("output_paths")
    return data
