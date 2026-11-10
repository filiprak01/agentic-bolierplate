from __future__ import annotations

from pathlib import Path

from agentic_boilerplate.domain import (
    AgentRole,
    CodexLimitObservationSource,
    CodexLimitPlanMode,
    CodexLimitRecommendedAction,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    build_codex_limit_availability_record,
    build_single_pool_codex_limit_availability_record,
    decide_codex_limit_gate,
)
from agentic_boilerplate.domain.worker_instruction_bundle import validate_worker_instruction_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = PROJECT_ROOT / ".agents" / "skills" / "codex-quota-guard" / "SKILL.md"


def test_quota_guard_skill_metadata_and_adapter_contract() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert "name: codex-quota-guard" in text
    assert "description:" in text
    assert "agentic codex-limits refresh" in text
    assert "agentic codex-limits latest --json" in text
    assert "--codex-limits-root" in text
    assert "--account-scope-id" in text
    assert "--bucket-id" in text
    assert "Do not parse `/status`, `/usage`, browser text" in text
    assert "hand-written percentage parser" in text
    assert "TODO" not in text


def test_quota_guard_skill_documents_required_stage_boundaries() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    for phrase in (
        "starts or resumes a Jira assignment",
        "bounded stage, retry",
        "After completion, failure, or a checkpoint",
        "block only the next quota-spending stage",
        "Read-only quota rechecks and durable checkpoint/evidence writes are allowed while blocked",
        "reset time is only a recheck time",
    ):
        assert phrase in text


def test_quota_guard_skill_documents_host_and_runtime_boundaries() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    for phrase in (
        "Hosted or Docker workers without host Codex authentication must ask the host-owned guard",
        "must not mount `CODEX_HOME`, browser profiles, access tokens",
        "Session-mode checks are best-effort",
        "cannot interrupt every internal model request",
        "reserve quota for a whole story",
        "Background wakeups remain outside this skill and belong to `AGENT-966`",
        "runtime enforcement",
    ):
        assert phrase in text


def test_quota_guard_scenario_allows_fresh_record_above_threshold() -> None:
    record = build_single_pool_codex_limit_availability_record(
        record_id="quota-allowed-001",
        account_scope_id="chatgpt-primary",
        pool=_window(
            remaining_percent=12,
            observed_at="2026-09-03T19:20:00Z",
            reset_at="2026-09-07T19:12:57Z",
            bucket_id="codex",
            window_id="primary",
            label="Codex primary",
        ),
    )

    decision = decide_codex_limit_gate(
        record,
        now="2026-09-03T19:21:00Z",
        stale_after_seconds=300,
    )

    assert record.account_scope_id == "chatgpt-primary"
    assert record.windows[0].bucket_id == "codex"
    assert record.recommended_action == CodexLimitRecommendedAction.RESUME
    assert decision.allowed is True
    assert decision.action == CodexLimitRecommendedAction.RESUME


def test_quota_guard_scenario_blocks_at_threshold_and_keeps_reset_as_recheck_time() -> None:
    record = build_single_pool_codex_limit_availability_record(
        record_id="quota-threshold-001",
        account_scope_id="chatgpt-primary",
        pool=_window(
            remaining_percent=10,
            observed_at="2026-09-03T19:20:00Z",
            reset_at="2026-09-07T19:12:57Z",
            bucket_id="codex",
            window_id="primary",
            label="Codex primary",
        ),
    )

    decision = decide_codex_limit_gate(
        record,
        now="2026-09-03T19:21:00Z",
        stale_after_seconds=300,
    )

    assert record.recommended_action == CodexLimitRecommendedAction.WAIT
    assert decision.allowed is False
    assert decision.action == CodexLimitRecommendedAction.WAIT
    assert decision.resume_after == "2026-09-07T19:12:57Z"


def test_quota_guard_scenario_blocks_missing_stale_error_and_limited_records() -> None:
    missing = decide_codex_limit_gate(None)
    stale = decide_codex_limit_gate(
        build_single_pool_codex_limit_availability_record(
            record_id="quota-stale-001",
            pool=_window(
                remaining_percent=80,
                observed_at="2026-09-03T18:00:00Z",
                reset_at="2026-09-07T19:12:57Z",
            ),
        ),
        now="2026-09-03T19:00:01Z",
        stale_after_seconds=3600,
    )
    error_record = build_codex_limit_availability_record(
        record_id="quota-error-001",
        plan_mode=CodexLimitPlanMode.DYNAMIC,
        short_window=_unknown_window(observed_at="2026-09-03T19:00:00Z"),
        broad_quota=_unknown_window(observed_at="2026-09-03T19:00:00Z"),
        windows=(_unknown_window(observed_at="2026-09-03T19:00:00Z"),),
        note="mocked refresh failure from explicit_failure source",
    )
    error = decide_codex_limit_gate(error_record, now="2026-09-03T19:00:01Z", stale_after_seconds=3600)
    limited = decide_codex_limit_gate(
        build_single_pool_codex_limit_availability_record(
            record_id="quota-limited-001",
            pool=_window(
                status=CodexLimitWindowStatus.LIMITED,
                remaining_percent=0,
                observed_at="2026-09-03T19:00:00Z",
                reset_at="2026-09-07T19:12:57Z",
            ),
        ),
        now="2026-09-03T19:00:01Z",
        stale_after_seconds=3600,
    )

    assert missing.allowed is False
    assert missing.action == CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert stale.allowed is False
    assert "stale" in stale.reason
    assert error.allowed is False
    assert error.action == CodexLimitRecommendedAction.ASK_PRODUCT_OWNER
    assert limited.allowed is False
    assert limited.action == CodexLimitRecommendedAction.WAIT


