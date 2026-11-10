from datetime import datetime, timezone

from agentic_boilerplate.domain.dependency_eligibility import (
    DependencyBlockerKind,
    DependencyGraphIssueKind,
    build_dependency_graph_audit,
    check_dependency_eligibility,
    render_dependency_eligibility_note,
    render_dependency_graph_audit,
)
from agentic_boilerplate.integrations.jira import JiraIssueDependencyLinks, JiraLinkedIssue
from agentic_boilerplate.storage.dependency_eligibility import write_dependency_eligibility_note


def test_dependency_checker_marks_story_blocked_by_incomplete_prerequisite() -> None:
    links = JiraIssueDependencyLinks(
        issue_key="AGENT-39",
        blockers=("AGENT-29",),
        blocker_issues=(
            JiraLinkedIssue(
                key="AGENT-29",
                summary="Adapter",
                issue_type="Story",
                status="IN PROGRESS",
            ),
        ),
    )

    result = check_dependency_eligibility(links)

    assert result.eligible is False
    assert result.blockers[0].issue_key == "AGENT-29"
    assert result.blockers[0].kind is DependencyBlockerKind.INCOMPLETE_PREREQUISITE


def test_dependency_checker_marks_story_unblocked_when_prerequisites_are_test_completed() -> None:
    links = JiraIssueDependencyLinks(
        issue_key="AGENT-39",
        blockers=("AGENT-29",),
        blocked=("AGENT-41",),
        blocker_issues=(JiraLinkedIssue(key="AGENT-29", status="TEST COMPLETED"),),
    )

    result = check_dependency_eligibility(links)

    assert result.eligible is True
    assert result.downstream_blocked_issue_keys == ("AGENT-41",)
    assert result.satisfied_prerequisites[0].key == "AGENT-29"
    assert result.reasons == ("All prerequisite dependency links are satisfied.",)


def test_dependency_checker_treats_unresolved_linked_bugs_as_blockers() -> None:
    links = JiraIssueDependencyLinks(
        issue_key="AGENT-39",
        linked_bugs=(
            JiraLinkedIssue(
                key="AGENT-88",
                summary="Regression failure",
                issue_type="Bug",
                status="DEV COMPLETED",
            ),
        ),
    )

    result = check_dependency_eligibility(links)

    assert result.eligible is False
    assert result.blockers[0].kind is DependencyBlockerKind.UNRESOLVED_LINKED_BUG


def test_dependency_checker_ignores_resolved_linked_bugs() -> None:
    links = JiraIssueDependencyLinks(
        issue_key="AGENT-39",
        linked_bugs=(JiraLinkedIssue(key="AGENT-88", issue_type="Bug", status="ACCEPTED/DONE"),),
    )

    result = check_dependency_eligibility(links)

    assert result.eligible is True
    assert result.blockers == ()


def test_dependency_checker_flags_support_task_blocks_as_closure_sequencing_warning() -> None:
    links = JiraIssueDependencyLinks(
        issue_key="AP-121",
        blockers=("AP-126",),
        blocker_issues=(
            JiraLinkedIssue(
                key="AP-126",
                summary="Regression overview",
                issue_type="Task",
                status="READY TO START",
                labels=("support-task", "role-release-manager"),
            ),
        ),
    )

    result = check_dependency_eligibility(links)
    note = render_dependency_eligibility_note(result)

    assert result.eligible is True
    assert result.blockers == ()
    assert result.support_task_prerequisites[0].key == "AP-126"
    assert "Support-task Blocks links were flagged" in result.reasons[0]
    assert "Support Task Link Warnings" in note
    assert "closure sequencing" in note


def test_dependency_checker_requires_explicit_override_reason() -> None:
    links = JiraIssueDependencyLinks(
        issue_key="AGENT-39",
        blocker_issues=(JiraLinkedIssue(key="AGENT-29", status="READY TO START"),),
    )

    without_reason = check_dependency_eligibility(links, allow_override=True)
    with_reason = check_dependency_eligibility(
        links,
        allow_override=True,
        override_reason="PO approved parallel discovery only.",
    )

    assert without_reason.eligible is False
    assert with_reason.eligible is True
    assert with_reason.overridden is True
    assert with_reason.override_reason == "PO approved parallel discovery only."


def test_dependency_graph_uses_prerequisite_as_blocker_direction() -> None:
    result = build_dependency_graph_audit(
        (
            JiraIssueDependencyLinks(
                issue_key="AGENT-1049",
                blockers=("AGENT-968",),
                blocked=("AGENT-962",),
            ),
        )
    )

    assert result.passed is True
    assert [edge.notation for edge in result.edges] == ["AGENT-1049 -> AGENT-962", "AGENT-968 -> AGENT-1049"]
    assert render_dependency_graph_audit(result).count("->") == 2


def test_dependency_graph_detects_reciprocal_links_before_assignment() -> None:
    result = build_dependency_graph_audit(
        (
            JiraIssueDependencyLinks(issue_key="AGENT-1015", blockers=("AGENT-1049",)),
            JiraIssueDependencyLinks(issue_key="AGENT-1049", blockers=("AGENT-1015",)),
        )
    )

    assert result.passed is False
    assert result.blocked_issue_keys == ("AGENT-1015", "AGENT-1049")
    assert DependencyGraphIssueKind.RECIPROCAL_BLOCKS_LINK in {issue.kind for issue in result.issues}
    assert DependencyGraphIssueKind.CYCLE in {issue.kind for issue in result.issues}
    assert "Scheduler and sprint closure must stop" in render_dependency_graph_audit(result)


def test_dependency_graph_detects_long_cycles_before_sprint_closure() -> None:
    result = build_dependency_graph_audit(
        (
            JiraIssueDependencyLinks(issue_key="AGENT-1014", blockers=("AGENT-1049",)),
            JiraIssueDependencyLinks(issue_key="AGENT-1015", blockers=("AGENT-1014",)),
            JiraIssueDependencyLinks(issue_key="AGENT-1049", blockers=("AGENT-1015",)),
        )
    )

    cycle_issues = [issue for issue in result.issues if issue.kind is DependencyGraphIssueKind.CYCLE]

    assert result.passed is False
    assert result.blocked_issue_keys == ("AGENT-1014", "AGENT-1015", "AGENT-1049")
    assert len(cycle_issues) == 1
    assert cycle_issues[0].edge_notations == (
        "AGENT-1014 -> AGENT-1015",
        "AGENT-1015 -> AGENT-1049",
        "AGENT-1049 -> AGENT-1014",
    )


def test_dependency_checker_records_durable_assignment_note(tmp_path) -> None:
    result = check_dependency_eligibility(JiraIssueDependencyLinks(issue_key="AGENT-39"))

    path = write_dependency_eligibility_note(
        result,
        tmp_path,
        created_at=datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert path.name == "AGENT-39-dependency-eligibility-20260621T120000Z.md"
    assert "Eligible: yes" in path.read_text(encoding="utf-8")
    assert render_dependency_eligibility_note(result).startswith("# Dependency Eligibility")