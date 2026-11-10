"""Worker instruction and context bundle validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentic_boilerplate.domain.po_inbox import AgentRole

TARGET_PROJECT_AGENTS_TEMPLATE_PATH = Path("docs/templates/target-project-AGENTS.md")
CODEX_QUOTA_GUARD_SKILL_PATH = Path(".agents/skills/codex-quota-guard/SKILL.md")


@dataclass(frozen=True)
class WorkerInstructionCheck:
    """One safe file-availability check for worker startup."""

    name: str
    passed: bool
    message: str
    path: str


@dataclass(frozen=True)
class WorkerInstructionBundleValidation:
    """Validation result for role instructions and assignment context."""

    checks: tuple[WorkerInstructionCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[WorkerInstructionCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)


def validate_worker_instruction_bundle(
    *,
    role: AgentRole,
    instruction_root: Path | str = ".",
    context_packs_root: Path | str = "data/context-packs",
    assignment_context_pack_path: str = "",
) -> WorkerInstructionBundleValidation:
    """Validate that a worker can load its role instructions and context pack."""

    root = Path(instruction_root).expanduser()
    checks = [
        _file_check("instructions.root_agents", root / "AGENTS.md"),
        _file_check("instructions.role", root / "ai_agents" / "roles" / f"{role.value}.md"),
        _file_check("instructions.session_starters", root / "ai_agents" / "session_starters" / "README.md"),
        _file_check("instructions.context_pack_workflow", root / "docs" / "context-pack-generator.md"),
        _file_check("instructions.codex_quota_guard_skill", root / CODEX_QUOTA_GUARD_SKILL_PATH),
        _file_check("instructions.target_project_agents_template", target_project_agents_template_path(root)),
    ]

    context_path = assignment_context_pack_path.strip()
    if context_path:
        resolved_context_path = resolve_assignment_context_pack_path(
            context_path,
            context_packs_root=context_packs_root,
            instruction_root=root,
        )
        checks.append(_file_check("assignment.context_pack", resolved_context_path))

    return WorkerInstructionBundleValidation(checks=tuple(checks))


def format_worker_instruction_bundle_validation(result: WorkerInstructionBundleValidation) -> str:
    """Format instruction checks without reading or exposing file contents."""

    lines = ["Worker instruction/context checklist:"]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{marker}] {check.name}: {check.message} ({check.path})")
    return "\n".join(lines)


def worker_instruction_failure_reason(result: WorkerInstructionBundleValidation) -> str:
    """Return a concise safe failure reason for worker logs and CLI output."""

    failed = result.failed_checks
    if not failed:
        return ""
    names = ", ".join(check.name for check in failed)
    return f"Missing required worker instruction/context files: {names}."


def resolve_assignment_context_pack_path(
    path: str,
    *,
    context_packs_root: Path | str = "data/context-packs",
    instruction_root: Path | str = ".",
) -> Path:
    """Resolve assignment context paths through the configured durable context root."""

    raw_path = path.strip()
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate

    normalized = raw_path.replace("\\", "/").strip("/")
    data_prefix = "data/context-packs/"
    short_prefix = "context-packs/"
    context_root = Path(context_packs_root).expanduser()

    if normalized == "data/context-packs":
        return context_root
    if normalized.startswith(data_prefix):
        return context_root / normalized.removeprefix(data_prefix)
    if normalized == "context-packs":
        return context_root
    if normalized.startswith(short_prefix):
        return context_root / normalized.removeprefix(short_prefix)

    return Path(instruction_root).expanduser() / raw_path


def target_project_agents_template_path(instruction_root: Path | str = ".") -> Path:
    """Return the target-project AGENTS.md template path for setup output."""

    root = Path(instruction_root).expanduser()
    local_template = root / TARGET_PROJECT_AGENTS_TEMPLATE_PATH
    if local_template.is_file():
        return local_template

    package_root = Path(__file__).resolve().parents[3]
    return package_root / TARGET_PROJECT_AGENTS_TEMPLATE_PATH


def _file_check(name: str, path: Path) -> WorkerInstructionCheck:
    expanded_path = path.expanduser()
    return WorkerInstructionCheck(
        name=name,
        passed=expanded_path.is_file(),
        message="Required file exists." if expanded_path.is_file() else "Required file is missing.",
        path=str(expanded_path),
    )
