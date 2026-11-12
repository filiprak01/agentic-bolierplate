from pathlib import Path

from agentic_boilerplate.domain.worker_instruction_bundle import platform_agents_instruction_path


def test_agents_md_defines_project_scoped_worker_context() -> None:
    text = _normalized("AGENTS.md")

    for required in (
        "Multi-Project Agent Context",
        "pooled role capacity",
        "one project-scoped assignment per worker at a time",
        "one project identity",
        "one durable PO inbox namespace",
        "one isolated workspace",
        "release or reset all project-specific assumptions",
        "Use dedicated per-project agents",
        "project_id",
        "jira_project_key",
    ):
        assert required in text


def test_orchestrator_role_defines_multi_project_routing_rules() -> None:
    text = _normalized("ai_agents/roles/orchestrator.md")

    for required in (
        "Multi-Project Routing",
        "Default to pooled role capacity",
        "complete project identity",
        "durable PO inbox namespace",
        "isolated workspace",
        "project-specific assumptions have been reset",
        "Use dedicated per-project agents",
        "create a PO inbox blocker",
        "docs/multi-project-identity.md",
    ):
        assert required in text


def test_parallel_workspace_doc_defines_pool_vs_dedicated_policy() -> None:
    text = _normalized("docs/parallel-agent-workspaces.md")

    for required in (
        "Multi-Project Agent Pooling",
        "Default recommendation for Product Owners",
        "pooled role capacity with isolated assignments",
        "one project-scoped assignment at a time",
        "Durable PO inbox namespace",
        "must not reuse target-project assumptions",
        "released or reset",
        "Use dedicated per-project agents",
        "strict operational separation",
    ):
        assert required in text


def test_scheduler_assignment_policy_carries_project_identity_and_reset_gate() -> None:
    text = _normalized("docs/scheduler-approved-scope-assignment.md")

    for required in (
        "Project identity fields",
        "project_id",
        "project_name",
        "project_root",
        "repository",
        "jira_project_key",
        "Durable PO inbox namespace",
        "Isolated workspace path",
        "scheduler assignment is project-scoped",
        "released or reset",
        "docs/multi-project-identity.md",
    ):
        assert required in text


def _normalized(path: str) -> str:
    resolved = platform_agents_instruction_path() if path == "AGENTS.md" else Path(path)
    return " ".join(resolved.read_text(encoding="utf-8").split())
