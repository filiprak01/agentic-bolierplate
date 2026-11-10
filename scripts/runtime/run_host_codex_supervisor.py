#!/usr/bin/env python3
"""Run the host-side Codex supervisor for queued durable jobs.

This script is intentionally thin: it wires configured stores, refreshes Codex
quota through the local app-server boundary, builds a RUN02 preflight request,
and lets HostCodexSupervisor process at most one queued job or one bounded loop.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from agentic_boilerplate.config import load_settings
from agentic_boilerplate.domain import (
    AgentAssignment,
    AssignmentWorkspacePlan,
    CodexJobArtifact,
    CodexLimitAvailabilityRecord,
    CodexLimitObservationSource,
    SharedDurablePath,
    WorkspaceProvisioningMode,
    build_assignment_workspace_plan,
)
from agentic_boilerplate.runtime import (
    CodexAppServerLimitReader,
    HostCheckoutState,
    HostCodexLimitRefreshEvidence,
    HostCodexPreflightDecision,
    HostCodexPreflightProvider,
    HostCodexPreflightRequest,
    HostCodexSupervisor,
    HostCodexSupervisorStatus,
    HostPathMapping,
    HostScopeState,
    HostSideCodexRunner,
    SubprocessCodexRunnerExecutor,
    build_unknown_codex_limit_record,
    codex_subprocess_executor_config_from_env,
    evaluate_host_codex_preflight,
    host_codex_supervisor_result_to_dict,
    host_codex_supervisor_status_to_dict,
    refresh_codex_limit_from_payload,
)
from agentic_boilerplate.storage import (
    FileAgentAssignmentStore,
    FileAssignmentLockStore,
    FileCodexJobStore,
    FileCodexLimitAvailabilityStore,
    FileCodexPauseStore,
    FileDetachedWorkerCheckpointStore,
    FileOrchestrationEventQueue,
)


DEFAULT_POLL_SECONDS = 300


def main() -> int:
    args = _parse_args()
    settings = load_settings(args.env_file)
    paths = _RuntimePaths.from_args(args, settings)
    limit_store = FileCodexLimitAvailabilityStore(paths.codex_limits_root)
    if args.command != "status" and not args.skip_limit_refresh:
        _refresh_limits(settings, limit_store)

    supervisor = _build_supervisor(args, settings, paths, limit_store)
    if args.command == "status":
        _print_status(supervisor.status(), as_json=args.json)
        return 0
    if args.command == "run-once":
        result = supervisor.run_once()
        _print_payload(host_codex_supervisor_result_to_dict(result), as_json=args.json)
        return 0 if result.status.service_state.value in {"idle", "stopped"} else 2
    status = supervisor.run_until_stopped(max_iterations=args.max_iterations)
    _print_status(status, as_json=args.json)
    return 0 if status.service_state.value in {"idle", "stopped"} else 2


class _RuntimePaths:
    def __init__(
        self,
        *,
        assignment_state_root: Path,
        lock_state_root: Path,
        checkpoint_state_root: Path,
        event_state_root: Path,
        codex_jobs_root: Path,
        codex_pause_root: Path,
        codex_results_root: Path,
        codex_limits_root: Path,
        logs_root: Path,
    ) -> None:
        self.assignment_state_root = assignment_state_root
        self.lock_state_root = lock_state_root
        self.checkpoint_state_root = checkpoint_state_root
        self.event_state_root = event_state_root
        self.codex_jobs_root = codex_jobs_root
        self.codex_pause_root = codex_pause_root
        self.codex_results_root = codex_results_root
        self.codex_limits_root = codex_limits_root
        self.logs_root = logs_root

    @classmethod
    def from_args(cls, args: argparse.Namespace, settings) -> "_RuntimePaths":
        return cls(
            assignment_state_root=_path(args.assignment_state_root, settings.paths.agent_state),
            lock_state_root=_path(args.lock_state_root, settings.paths.agent_state),
            checkpoint_state_root=_path(args.checkpoint_state_root, settings.paths.agent_state),
            event_state_root=_path(args.event_state_root, settings.paths.agent_state),
            codex_jobs_root=_path(args.codex_jobs_root, settings.paths.codex_jobs),
            codex_pause_root=_path(args.codex_pause_root, settings.paths.codex_results),
            codex_results_root=_path(args.codex_results_root, settings.paths.codex_results),
            codex_limits_root=_path(args.codex_limits_root, settings.paths.codex_limits),
            logs_root=_path(args.logs_root, settings.paths.agent_logs / "host-codex-supervisor"),
        )


def _build_supervisor(args: argparse.Namespace, settings, paths: _RuntimePaths, limit_store: FileCodexLimitAvailabilityStore) -> HostCodexSupervisor:
    job_store = FileCodexJobStore(paths.codex_jobs_root)
    pause_store = FileCodexPauseStore(paths.codex_pause_root)
    assignment_store = FileAgentAssignmentStore(paths.assignment_state_root)
    lock_store = FileAssignmentLockStore(paths.lock_state_root)
    checkpoint_store = FileDetachedWorkerCheckpointStore(paths.checkpoint_state_root)
    event_queue = FileOrchestrationEventQueue(paths.event_state_root)
    executor = SubprocessCodexRunnerExecutor(codex_subprocess_executor_config_from_env())
    runner = HostSideCodexRunner(
        job_store=job_store,
        pause_store=pause_store,
        executor=executor,
        limit_store=limit_store,
        logs_root=paths.logs_root / "runner",
        worker_id=args.worker_id,
        limit_stale_after_seconds=_stale_after(settings),
        limit_future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
        limit_account_scope_id=settings.codex_limit_sentinel.account_scope_id,
        limit_bucket_id=settings.codex_limit_sentinel.bucket_id,
    )
    return HostCodexSupervisor(
        runner=runner,
        assignment_store=assignment_store,
        lock_store=lock_store,
        checkpoint_store=checkpoint_store,
        event_queue=event_queue,
        limit_store=limit_store,
        limit_reader=None if args.skip_post_stage_limit_refresh else _limit_reader(settings),
        preflight_provider=_preflight_provider(args, settings, paths),
        logs_root=paths.logs_root,
        worker_id=args.worker_id,
        poll_interval_seconds=args.poll_interval_seconds,
        limit_account_scope_id=settings.codex_limit_sentinel.account_scope_id,
        limit_bucket_id=settings.codex_limit_sentinel.bucket_id,
        limit_cutoff_percent=settings.codex_limit_sentinel.guard_cutoff_percent,
    )


def _preflight_provider(args: argparse.Namespace, settings, paths: _RuntimePaths) -> HostCodexPreflightProvider:
    path_mappings = _path_mappings(args.path_mapping, settings, paths)
    permitted_output_roots = _permitted_output_roots(settings, paths)
    limit_stale_after_seconds = _stale_after(settings)

    def provider(
        job: CodexJobArtifact,
        assignment: AgentAssignment,
        lock,
        limit_record: CodexLimitAvailabilityRecord | None,
        now: str,
    ) -> HostCodexPreflightDecision:
        workspace_plan = _workspace_plan(assignment, job, settings, paths)
        checkout = _checkout_state(assignment, job, settings, workspace_plan)
        scope = _scope_state(args, assignment, lock, settings)
        request = _preflight_request(
            assignment=assignment,
            workspace_plan=workspace_plan,
            checkout=checkout,
            scope=scope,
            limit_record=limit_record,
            path_mappings=path_mappings,
            permitted_output_roots=permitted_output_roots,
            now=now,
            limit_stale_after_seconds=limit_stale_after_seconds,
            limit_future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
            settings=settings,
        )
        return evaluate_host_codex_preflight(request)

    return provider


def _workspace_plan(assignment: AgentAssignment, job: CodexJobArtifact, settings, paths: _RuntimePaths) -> AssignmentWorkspacePlan:
    seeded = assignment
    if not seeded.branch_name and job.branch_name:
        seeded = replace(seeded, branch_name=job.branch_name)
    if not seeded.repository and settings.github.repository:
        seeded = replace(seeded, repository=settings.github.repository)
    if not seeded.project_root and settings.workers.target_project_path:
        seeded = replace(seeded, project_root=settings.workers.target_project_path)
    return build_assignment_workspace_plan(
        seeded,
        workspaces_root=str(settings.paths.agent_workspaces),
        durable_paths=_shared_durable_paths(settings, paths),
        mode=WorkspaceProvisioningMode.GIT_WORKTREE,
        base_branch=settings.github.default_branch,
        credentials_available=_git_credentials_available(settings),
        require_existing_source=False,
    )


def _checkout_state(
    assignment: AgentAssignment,
    job: CodexJobArtifact,
    settings,
    workspace_plan: AssignmentWorkspacePlan,
) -> HostCheckoutState:
    return HostCheckoutState(
        repository=assignment.repository or workspace_plan.repository or settings.github.repository,
        branch_name=assignment.branch_name or job.branch_name,
        project_id=assignment.project_id,
        jira_project_key=assignment.jira_project_key or settings.jira.project_key,
        jira_issue_key=assignment.jira_issue_key,
        role=assignment.role,
        source_repo_root=assignment.project_root or workspace_plan.source_repo_root or settings.workers.target_project_path,
    )


def _scope_state(args: argparse.Namespace, assignment: AgentAssignment, lock, settings) -> HostScopeState:
    return HostScopeState(
        jira_issue_key=assignment.jira_issue_key,
        jira_project_key=assignment.jira_project_key or settings.jira.project_key,
        project_id=assignment.project_id,
        role=assignment.role,
        status=args.jira_status,
        unresolved_dependency_keys=tuple(_split_csv(args.unresolved_dependency_keys)),
        blocking_bug_keys=tuple(_split_csv(args.blocking_bug_keys)),
        po_blocker_ids=tuple(_split_csv(args.po_blocker_ids)),
        ui_design_required=args.ui_design_required,
        accepted_ui_design_reference=args.accepted_ui_design_reference,
        context_revision_current=not args.context_stale,
        context_revision=args.context_revision,
        assignment_lock_owner=lock.worker_session_id,
        expected_worker_id=lock.worker_session_id,
        assignment_reference=assignment.id,
        po_inbox_reference=assignment.po_inbox_item_id,
    )


def _preflight_request(**kwargs) -> HostCodexPreflightRequest:
    settings = kwargs.pop("settings")
    limit_record = kwargs.pop("limit_record")
    limit_refresh = None
    if limit_record is not None:
        limit_refresh = HostCodexLimitRefreshEvidence(
            record=limit_record,
            observation_id=limit_record.id,
            observed_at=limit_record.short_window.observed_at,
            source=limit_record.short_window.observation_source,
            account_scope_id=settings.codex_limit_sentinel.account_scope_id,
            bucket_id=settings.codex_limit_sentinel.bucket_id,
            refreshed_this_attempt=True,
        )
    return HostCodexPreflightRequest(limit_refresh=limit_refresh, **kwargs)


def _refresh_limits(settings, limit_store: FileCodexLimitAvailabilityStore) -> CodexLimitAvailabilityRecord:
    observed_at = _utc_now()
    reader = _limit_reader(settings)
    try:
        payload = reader.read()
        result = refresh_codex_limit_from_payload(
            payload,
            record_id=_safe_id(f"pre-dispatch-{observed_at}"),
            observed_at=observed_at,
            cutoff_percent=settings.codex_limit_sentinel.guard_cutoff_percent,
            account_scope_id=settings.codex_limit_sentinel.account_scope_id or "default",
            selected_bucket_id=settings.codex_limit_sentinel.bucket_id,
            note="Pre-dispatch refresh from account/rateLimits/read before host supervisor work.",
        )
        selected = limit_store.write_record_and_select_latest(
            result.record,
            account_scope_id=settings.codex_limit_sentinel.account_scope_id,
            bucket_id=settings.codex_limit_sentinel.bucket_id,
        )
        return selected or result.record
    except Exception as exc:  # noqa: BLE001 - unknown quota must fail closed.
        record = build_unknown_codex_limit_record(
            record_id=_safe_id(f"pre-dispatch-unknown-{observed_at}"),
            observed_at=observed_at,
            source=CodexLimitObservationSource.EXPLICIT_FAILURE,
            note=str(exc),
            account_scope_id=settings.codex_limit_sentinel.account_scope_id or "default",
            bucket_id=settings.codex_limit_sentinel.bucket_id,
        )
        limit_store.write_record(record)
        return record


def _limit_reader(settings) -> CodexAppServerLimitReader:
    return CodexAppServerLimitReader(command=settings.codex_limit_sentinel.app_server_command)


def _path_mappings(raw_mappings: Iterable[str], settings, paths: _RuntimePaths) -> tuple[HostPathMapping, ...]:
    configured = [_mapping_from_text(value) for value in raw_mappings]
    defaults = [
        HostPathMapping(".", str(Path(".").resolve()), "repository-root"),
        HostPathMapping("data", str(Path("data").resolve()), "default-durable-root"),
        HostPathMapping(str(settings.paths.po_inbox), str(settings.paths.po_inbox), "po-inbox"),
        HostPathMapping(str(settings.paths.context_packs), str(settings.paths.context_packs), "context-packs"),
        HostPathMapping(str(settings.paths.agent_state), str(settings.paths.agent_state), "agent-state"),
        HostPathMapping(str(settings.paths.agent_logs), str(settings.paths.agent_logs), "agent-logs"),
        HostPathMapping(str(settings.paths.agent_workspaces), str(settings.paths.agent_workspaces), "agent-workspaces"),
        HostPathMapping(str(paths.codex_jobs_root), str(paths.codex_jobs_root), "codex-jobs"),
        HostPathMapping(str(paths.codex_results_root), str(paths.codex_results_root), "codex-results"),
        HostPathMapping(str(paths.codex_limits_root), str(paths.codex_limits_root), "codex-limits"),
    ]
    if settings.workers.target_project_path:
        defaults.append(HostPathMapping(settings.workers.target_project_path, settings.workers.target_project_path, "target-project"))
    return tuple(configured + defaults)


def _mapping_from_text(value: str) -> HostPathMapping:
    if "=" not in value:
        raise SystemExit(f"Invalid --path-mapping {value!r}; expected source=host.")
    source, host = value.split("=", 1)
    if not source.strip() or not host.strip():
        raise SystemExit(f"Invalid --path-mapping {value!r}; source and host are required.")
    return HostPathMapping(source.strip(), host.strip(), "operator")


def _shared_durable_paths(settings, paths: _RuntimePaths) -> tuple[SharedDurablePath, ...]:
    return (
        SharedDurablePath("po-inbox", str(settings.paths.po_inbox)),
        SharedDurablePath("agent-logs", str(paths.logs_root.parent)),
        SharedDurablePath("agent-state", str(settings.paths.agent_state)),
        SharedDurablePath("codex-limits", str(paths.codex_limits_root)),
        SharedDurablePath("codex-jobs", str(paths.codex_jobs_root)),
        SharedDurablePath("codex-results", str(paths.codex_results_root)),
        SharedDurablePath("context-packs", str(settings.paths.context_packs)),
    )


def _permitted_output_roots(settings, paths: _RuntimePaths) -> tuple[str, ...]:
    return (
        str(settings.paths.po_inbox),
        str(settings.paths.context_packs),
        str(settings.paths.agent_state),
        str(paths.codex_jobs_root),
        str(paths.codex_results_root),
        str(paths.codex_limits_root),
        str(paths.logs_root.parent),
    )


def _git_credentials_available(settings) -> bool:
    github = settings.github
    return bool(
        github.token
        or github.ssh_key_path
        or github.ssh_private_key
        or github.ssh_private_key_b64
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the host-side Codex supervisor.")
    parser.add_argument("command", choices=("run-once", "run-loop", "status"))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--worker-id", default="host-codex-supervisor")
    parser.add_argument("--poll-interval-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skip-limit-refresh", action="store_true")
    parser.add_argument("--skip-post-stage-limit-refresh", action="store_true")
    parser.add_argument("--jira-status", default="IN PROGRESS")
    parser.add_argument("--unresolved-dependency-keys", default="")
    parser.add_argument("--blocking-bug-keys", default="")
    parser.add_argument("--po-blocker-ids", default="")
    parser.add_argument("--ui-design-required", action="store_true")
    parser.add_argument("--accepted-ui-design-reference", default="not-required")
    parser.add_argument("--context-stale", action="store_true")
    parser.add_argument("--context-revision", default="")
    parser.add_argument("--path-mapping", action="append", default=[])
    parser.add_argument("--assignment-state-root")
    parser.add_argument("--lock-state-root")
    parser.add_argument("--checkpoint-state-root")
    parser.add_argument("--event-state-root")
    parser.add_argument("--codex-jobs-root")
    parser.add_argument("--codex-pause-root")
    parser.add_argument("--codex-results-root")
    parser.add_argument("--codex-limits-root")
    parser.add_argument("--logs-root")
    return parser.parse_args()


def _path(value: str | None, default: Path) -> Path:
    return Path(value) if value else Path(default)


def _stale_after(settings) -> int | None:
    value = settings.codex_limit_sentinel.stale_after_seconds
    return value if value > 0 else None


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_id(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "_.-" else "-" for character in value)
    return f"{safe.strip('-')}-{datetime.now(timezone.utc).strftime('%f')}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _print_status(status: HostCodexSupervisorStatus, *, as_json: bool) -> None:
    _print_payload(host_codex_supervisor_status_to_dict(status), as_json=as_json)


def _print_payload(payload: dict, *, as_json: bool) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
