from pathlib import Path
import runpy
import sys

from agentic_boilerplate.config import load_settings
from agentic_boilerplate.domain import (
    AgentAssignment, AgentRole, AssignmentPaths, AssignmentStatus,
    CodexEffortMode, CodexJobArtifact, CodexJobStatus,
    CodexLimitObservationSource, CodexLimitWindowAvailability, CodexLimitWindowStatus,
    ReasoningLevel, acquire_assignment_lock, build_single_pool_codex_limit_availability_record,
)
from agentic_boilerplate.runtime import HostCodexPreflightIssueKind

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/runtime/run_host_codex_supervisor.py"
NOW = "2026-10-11T18:00:00Z"


def _provider_fixture(tmp_path, monkeypatch):
    entrypoint = runpy.run_path(str(SCRIPT))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "run-once"])
    args = entrypoint["_parse_args"]()
    root = tmp_path / "durable"
    source = tmp_path / "source"
    workspace = tmp_path / "workspaces" / "AGENT-1045" / "developer"
    (source / ".git").mkdir(parents=True)
    (workspace / ".git").mkdir(parents=True)
    values = {
        "GITHUB_TOKEN": "fixture-only-never-sent",
        "TARGET_PROJECT_PATH": str(source),
        "AGENTIC_WORKSPACES_ROOT": str(tmp_path / "workspaces"),
        "CODEX_LIMIT_ACCOUNT_SCOPE_ID": "fixture-account",
        "CODEX_LIMIT_BUCKET_ID": "codex",
        "CODEX_LIMIT_STALE_AFTER_SECONDS": "300",
        "CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS": "60",
    }
    for name in ("PO_INBOX", "CONTEXT_PACKS", "AGENT_STATE", "AGENT_LOGS", "CODEX_JOBS", "CODEX_RESULTS", "CODEX_LIMITS"):
        path = root / name.lower()
        path.mkdir(parents=True)
        values[f"DURABLE_{name}_PATH"] = str(path)
    settings = load_settings(None, environ=values)
    paths = entrypoint["_RuntimePaths"].from_args(args, settings)
    assignment = AgentAssignment(
        id="entrypoint-assignment", jira_issue_key="AGENT-1045", role=AgentRole.DEVELOPER,
        status=AssignmentStatus.ASSIGNED,
        paths=AssignmentPaths(
            context_pack_path=str(settings.paths.context_packs / "context.json"),
            codex_job_path=str(settings.paths.codex_jobs / "job.json"),
            output_path=str(settings.paths.codex_results / "result.json"),
            workspace_path=str(workspace),
            evidence_path=str(settings.paths.agent_logs / "evidence.md"),
        ),
        branch_name="feature/AGENT-1045-supervisor-preflight",
        project_id="fixture", project_root=str(source),
        repository=settings.github.repository, jira_project_key="AGENT",
        created_at=NOW, updated_at=NOW,
    )
    job = CodexJobArtifact(
        id="entrypoint-job", jira_issue_key=assignment.jira_issue_key, role=assignment.role,
        target_repo_path=str(workspace), branch_name=assignment.branch_name,
        context_pack_path=assignment.paths.context_pack_path, output_path=assignment.paths.output_path,
        model="fixture-model", reasoning=ReasoningLevel.HIGH, speed="normal",
        effort_mode=CodexEffortMode.COMPLEX, status=CodexJobStatus.QUEUED, created_at=NOW, updated_at=NOW,
    )
    lock = acquire_assignment_lock(
        jira_issue_key=assignment.jira_issue_key, role=assignment.role, worker_session_id="fixture-worker",
        acquired_at=NOW, dependency_gate_passed=True, workspace_path=str(workspace),
    )
    pool = CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus.AVAILABLE, remaining_percent=80,
        reset_at="2026-10-18T18:00:00Z", observation_source=CodexLimitObservationSource.CODEX_APP_SERVER,
        observed_at="2026-10-11T18:00:40Z", bucket_id="codex", window_id="primary", window_name="primary",
        window_duration_minutes=10080,
    )
    record = build_single_pool_codex_limit_availability_record(
        record_id="fixture-observation", pool=pool, account_scope_id="fixture-account",
    )
    return entrypoint["_preflight_provider"](args, settings, paths), args, job, assignment, lock, record


def test_entrypoint_constructs_real_preflight_and_forwards_future_tolerance(tmp_path, monkeypatch):
    provider, _, job, assignment, lock, record = _provider_fixture(tmp_path, monkeypatch)

    decision = provider(job, assignment, lock, record, NOW)

    assert decision.allowed
    assert decision.issues == ()
    assert decision.limit_observation_id == "fixture-observation"


def test_entrypoint_preserves_po_blocker_gate(tmp_path, monkeypatch):
    provider, args, job, assignment, lock, record = _provider_fixture(tmp_path, monkeypatch)
    args.po_blocker_ids = "fixture-blocker"

    decision = provider(job, assignment, lock, record, NOW)

    assert not decision.allowed
    assert HostCodexPreflightIssueKind.PO_BLOCKERS in {issue.kind for issue in decision.issues}


def test_entrypoint_missing_limits_remain_fail_closed(tmp_path, monkeypatch):
    provider, _, job, assignment, lock, _ = _provider_fixture(tmp_path, monkeypatch)

    decision = provider(job, assignment, lock, None, NOW)

    assert not decision.allowed
    assert HostCodexPreflightIssueKind.LIMIT_REFRESH_MISSING in {issue.kind for issue in decision.issues}

