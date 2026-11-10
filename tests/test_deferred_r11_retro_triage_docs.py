from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_deferred_release_1_1_retro_items_are_routed_to_release_1_2_scope() -> None:
    roadmap = (PROJECT_ROOT / "docs/retro-follow-up-roadmap.md").read_text(encoding="utf-8")

    assert "Release 1.1 Deferred Retro Closure Routing" in roadmap
    for deferred_key in ("AGENT-463", "AGENT-465", "AGENT-467"):
        assert deferred_key in roadmap
    for routed_key in (
        "AGENT-636",
        "AGENT-643",
        "AGENT-674",
        "AGENT-678",
        "AGENT-687",
        "AGENT-698",
    ):
        assert routed_key in roadmap
    assert "historical deferred source items" in roadmap
    assert "mixed target/process PRs without visible reasoning are excluded" in roadmap
