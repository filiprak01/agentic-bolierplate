from pathlib import Path


def test_release_track_policy_explains_operator_branch_selection(project_root: Path) -> None:
    policy = (project_root / "docs" / "release-track-policy.md").read_text(encoding="utf-8")
    getting_started = (project_root / "docs" / "getting-started.md").read_text(encoding="utf-8")
    readme = (project_root / "README.md").read_text(encoding="utf-8")

    assert "## Operator Track Selection" in policy
    assert "release/1.0.0" in policy
    assert "Release `1.1.0` planning" in policy
    assert "Do not mix Release `1.1.0` planning" in policy
    assert "docs/release-1.1-scope-discussion.md" in policy
    assert "docs/release-1.1-backlog-draft.md" in policy

    assert "docs/release-track-policy.md" in getting_started
    assert "Use `release/1.0.0` only when testing or demonstrating the MVP snapshot." in getting_started
    assert "Release `1.1.0` planning and implementation" in getting_started

    assert "Release track selection is documented in `docs/release-track-policy.md`." in readme
    assert "Use `release/1.2.0` or `v1.2.0` for stable Release 1.2 validation." in readme
    assert "Use `v1.2.0`, or use `release/1.2.0`" in readme
    assert "when you need the maintained" in readme
