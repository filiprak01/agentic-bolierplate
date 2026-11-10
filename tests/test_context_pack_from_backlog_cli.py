import json
from pathlib import Path

from agentic_boilerplate.cli import main
from agentic_boilerplate.domain import (
    AgentRole,
    RequirementEpicInput,
    RequirementInput,
    RequirementSprintInput,
    RequirementStoryInput,
    backlog_draft_to_dict,
    create_backlog_draft,
)
from agentic_boilerplate.domain.story_complexity import ComplexityLevel


def test_context_pack_generate_from_backlog_draft_cli_writes_all_story_packs(tmp_path: Path, capsys) -> None:
    draft = create_backlog_draft(_requirement(), created_at="2026-08-10T12:00:00Z")
    draft_path = tmp_path / "REQ-R1.json"
    draft_path.write_text(json.dumps(backlog_draft_to_dict(draft)), encoding="utf-8")
    context_root = tmp_path / "context-packs"

    result = main(
        [
            "context-pack",
            "generate-from-backlog-draft",
            "--draft-path",
            str(draft_path),
            "--context-pack-root",
            str(context_root),
            "--target-repo-path",
            "/workspace/airline",
            "--created-at",
            "2026-08-10T12:10:00Z",
            "--documentation-reference",
            "docs/product/scope.md=Approved PO scope",
            "--shared-context",
            "Release source docs are approved.",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["context_pack_count"] == 2
    assert len(payload["locations"]) == 2
    first_markdown = Path(payload["locations"][0]["markdown_path"])
    second_json = Path(payload["locations"][1]["json_path"])
    assert first_markdown.is_file()
    assert second_json.is_file()
    markdown = first_markdown.read_text(encoding="utf-8")
    assert "## Shared Context" in markdown
    assert "## Role-Specific Context" in markdown
    assert "Release source docs are approved." in markdown


def _requirement() -> RequirementInput:
    return RequirementInput(
        key="REQ-R1",
        title="Release 1 draft",
        overview="Create the initial release backlog from approved docs.",
        epics=(
            RequirementEpicInput(
                id="EPIC-PLANNING",
                title="Planning",
                description="Planning workflow.",
                stories=(
                    RequirementStoryInput(
                        id="STORY-1",
                        title="Generate draft",
                        description="Generate a local draft.",
                        acceptance_criteria=("Draft exists.",),
                        prerequisite_story_ids=(),
                        complexity=ComplexityLevel.C2,
                        complexity_rationale="Structured transformation.",
                    ),
                    RequirementStoryInput(
                        id="STORY-2",
                        title="Build inbox UI",
                        description="Implement accepted inbox UI.",
                        acceptance_criteria=("UI uses accepted design.",),
                        prerequisite_story_ids=("STORY-1",),
                        complexity=ComplexityLevel.C3,
                        complexity_rationale="Frontend work with project state.",
                        role=AgentRole.FRONTEND,
                    ),
                ),
            ),
        ),
        sprint_rings=(
            RequirementSprintInput(
                id="SPRINT-1",
                name="Planning setup",
                goal="Prepare planning and UI slices.",
                story_ids=("STORY-1", "STORY-2"),
            ),
        ),
    )
