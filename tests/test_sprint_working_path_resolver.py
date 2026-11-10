import pytest

from agentic_boilerplate.domain import (
    SprintDependencyKind,
    SprintPathCandidate,
    SprintPathDependency,
    SprintTestabilityTiming,
    SprintWorkingPathKind,
    render_sprint_working_path_markdown,
    resolve_sprint_working_paths,
    sprint_working_path_resolution_to_dict,
)


def test_same_repo_implementation_dependencies_form_stacked_path() -> None:
    resolution = resolve_sprint_working_paths(
        (
            _candidate("AGENT-687", blocks=()),
            _candidate("AGENT-688", blocks=("AGENT-687",)),
            _candidate("AGENT-689", blocks=("AGENT-688",)),
        ),
        sprint_label="sprint-r12-s7",
    )

    by_key = {story.issue_key: story for story in resolution.stories}

    assert {story.path_kind for story in resolution.stories} == {SprintWorkingPathKind.STACKED_DEPENDENT}
    assert by_key["AGENT-687"].stack_id == "stack-agent-687"
    assert by_key["AGENT-688"].stack_id == "stack-agent-687"
    assert by_key["AGENT-689"].stack_id == "stack-agent-687"
    assert by_key["AGENT-687"].order < by_key["AGENT-688"].order < by_key["AGENT-689"].order
    assert by_key["AGENT-688"].prerequisite_keys == ("AGENT-687",)
    assert by_key["AGENT-688"].testability_timing is SprintTestabilityTiming.AFTER_STACK_LAYER_MERGE


def test_independent_story_remains_available_for_parallel_pickup() -> None:
    resolution = resolve_sprint_working_paths(
        (
            _candidate("AGENT-687", blocks=()),
            _candidate("AGENT-694", blocks=()),
        ),
        sprint_label="sprint-r12-s7",
    )

    by_key = {story.issue_key: story for story in resolution.stories}

    assert by_key["AGENT-687"].path_kind is SprintWorkingPathKind.INDEPENDENT_PARALLEL
    assert by_key["AGENT-687"].lane_id == "parallel-agent-687"
    assert by_key["AGENT-694"].path_kind is SprintWorkingPathKind.INDEPENDENT_PARALLEL
    assert by_key["AGENT-694"].next_agent_role == "developer"
    assert by_key["AGENT-694"].testability_timing is SprintTestabilityTiming.AFTER_STORY_MERGE


def test_missing_context_design_credentials_and_business_dependency_block_for_po() -> None:
    resolution = resolve_sprint_working_paths(
        (
            SprintPathCandidate(
                issue_key="AGENT-700",
                summary="Needs PO clarity",
                status="READY TO START",
                next_agent_role="developer",
                repository="example-org/agentic-boilerplate",
                trunk_branch="main",
                sprint_label="sprint-r12-s7",
                acceptance_criteria=(),
                context_pack_path="",
                requires_credentials=True,
                credentials_ready=False,
                ui_facing=True,
                accepted_design_reference="",
                dependencies=(
                    SprintPathDependency(
                        blocker_key="AGENT-699",
                        kind=SprintDependencyKind.BUSINESS_DECISION,
                        status="READY TO START",
                    ),
                ),
            ),
        ),
        sprint_label="sprint-r12-s7",
    )

    story = resolution.stories[0]

    assert story.path_kind is SprintWorkingPathKind.BLOCKED_NEEDS_PO
    assert story.next_agent_role == "product_owner"
    assert story.testability_timing is SprintTestabilityTiming.AFTER_PO_DECISION
    assert "Acceptance criteria are missing or unclear." in story.blockers
    assert "Context pack path is missing." in story.blockers
    assert "Required credentials or integration readiness are missing." in story.blockers
    assert "Accepted UI design reference is missing." in story.blockers
    assert "AGENT-699 is an unresolved business-decision dependency." in story.blockers


def test_cross_repo_or_trunk_mismatch_forces_sequential_only_path() -> None:
    resolution = resolve_sprint_working_paths(
        (
            _candidate("AGENT-687", blocks=(), repository="example-org/agentic-boilerplate"),
            _candidate(
                "AGENT-688",
                blocks=("AGENT-687",),
                repository="example-org/other-repo",
            ),
        ),
        sprint_label="sprint-r12-s7",
    )

    by_key = {story.issue_key: story for story in resolution.stories}

    assert by_key["AGENT-688"].path_kind is SprintWorkingPathKind.SEQUENTIAL_ONLY
    assert by_key["AGENT-688"].stack_id == ""
    assert by_key["AGENT-688"].testability_timing is SprintTestabilityTiming.AFTER_PREREQUISITES_MERGE
    assert any("different repository or trunk branch" in blocker for blocker in by_key["AGENT-688"].blockers)


def test_durable_output_contains_required_fields_and_guardrail() -> None:
    resolution = resolve_sprint_working_paths(
        (_candidate("AGENT-687", blocks=()),),
        sprint_label="sprint-r12-s7",
    )

    artifact = sprint_working_path_resolution_to_dict(resolution)
    markdown = render_sprint_working_path_markdown(resolution)

    assert artifact["stories"][0] == {
        "issue_key": "AGENT-687",
        "path_kind": "independent-parallel",
        "lane_id": "parallel-agent-687",
        "stack_id": "",
        "order": 1,
        "blockers": [],
        "next_agent_role": "developer",
        "testability_timing": "after-story-merge",
        "prerequisite_keys": [],
        "downstream_issue_keys": [],
    }
    assert "Agents must follow the resolved lane" in artifact["guardrail"]
    assert "| Issue | Path | Lane | Stack | Order | Blockers | Next agent | Testability | Downstream |" in markdown
    assert "create a Product Owner inbox question" in markdown


def test_duplicate_issue_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate sprint path candidate"):
        resolve_sprint_working_paths(
            (_candidate("AGENT-687", blocks=()), _candidate("AGENT-687", blocks=())),
            sprint_label="sprint-r12-s7",
        )


def _candidate(
    issue_key: str,
    *,
    blocks: tuple[str, ...],
    repository: str = "example-org/agentic-boilerplate",
    trunk_branch: str = "main",
) -> SprintPathCandidate:
    return SprintPathCandidate(
        issue_key=issue_key,
        summary=f"{issue_key} summary",
        status="READY TO START",
        next_agent_role="developer",
        repository=repository,
        trunk_branch=trunk_branch,
        sprint_label="sprint-r12-s7",
        acceptance_criteria=("AC1",),
        context_pack_path=f"data/context-packs/{issue_key}/context.json",
        dependencies=tuple(
            SprintPathDependency(
                blocker_key=blocker_key,
                kind=SprintDependencyKind.IMPLEMENTATION,
                status="READY TO START",
                repository=repository,
                trunk_branch=trunk_branch,
            )
            for blocker_key in blocks
        ),
    )
