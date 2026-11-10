from pathlib import Path


WORKSPACES = Path("docs/parallel-agent-workspaces.md")
SESSION_POLICY = Path("docs/parallel-session-safety-policy.md")
SCHEDULER = Path("docs/scheduler-approved-scope-assignment.md")
DOCKER_READINESS = Path("docs/docker-worker-readiness.md")


def test_parallel_agent_workspace_design_defines_allocation_and_isolation() -> None:
    text = WORKSPACES.read_text(encoding="utf-8")

    assert "{AGENTIC_WORKSPACES_ROOT}/{project_key}/{jira_issue_key}/{role}/" in text
    assert "one isolated project workspace" in text
    assert "shared durable coordination folders" in text.lower()
    assert "Isolated Per-Worker Folders" in text
    assert "writes source changes only inside its assigned workspace" in text


def test_parallel_agent_workspace_design_defines_creation_options() -> None:
    text = WORKSPACES.read_text(encoding="utf-8")

    assert "Option A - Git Worktree" in text
    assert "default recommendation for local session-mode work" in text
    assert "Option B - Fresh Clone" in text
    assert "preferred for long-running Docker workers" in text
    assert "Option C - Copied Snapshot" in text
    assert "non-mutating validation work" in text


def test_parallel_agent_workspace_design_defines_scheduler_gates_and_blocked_fallback() -> None:
    text = WORKSPACES.read_text(encoding="utf-8")

    for required in (
        "READY TO START",
        "Dependency eligibility",
        "Assignment lock",
        "Codex limit availability",
        "Predicted file-scope conflict risk",
        "blocked story must not stop the sprint",
        "same active sprint",
    ):
        assert required in text


def test_parallel_agent_workspace_design_defines_docker_boundary_and_future_stories() -> None:
    text = WORKSPACES.read_text(encoding="utf-8")

    assert "Assigned isolated workspace at `/workspace/project`" in text
    assert "Shared durable coordination root at `/workspace/data`" in text
    assert "agentic_boilerplate.domain.assignment_workspace" in text
    assert "machine-readable blockers" in text
    assert "Workspace Archive And Cleanup" in text
    assert "agentic_boilerplate.domain.worktree_cleanup" in text
    assert "workspace closure readiness report" in text
    normalized = " ".join(text.split())
    assert "does not implement detached live Codex execution" in normalized
    assert "Workspace allocation command" in text
    assert "Workspace cleanup command" in text
    assert "Scheduler predicted file-scope conflict classifier" in text


def test_related_docs_link_to_parallel_workspace_design() -> None:
    for path in (SESSION_POLICY, SCHEDULER, DOCKER_READINESS):
        assert "docs/parallel-agent-workspaces.md" in path.read_text(encoding="utf-8")
