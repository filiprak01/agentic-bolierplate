from pathlib import Path


DOC = Path("docs/tester-bug-retest-workflow.md")


def test_tester_bug_retest_doc_defines_duplicate_signature_and_bug_reuse() -> None:
    text = _normalized()

    assert "stable duplicate-detection signature" in text
    assert "reuses the existing Bug" in text
    assert "covered issue, Test issue, and failed acceptance criteria" in text


def test_tester_bug_retest_doc_defines_durable_bug_fix_handoff() -> None:
    text = _normalized()

    assert "agentic agent-messages publish-handoff" in text
    assert "--event testing_failed" in text
    assert "`bug_fix_requested`" in text
    assert "targets the Developer role" in text
    assert "context pack path" in text
    assert "communication channel id" in text


def test_tester_bug_retest_doc_defines_retest_and_po_boundary() -> None:
    text = _normalized()

    assert "Retest required flag" in text
    assert "Failed-test signature" in text
    assert "Durable `bug_fix_requested` message id" in text
    assert "Product Owner input is required only" in text


def _normalized() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").split())
