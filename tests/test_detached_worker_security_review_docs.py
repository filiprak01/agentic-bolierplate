from pathlib import Path


SECURITY_REVIEW = Path("docs/detached-worker-security-review.md")
ARCHITECTURE = Path("docs/detached-docker-execution-architecture.md")
CREDENTIAL_SETUP = Path("docs/credential-setup.md")
READINESS = Path("docs/docker-worker-readiness.md")


def test_detached_worker_security_review_exists_with_release_gate() -> None:
    text = SECURITY_REVIEW.read_text()

    assert "Detached Worker Security Review" in text
    assert "Release 1.2 security gate" in text
    assert "Security Decision" in text
    assert "Threat Model" in text


def test_detached_worker_security_review_covers_release_blocking_risks() -> None:
    text = SECURITY_REVIEW.read_text()

    for risk in (
        "Secret value appears in logs",
        "Shared mutable checkout",
        "Worker resumes with stale or wrong assignment context",
        "Worker runs external writes without assignment metadata",
        "Worker starts without current limit state",
        "PO decision is resolved only through agent-to-agent communication",
    ):
        assert risk in text


def test_detached_worker_security_review_defines_downstream_story_constraints() -> None:
    text = SECURITY_REVIEW.read_text()

    for story_key in ("AGENT-624", "AGENT-625", "AGENT-626", "AGENT-627", "AGENT-628", "AGENT-684"):
        assert story_key in text


def test_related_docs_link_to_detached_worker_security_review() -> None:
    for path in (ARCHITECTURE, CREDENTIAL_SETUP, READINESS):
        assert "docs/detached-worker-security-review.md" in path.read_text()


def test_redaction_contract_includes_standalone_github_tokens() -> None:
    text = SECURITY_REVIEW.read_text()

    assert "github_pat_..." in text
    assert "ghp_..." in text
    assert "raw `.env` contents" in text
