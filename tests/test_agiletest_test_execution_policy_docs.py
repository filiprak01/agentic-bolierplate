from pathlib import Path


def test_agiletest_test_execution_policy_defines_required_and_skip_paths(project_root: Path) -> None:
    policy = (project_root / "docs" / "agiletest-test-execution-policy.md").read_text(encoding="utf-8")

    assert "Create or upsert an AgileTest Test Execution key" in policy
    assert "Accepted Skip Cases" in policy
    assert "skip justification" in policy
    assert "Durable manifest" in policy
    assert "Durable evidence" in policy
    assert "Missing without justification" in policy or "missing without justification" in policy
    assert "Developer-owned Jira story" in policy


def test_regression_overview_and_manifest_docs_reference_agiletest_policy(project_root: Path) -> None:
    overview = (project_root / "docs" / "sprint-regression-overview-workflow.md").read_text(
        encoding="utf-8"
    )
    manifest = (project_root / "docs" / "regression-manifest-builder.md").read_text(encoding="utf-8")

    assert "docs/agiletest-test-execution-policy.md" in overview
    assert "skip justification" in overview
    assert "block" in overview
    assert "closure publication" in overview
    assert "docs/agiletest-test-execution-policy.md" in manifest
    assert "Test Execution is skipped" in manifest


def test_release_manager_and_tester_roles_reference_agiletest_execution_policy(project_root: Path) -> None:
    release_manager = (project_root / "ai_agents" / "roles" / "release_manager.md").read_text(
        encoding="utf-8"
    )
    tester = (project_root / "ai_agents" / "roles" / "tester.md").read_text(encoding="utf-8")

    assert "docs/agiletest-test-execution-policy.md" in release_manager
    assert "accepted skip" in release_manager
    assert "docs/agiletest-test-execution-policy.md" in tester
    assert "skip-justification" in tester
