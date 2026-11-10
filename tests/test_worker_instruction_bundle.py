from pathlib import Path

from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.domain.worker_instruction_bundle import (
    format_worker_instruction_bundle_validation,
    resolve_assignment_context_pack_path,
    validate_worker_instruction_bundle,
    worker_instruction_failure_reason,
)


def test_worker_instruction_bundle_passes_with_role_docs_and_assignment_context(tmp_path: Path) -> None:
    instruction_root = _instruction_root(tmp_path)
    context_pack = tmp_path / "context-packs" / "AGENT-621" / "context.json"
    context_pack.parent.mkdir(parents=True)
    context_pack.write_text("{}", encoding="utf-8")

    result = validate_worker_instruction_bundle(
        role=AgentRole.DEVELOPER,
        instruction_root=instruction_root,
        context_packs_root=tmp_path / "context-packs",
        assignment_context_pack_path="data/context-packs/AGENT-621/context.json",
    )

    assert result.passed
    assert not result.failed_checks
    assert worker_instruction_failure_reason(result) == ""


def test_worker_instruction_bundle_reports_missing_role_file_without_contents(tmp_path: Path) -> None:
    instruction_root = _instruction_root(tmp_path)
    (instruction_root / "ai_agents" / "roles" / "developer.md").unlink()

    result = validate_worker_instruction_bundle(
        role=AgentRole.DEVELOPER,
        instruction_root=instruction_root,
        context_packs_root=tmp_path / "context-packs",
    )
    formatted = format_worker_instruction_bundle_validation(result)

    assert not result.passed
    assert [check.name for check in result.failed_checks] == ["instructions.role"]
    assert "instructions.role" in worker_instruction_failure_reason(result)
    assert "developer secret instructions" not in formatted


def test_assignment_context_pack_resolution_uses_configured_durable_root(tmp_path: Path) -> None:
    context_root = tmp_path / "custom-context-packs"
    absolute = tmp_path / "absolute-context.json"

    assert resolve_assignment_context_pack_path(
        "data/context-packs/AGENT-621/context.json",
        context_packs_root=context_root,
    ) == context_root / "AGENT-621" / "context.json"
    assert resolve_assignment_context_pack_path(
        "context-packs/AGENT-622/context.json",
        context_packs_root=context_root,
    ) == context_root / "AGENT-622" / "context.json"
    assert resolve_assignment_context_pack_path(str(absolute), context_packs_root=context_root) == absolute


def _instruction_root(tmp_path: Path) -> Path:
    root = tmp_path / "instructions"
    files = (
        root / "AGENTS.md",
        root / "ai_agents" / "roles" / "developer.md",
        root / "ai_agents" / "session_starters" / "README.md",
        root / "docs" / "context-pack-generator.md",
        root / ".agents" / "skills" / "codex-quota-guard" / "SKILL.md",
        root / "docs" / "templates" / "target-project-AGENTS.md",
    )
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("developer secret instructions", encoding="utf-8")
    return root
