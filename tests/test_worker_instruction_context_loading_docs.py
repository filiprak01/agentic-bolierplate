from pathlib import Path


DOC = Path("docs/worker-instruction-context-loading.md")
READINESS = Path("docs/docker-worker-readiness.md")
GETTING_STARTED = Path("docs/getting-started.md")


def test_worker_instruction_context_loading_doc_defines_required_gate(project_root: Path) -> None:
    text = (project_root / DOC).read_text(encoding="utf-8")

    for required in (
        "AGENTS.md",
        "ai_agents/roles/{role}.md",
        "ai_agents/session_starters/README.md",
        ".agents/skills/codex-quota-guard/SKILL.md",
        "docs/context-pack-generator.md",
        "docs/templates/target-project-AGENTS.md",
        "assignment.paths.context_pack_path",
        "instruction_gate_allowed=false",
    ):
        assert required in text


def test_worker_instruction_context_loading_doc_defines_context_path_resolution(project_root: Path) -> None:
    text = (project_root / DOC).read_text(encoding="utf-8")

    assert "data/context-packs/..." in text
    assert "DURABLE_CONTEXT_PACKS_PATH" in text
    assert "Other relative paths resolve under the instruction root" in text
    assert "<PLATFORM_REPO>/.agents/skills/codex-quota-guard/SKILL.md" in text
    assert "does not automatically discover shared platform skills" in text


def test_worker_instruction_context_loading_is_linked_from_operator_docs(project_root: Path) -> None:
    readiness = (project_root / READINESS).read_text(encoding="utf-8")
    getting_started = (project_root / GETTING_STARTED).read_text(encoding="utf-8")

    assert "docs/worker-instruction-context-loading.md" in readiness
    assert "docs/worker-instruction-context-loading.md" in getting_started
