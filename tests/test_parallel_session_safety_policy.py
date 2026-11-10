from pathlib import Path


def test_parallel_session_policy_covers_required_operating_rules() -> None:
    text = Path("docs/parallel-session-safety-policy.md").read_text(encoding="utf-8")

    assert "READY TO START" in text
    assert "assignment lock" in text
    assert "feature/{JIRA_KEY}-{short-slug}" in text
    assert "Review, testing, and release work are sequential" in text
    assert "Product Owner gates work by moving stories into `READY TO START`" in text
    assert "Codex limits" in text
    assert "Dry-run worker checks detect conflicting active locks" in text
    assert "Live worker execution creates or reuses one active lock" in text
    assert "workspace path" in text
    assert "agentic worker locks list" in text
