from pathlib import Path


HANDOFF = Path("docs/release-1.1-planning-handoff.md")


def test_release_1_1_handoff_bundle_exists_with_release_identity() -> None:
    text = HANDOFF.read_text()

    assert "Release 1.1 Planning Handoff" in text
    assert "Release version: `1.1.0`" in text
    assert "Session Agent And Operator UX Foundation" in text
    assert "does not deliver fully autonomous detached Docker agents" in text


def test_release_1_1_handoff_lists_sprints_and_blocking_closure_story() -> None:
    text = HANDOFF.read_text()

    for sprint_name in (
        "R1.1 S1 Startup",
        "R1.1 S2 Roles Inbox",
        "R1.1 S3 Operator UI",
        "R1.1 S4 Sec Docker",
        "R1.1 S5 Validation",
        "R1.1 S6 Closure",
    ):
        assert sprint_name in text

    assert "`AGENT-453` blocks `AGENT-455`" in text
    assert "`AGENT-455` - R11-S31 - Final Release 1.1 regression and retro package" in text


def test_release_1_1_handoff_keeps_agent_routing_and_durable_paths_visible() -> None:
    text = HANDOFF.read_text()

    assert "Product Planning | `gpt-5.5` | extra high" in text
    assert "Security | `gpt-5.5` | extra high" in text
    assert "`data/po-inbox`" in text
    assert "`data/codex-limits`" in text
    assert "`data/context-packs`" in text


def test_release_1_1_handoff_records_current_board_cleanup_notes() -> None:
    text = HANDOFF.read_text()

    assert "`AGENT-433` is a Sprint 1-labeled story" in text
    assert "`AGENT-447` was pulled forward" in text
    assert "`AGENT-483` was delivered as a Sprint 2 retro follow-up" in text


def test_release_1_1_handoff_records_dogfooding_and_branch_boundaries() -> None:
    text = HANDOFF.read_text()

    assert "MVP Dogfooding Decisions" in text
    assert "must not be added to the `release/1.0.0` MVP snapshot branch" in text
    assert "Backlog drafts, planning bundles, context packs" in text
    assert "Defer live autonomous Docker workers" in text
