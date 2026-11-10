from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ci_failure_recovery_playbook_documents_runtime_handoff_and_recovery_steps() -> None:
    playbook = (PROJECT_ROOT / "docs/ci-failure-recovery-playbook.md").read_text(encoding="utf-8")

    assert "Validation Runtime Handoff" in playbook
    assert "Runtime command prefix" in playbook
    assert "system Python" in playbook
    assert "Reacquire or reopen the assignment lock" in playbook
    assert "Move Jira back to the closest active development status" in playbook
    assert "Push a focused fix commit" in playbook
    assert "Verify GitHub checks" in playbook
    assert "Return the story to `DEV COMPLETED` only after" in playbook


def test_validation_and_github_docs_link_to_ci_recovery_playbook() -> None:
    validation_workflow = (
        PROJECT_ROOT / "docs/developer-branch-commit-validation-workflow.md"
    ).read_text(encoding="utf-8")
    github_adapter = (PROJECT_ROOT / "docs/github-adapter.md").read_text(encoding="utf-8")

    assert "Validation Runtime Handoff" in validation_workflow
    assert "docs/ci-failure-recovery-playbook.md" in validation_workflow
    assert "restore Jira" in validation_workflow
    assert "docs/ci-failure-recovery-playbook.md" in github_adapter
    assert "final GitHub check\nstate" in github_adapter