def test_quota_guard_docs_separate_live_endpoint_from_mocked_failure_sources() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    availability_doc = (PROJECT_ROOT / "docs" / "codex-limit-availability.md").read_text(encoding="utf-8")

    assert "account/rateLimits/read" in availability_doc
    assert "codex_app_server" in availability_doc
    assert "offline_fixture" in availability_doc
    assert "explicit_failure" in availability_doc
    assert "EXPLICIT_FAILURE" not in skill


def test_quota_guard_after_stage_refresh_failure_is_next_stage_only_block() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    runner_doc = (PROJECT_ROOT / "docs" / "host-side-codex-runner.md").read_text(encoding="utf-8")

    assert "keep the completed work" in skill
    assert "block only the next quota-spending stage" in skill
    assert "blocks the next Codex request" in runner_doc
    assert "does not invalidate" in runner_doc
    assert "replay the completed side effects" in runner_doc


def test_quota_guard_is_discovered_from_platform_root_for_target_worktree(tmp_path: Path) -> None:
    platform_root = _instruction_root(tmp_path / "platform")
    target_worktree = tmp_path / "target-project"
    target_worktree.mkdir()
    context_pack = tmp_path / "context-packs" / "AGENT-976" / "context.json"
    context_pack.parent.mkdir(parents=True)
    context_pack.write_text("{}", encoding="utf-8")

    result = validate_worker_instruction_bundle(
        role=AgentRole.DEVELOPER,
        instruction_root=platform_root,
        context_packs_root=tmp_path / "context-packs",
        assignment_context_pack_path="data/context-packs/AGENT-976/context.json",
    )

    assert result.passed
    assert target_worktree.exists()
    assert any(
        check.name == "instructions.codex_quota_guard_skill"
        and str(platform_root / ".agents" / "skills" / "codex-quota-guard" / "SKILL.md") == check.path
        for check in result.checks
    )


def test_worker_instruction_bundle_reports_missing_quota_guard_skill(tmp_path: Path) -> None:
    platform_root = _instruction_root(tmp_path / "platform")
    (platform_root / ".agents" / "skills" / "codex-quota-guard" / "SKILL.md").unlink()

    result = validate_worker_instruction_bundle(
        role=AgentRole.DEVELOPER,
        instruction_root=platform_root,
    )

    assert result.passed is False
    assert [check.name for check in result.failed_checks] == ["instructions.codex_quota_guard_skill"]


def test_same_account_multi_project_guidance_keeps_project_refs_separate() -> None:
    subscription = _compact((PROJECT_ROOT / "docs" / "codex-subscription-setup.md").read_text(encoding="utf-8"))
    parallel = _compact((PROJECT_ROOT / "docs" / "parallel-session-safety-policy.md").read_text(encoding="utf-8"))
    context = _compact((PROJECT_ROOT / "docs" / "context-pack-generator.md").read_text(encoding="utf-8"))

    assert "Shared-account multi-project work may use the same account scope" in subscription
    assert "record its own project, issue, role" in subscription
    assert "Project-specific memory, credentials, and unresolved assumptions are never copied" in subscription
    assert "same configured account scope and durable quota root" in parallel
    assert "must not copy host Codex login folders" in parallel
    assert "raw account identifiers" in context


def _compact(text: str) -> str:
    return " ".join(text.split())


def _window(
    *,
    remaining_percent: int,
    observed_at: str = "2026-09-03T19:00:00Z",
    reset_at: str = "2026-09-07T19:12:57Z",
    status: CodexLimitWindowStatus = CodexLimitWindowStatus.AVAILABLE,
    source: CodexLimitObservationSource = CodexLimitObservationSource.CODEX_APP_SERVER,
    bucket_id: str = "codex",
    window_id: str = "primary",
    label: str = "Codex primary",
) -> CodexLimitWindowAvailability:
    return CodexLimitWindowAvailability(
        status=status,
        remaining_percent=remaining_percent,
        reset_at=reset_at,
        observation_source=source,
        observed_at=observed_at,
        bucket_id=bucket_id,
        window_id=window_id,
        label=label,
    )


def _unknown_window(*, observed_at: str) -> CodexLimitWindowAvailability:
    return CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.UNKNOWN,
        remaining_percent=None,
        reset_at="",
        observation_source=CodexLimitObservationSource.EXPLICIT_FAILURE,
        observed_at=observed_at,
        bucket_id="codex",
        window_id="primary",
        label="Codex primary",
    )


def _instruction_root(root: Path) -> Path:
    files = (
        root / "AGENTS.md",
        root / "ai_agents" / "roles" / "developer.md",
        root / "ai_agents" / "session_starters" / "README.md",
        root / "docs" / "context-pack-generator.md",
        root / ".agents" / "skills" / "codex-quota-guard" / "SKILL.md",
        root / "docs" / "templates" / "target-project-AGENTS.md",
    )
    for file_path in files:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test instruction", encoding="utf-8")
    return root
