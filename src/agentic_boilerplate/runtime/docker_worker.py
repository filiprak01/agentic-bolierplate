"""Role-specific Docker worker runtime loop."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentic_boilerplate.config import PlatformSettings
from agentic_boilerplate.domain import (
    DEFAULT_ASSIGNMENT_LOCK_STALE_AFTER_SECONDS,
    AgentRole,
    AssignmentLockDecision,
    AssignmentLockStatus,
    CodexEffortMode,
    SharedDurablePath,
    WorkspaceProvisioningMode,
    acquire_assignment_lock,
    assignment_with_workspace_path,
    assignment_workspace_plan_to_dict,
    build_assignment_workspace_plan,
    evaluate_assignment_lock_request,
)
from agentic_boilerplate.domain.assignment_workspace import AssignmentWorkspacePlan
from agentic_boilerplate.domain.agent_assignment import (
    AgentAssignment,
    AgentRegistry,
    AssignmentStatus,
    WorkerInstance,
    WorkerStatus,
)
from agentic_boilerplate.domain.detached_worker_checkpoint import (
    DetachedWorkerCheckpoint,
    DetachedWorkerCheckpointStage,
    DetachedWorkerResumeAction,
)
from agentic_boilerplate.domain.codex_limit_availability import (
    CodexLimitAvailabilityRecord,
    CodexLimitGateDecision,
    CodexLimitRecommendedAction,
    decide_codex_limit_gate,
)
from agentic_boilerplate.domain.worker_instruction_bundle import (
    WorkerInstructionBundleValidation,
    format_worker_instruction_bundle_validation,
    validate_worker_instruction_bundle,
    worker_instruction_failure_reason,
)
from agentic_boilerplate.integrations.git_ssh_auth import (
    GitSSHRuntimeEnvironment,
    git_ssh_auth_config_from_settings,
    prepare_git_ssh_runtime_environment,
    redacted_git_ssh_runtime_summary,
)
from agentic_boilerplate.runtime.startup import StartupValidationResult, format_startup_checklist, validate_startup
from agentic_boilerplate.runtime.codex_execution_bridge import HostSideCodexExecutionBridge
from agentic_boilerplate.storage import (
    DuplicateActiveAssignmentLockError,
    FileAgentAssignmentStore,
    FileAssignmentLockStore,
    FileCodexJobStore,
    FileCodexLimitAvailabilityStore,
    FileCodexPauseStore,
    FileDetachedWorkerCheckpointStore,
)

DOCKER_WORKER_ROLES: tuple[AgentRole, ...] = (
    AgentRole.PRODUCT_PLANNING,
    AgentRole.ARCHITECTURE,
    AgentRole.DEVELOPER,
    AgentRole.REVIEW,
    AgentRole.TESTER,
    AgentRole.RELEASE_MANAGER,
    AgentRole.SCHEDULER,
    AgentRole.PLATFORM,
    AgentRole.FRONTEND,
    AgentRole.UI_UX,
    AgentRole.SECURITY,
    AgentRole.DOCS_CONFLUENCE,
    AgentRole.DEVOPS_PLATFORM,
    AgentRole.DATA_PERSISTENCE,
)

MVP_DOCKER_WORKER_ROLES: tuple[AgentRole, ...] = DOCKER_WORKER_ROLES
_DISABLE_RUNTIME_STALE_REPLACEMENT_SECONDS = 100 * 365 * 24 * 60 * 60


@dataclass(frozen=True)
class DockerWorkerRunResult:
    """One visible worker loop iteration outcome."""

    worker_id: str
    role: AgentRole
    startup_passed: bool
    worker_status: WorkerStatus
    message: str
    log_path: Path
    assignment_id: str = ""
    assignment_status: AssignmentStatus | None = None
    limit_action: CodexLimitRecommendedAction | None = None
    limit_gate_allowed: bool = True
    limit_gate_reason: str = ""
    assignment_lock_allowed: bool = True
    assignment_lock_reason: str = ""
    assignment_lock_path: Path | None = None
    instruction_gate_allowed: bool = True
    instruction_gate_reason: str = ""
    resume_after: str = ""
    dry_run: bool = True
    workspace_path: str = ""
    workspace_gate_allowed: bool = True
    workspace_gate_reason: str = ""
    checkpoint_path: Path | None = None
    evidence_path: Path | None = None
    codex_job_path: Path | None = None
    failed_request_path: Path | None = None
    git_ssh_enabled: bool = False
    git_ssh_key_source: str = ""


def run_docker_worker_once(
    settings: PlatformSettings,
    *,
    role: AgentRole | str,
    worker_id: str = "",
    container_name: str = "",
    workspace_path: str = "",
    dry_run: bool = True,
    check_integrations: bool = False,
    assignment_store_root: Path | str | None = None,
    lock_store_root: Path | str | None = None,
    limit_store_root: Path | str | None = None,
    logs_root: Path | str | None = None,
    checkpoint_store_root: Path | str | None = None,
    instruction_root: Path | str | None = None,
    codex_execution_mode: str = "host_side",
    now: Callable[[], str] | None = None,
) -> DockerWorkerRunResult:
    """Register one Docker worker and poll one assignment without live side effects by default."""

    role_value = _coerce_role(role)
    timestamp = (now or _utc_now)()
    worker_id = worker_id.strip() or f"{role_value.value}-worker"
    container_name = container_name.strip() or os.environ.get("HOSTNAME", "")
    workspace_path = workspace_path.strip() or settings.workers.target_project_path or "/workspace"
    assignment_store = FileAgentAssignmentStore(assignment_store_root or settings.paths.agent_state)
    lock_store = FileAssignmentLockStore(lock_store_root or settings.paths.agent_state)
    checkpoint_store = FileDetachedWorkerCheckpointStore(checkpoint_store_root or settings.paths.agent_state)
    limit_store = FileCodexLimitAvailabilityStore(limit_store_root or settings.paths.codex_limits)
    log_root = Path(logs_root or settings.paths.agent_logs)
    log_path = log_root / role_value.value / f"{worker_id}.log"

    startup = validate_startup(settings, check_integrations=check_integrations)
    configured_roles = set(settings.workers.roles)
    role_configured = role_value.value in configured_roles
    limit_record = _latest_limit_record(
        limit_store,
        account_scope_id=settings.codex_limit_sentinel.account_scope_id,
        bucket_id=settings.codex_limit_sentinel.bucket_id,
    )
    limit_action = limit_record.recommended_action if limit_record else None
    instructions_root = Path(instruction_root or ".")

    if not startup.passed:
        worker = WorkerInstance(
            id=worker_id,
            role=role_value,
            status=WorkerStatus.OFFLINE,
            display_name=f"{role_value.value} Docker worker",
            container_name=container_name,
            workspace_path=workspace_path,
            registered_at=timestamp,
            updated_at=timestamp,
        )
        _save_worker_and_registry(assignment_store, worker, timestamp)
        message = "Startup validation failed; worker did not accept assignments."
        _write_worker_log(log_path, startup, message, limit_action=limit_action, assignment=None, dry_run=dry_run)
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=False,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            limit_action=limit_action,
            dry_run=dry_run,
        )

    if not role_configured:
        worker = WorkerInstance(
            id=worker_id,
            role=role_value,
            status=WorkerStatus.PAUSED,
            display_name=f"{role_value.value} Docker worker",
            container_name=container_name,
            workspace_path=workspace_path,
            registered_at=timestamp,
            updated_at=timestamp,
        )
        _save_worker_and_registry(assignment_store, worker, timestamp)
        message = "Worker role is supported but not enabled in WORKER_ROLES."
        _write_worker_log(log_path, startup, message, limit_action=limit_action, assignment=None, dry_run=dry_run)
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            limit_action=limit_action,
            dry_run=dry_run,
        )

    git_ssh_runtime = _prepare_git_ssh_runtime(settings, worker_id)
    base_instruction_gate = validate_worker_instruction_bundle(
        role=role_value,
        instruction_root=instructions_root,
        context_packs_root=settings.paths.context_packs,
    )
    if not base_instruction_gate.passed:
        worker = WorkerInstance(
            id=worker_id,
            role=role_value,
            status=WorkerStatus.PAUSED,
            display_name=f"{role_value.value} Docker worker",
            container_name=container_name,
            workspace_path=workspace_path,
            registered_at=timestamp,
            updated_at=timestamp,
        )
        _save_worker_and_registry(assignment_store, worker, timestamp)
        reason = worker_instruction_failure_reason(base_instruction_gate)
        message = f"Instruction/context gate failed; worker did not accept assignments. {reason}"
        _write_worker_log(
            log_path,
            startup,
            message,
            limit_action=limit_action,
            assignment=None,
            dry_run=dry_run,
            instruction_gate=base_instruction_gate,
            git_ssh_runtime=git_ssh_runtime,
        )
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            limit_action=limit_action,
            instruction_gate_allowed=False,
            instruction_gate_reason=reason,
            dry_run=dry_run,
            git_ssh_enabled=git_ssh_runtime.enabled,
            git_ssh_key_source=git_ssh_runtime.key_source,
        )

    assignment = _next_queued_assignment(assignment_store, role_value)
    if assignment is None:
        worker = WorkerInstance(
            id=worker_id,
            role=role_value,
            status=WorkerStatus.AVAILABLE,
            display_name=f"{role_value.value} Docker worker",
            container_name=container_name,
            workspace_path=workspace_path,
            registered_at=timestamp,
            updated_at=timestamp,
        )
        _save_worker_and_registry(assignment_store, worker, timestamp)
        message = "Worker started, validated configuration, and found no queued assignment for its role."
        _write_worker_log(
            log_path,
            startup,
            message,
            limit_action=limit_action,
            assignment=None,
            dry_run=dry_run,
            instruction_gate=base_instruction_gate,
            git_ssh_runtime=git_ssh_runtime,
        )
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            limit_action=limit_action,
            dry_run=dry_run,
            git_ssh_enabled=git_ssh_runtime.enabled,
            git_ssh_key_source=git_ssh_runtime.key_source,
        )

    worker = WorkerInstance(
        id=worker_id,
        role=role_value,
        status=WorkerStatus.PAUSED,
        display_name=f"{role_value.value} Docker worker",
        container_name=container_name,
        workspace_path=workspace_path,
        registered_at=timestamp,
        updated_at=timestamp,
    )
    assignment_instruction_gate = validate_worker_instruction_bundle(
        role=role_value,
        instruction_root=instructions_root,
        context_packs_root=settings.paths.context_packs,
        assignment_context_pack_path=assignment.paths.context_pack_path,
    )
    if not assignment_instruction_gate.passed:
        _save_worker_and_registry(assignment_store, worker, timestamp)
        reason = worker_instruction_failure_reason(assignment_instruction_gate)
        message = f"Queued assignment was blocked by instruction/context gate: {reason}"
        _write_worker_log(
            log_path,
            startup,
            message,
            limit_action=limit_action,
            assignment=assignment,
            dry_run=dry_run,
            instruction_gate=assignment_instruction_gate,
            git_ssh_runtime=git_ssh_runtime,
        )
        evidence_path = _write_assignment_evidence(
            log_root,
            role_value=role_value,
            worker_id=worker_id,
            assignment=assignment,
            message=message,
            stage=DetachedWorkerCheckpointStage.CONTEXT_LOADED,
            dry_run=dry_run,
            limit_gate=None,
            instruction_gate=assignment_instruction_gate,
            codex_job_path=None,
            failed_request_path=None,
            git_ssh_runtime=git_ssh_runtime,
        )
        checkpoint_path = _write_assignment_checkpoint(
            checkpoint_store,
            assignment=assignment,
            worker_id=worker_id,
            role_value=role_value,
            project_id=settings.jira.project_key,
            workspace_path=workspace_path,
            stage=DetachedWorkerCheckpointStage.CONTEXT_LOADED,
            last_command=_worker_command_summary(
                role_value,
                dry_run=dry_run,
                codex_execution_mode=codex_execution_mode,
            ),
            resume_action=DetachedWorkerResumeAction.REBUILD_CONTEXT,
            resume_recommendation=reason,
            timestamp=timestamp,
            evidence_path=evidence_path,
        )
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            assignment_id=assignment.id,
            assignment_status=assignment.status,
            limit_action=limit_action,
            instruction_gate_allowed=False,
            instruction_gate_reason=reason,
            dry_run=dry_run,
            checkpoint_path=checkpoint_path,
            evidence_path=Path(evidence_path),
            git_ssh_enabled=git_ssh_runtime.enabled,
            git_ssh_key_source=git_ssh_runtime.key_source,
        )

    stale_after_seconds = settings.codex_limit_sentinel.stale_after_seconds
    limit_gate = decide_codex_limit_gate(
        limit_record,
        now=timestamp,
        stale_after_seconds=stale_after_seconds if stale_after_seconds > 0 else None,
        future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
    )
    if not limit_gate.allowed:
        _save_worker_and_registry(assignment_store, worker, timestamp)
        message = f"Queued assignment was blocked by Codex limit gate: {limit_gate.reason}"
        _write_worker_log(
            log_path,
            startup,
            message,
            limit_action=limit_gate.action,
            assignment=assignment,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            git_ssh_runtime=git_ssh_runtime,
        )
        evidence_path = _write_assignment_evidence(
            log_root,
            role_value=role_value,
            worker_id=worker_id,
            assignment=assignment,
            message=message,
            stage=DetachedWorkerCheckpointStage.LIMIT_CHECKED,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            codex_job_path=None,
            failed_request_path=None,
            git_ssh_runtime=git_ssh_runtime,
        )
        checkpoint_path = _write_assignment_checkpoint(
            checkpoint_store,
            assignment=assignment,
            worker_id=worker_id,
            role_value=role_value,
            project_id=settings.jira.project_key,
            workspace_path=workspace_path,
            stage=DetachedWorkerCheckpointStage.LIMIT_CHECKED,
            last_command=_worker_command_summary(
                role_value,
                dry_run=dry_run,
                codex_execution_mode=codex_execution_mode,
            ),
            resume_action=_resume_action_from_limit_gate(limit_gate),
            resume_recommendation=limit_gate.reason,
            timestamp=timestamp,
            evidence_path=evidence_path,
            resume_after=limit_gate.resume_after,
        )
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            assignment_id=assignment.id,
            assignment_status=assignment.status,
            limit_action=limit_gate.action,
            limit_gate_allowed=False,
            limit_gate_reason=limit_gate.reason,
            resume_after=limit_gate.resume_after,
            dry_run=dry_run,
            checkpoint_path=checkpoint_path,
            evidence_path=Path(evidence_path),
            git_ssh_enabled=git_ssh_runtime.enabled,
            git_ssh_key_source=git_ssh_runtime.key_source,
        )

    workspace_assignment = _assignment_with_workspace_defaults(
        assignment,
        settings=settings,
        fallback_project_root=workspace_path,
    )
    workspace_plan = build_assignment_workspace_plan(
        workspace_assignment,
        workspaces_root=str(settings.paths.agent_workspaces),
        durable_paths=_shared_durable_paths(settings),
        mode=WorkspaceProvisioningMode.GIT_WORKTREE,
        base_branch=settings.github.default_branch,
        credentials_available=_git_credentials_available(settings, git_ssh_runtime),
    )
    if not workspace_plan.can_provision:
        _save_worker_and_registry(assignment_store, worker, timestamp)
        reason = _workspace_gate_reason(workspace_plan)
        message = f"Queued assignment was blocked by workspace provisioning gate: {reason}"
        _write_worker_log(
            log_path,
            startup,
            message,
            limit_action=limit_gate.action,
            assignment=workspace_assignment,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            workspace_plan=workspace_plan,
            git_ssh_runtime=git_ssh_runtime,
        )
        evidence_path = _write_assignment_evidence(
            log_root,
            role_value=role_value,
            worker_id=worker_id,
            assignment=workspace_assignment,
            message=message,
            stage=DetachedWorkerCheckpointStage.WORKSPACE_READY,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            codex_job_path=None,
            failed_request_path=None,
            workspace_plan=workspace_plan,
            git_ssh_runtime=git_ssh_runtime,
        )
        checkpoint_path = _write_assignment_checkpoint(
            checkpoint_store,
            assignment=workspace_assignment,
            worker_id=worker_id,
            role_value=role_value,
            project_id=settings.jira.project_key,
            workspace_path=workspace_plan.workspace_path or workspace_path,
            stage=DetachedWorkerCheckpointStage.WORKSPACE_READY,
            last_command=_worker_command_summary(
                role_value,
                dry_run=dry_run,
                codex_execution_mode=codex_execution_mode,
            ),
            resume_action=DetachedWorkerResumeAction.RECHECK_GATES,
            resume_recommendation=message,
            timestamp=timestamp,
            evidence_path=evidence_path,
        )
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            assignment_id=assignment.id,
            assignment_status=assignment.status,
            limit_action=limit_gate.action,
            limit_gate_allowed=limit_gate.allowed,
            limit_gate_reason=limit_gate.reason,
            workspace_path=workspace_plan.workspace_path,
            workspace_gate_allowed=False,
            workspace_gate_reason=reason,
            resume_after=limit_gate.resume_after,
            dry_run=dry_run,
            checkpoint_path=checkpoint_path,
            evidence_path=Path(evidence_path),
            git_ssh_enabled=git_ssh_runtime.enabled,
            git_ssh_key_source=git_ssh_runtime.key_source,
        )

    assignment = assignment_with_workspace_path(workspace_assignment, workspace_plan)
    workspace_path = workspace_plan.workspace_path

    existing_lock = lock_store.active_lock_for(assignment.jira_issue_key, role_value)
    lock_decision = evaluate_assignment_lock_request(
        jira_issue_key=assignment.jira_issue_key,
        role=role_value,
        worker_session_id=worker_id,
        requested_at=timestamp,
        dependency_gate_passed=True,
        existing_lock=existing_lock,
        # Runtime workers do not silently replace active stale locks. Operators
        # must mark/release stale locks through the CLI so recovery has evidence.
        stale_after_seconds=_DISABLE_RUNTIME_STALE_REPLACEMENT_SECONDS,
    )
    if not lock_decision.allowed:
        _save_worker_and_registry(assignment_store, worker, timestamp)
        message = "Queued assignment was blocked by assignment lock: " + "; ".join(lock_decision.reasons)
        _write_worker_log(
            log_path,
            startup,
            message,
            limit_action=limit_gate.action,
            assignment=assignment,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            assignment_lock=lock_decision,
            workspace_plan=workspace_plan,
            git_ssh_runtime=git_ssh_runtime,
        )
        evidence_path = _write_assignment_evidence(
            log_root,
            role_value=role_value,
            worker_id=worker_id,
            assignment=assignment,
            message=message,
            stage=DetachedWorkerCheckpointStage.ASSIGNMENT_CLAIMED,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            codex_job_path=None,
            failed_request_path=None,
            assignment_lock=lock_decision,
            assignment_lock_path=None,
            workspace_plan=workspace_plan,
            git_ssh_runtime=git_ssh_runtime,
        )
        checkpoint_path = _write_assignment_checkpoint(
            checkpoint_store,
            assignment=assignment,
            worker_id=worker_id,
            role_value=role_value,
            project_id=settings.jira.project_key,
            workspace_path=workspace_path,
            stage=DetachedWorkerCheckpointStage.ASSIGNMENT_CLAIMED,
            last_command=_worker_command_summary(
                role_value,
                dry_run=dry_run,
                codex_execution_mode=codex_execution_mode,
            ),
            resume_action=DetachedWorkerResumeAction.RECHECK_GATES,
            resume_recommendation=message,
            timestamp=timestamp,
            evidence_path=evidence_path,
        )
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            assignment_id=assignment.id,
            assignment_status=assignment.status,
            limit_action=limit_gate.action,
            limit_gate_allowed=limit_gate.allowed,
            limit_gate_reason=limit_gate.reason,
            assignment_lock_allowed=False,
            assignment_lock_reason="; ".join(lock_decision.reasons),
            workspace_path=workspace_path,
            workspace_gate_allowed=True,
            resume_after=limit_gate.resume_after,
            dry_run=dry_run,
            checkpoint_path=checkpoint_path,
            evidence_path=Path(evidence_path),
            git_ssh_enabled=git_ssh_runtime.enabled,
            git_ssh_key_source=git_ssh_runtime.key_source,
        )

    assignment_lock_path: Path | None = None
    if not dry_run:
        if existing_lock is not None and existing_lock.worker_session_id == worker_id:
            assignment_lock_path = lock_store.lock_path(assignment.jira_issue_key, role_value, worker_id)
        else:
            lock = acquire_assignment_lock(
                jira_issue_key=assignment.jira_issue_key,
                role=role_value,
                worker_session_id=worker_id,
                acquired_at=timestamp,
                dependency_gate_passed=True,
                workspace_path=workspace_path,
                expires_at=_lock_expires_at(timestamp),
            )
            try:
                assignment_lock_path = lock_store.create_lock(lock).path
            except DuplicateActiveAssignmentLockError:
                race_lock = lock_store.active_lock_for(assignment.jira_issue_key, role_value)
                race_decision = evaluate_assignment_lock_request(
                    jira_issue_key=assignment.jira_issue_key,
                    role=role_value,
                    worker_session_id=worker_id,
                    requested_at=timestamp,
                    dependency_gate_passed=True,
                    existing_lock=race_lock,
                    stale_after_seconds=_DISABLE_RUNTIME_STALE_REPLACEMENT_SECONDS,
                )
                _save_worker_and_registry(assignment_store, worker, timestamp)
                message = "Queued assignment was blocked by assignment lock: " + "; ".join(race_decision.reasons)
                _write_worker_log(
                    log_path,
                    startup,
                    message,
                    limit_action=limit_gate.action,
                    assignment=assignment,
                    dry_run=dry_run,
                    limit_gate=limit_gate,
                    instruction_gate=assignment_instruction_gate,
                    assignment_lock=race_decision,
                    workspace_plan=workspace_plan,
                    git_ssh_runtime=git_ssh_runtime,
                )
                evidence_path = _write_assignment_evidence(
                    log_root,
                    role_value=role_value,
                    worker_id=worker_id,
                    assignment=assignment,
                    message=message,
                    stage=DetachedWorkerCheckpointStage.ASSIGNMENT_CLAIMED,
                    dry_run=dry_run,
                    limit_gate=limit_gate,
                    instruction_gate=assignment_instruction_gate,
                    codex_job_path=None,
                    failed_request_path=None,
                    assignment_lock=race_decision,
                    assignment_lock_path=None,
                    workspace_plan=workspace_plan,
                    git_ssh_runtime=git_ssh_runtime,
                )
                checkpoint_path = _write_assignment_checkpoint(
                    checkpoint_store,
                    assignment=assignment,
                    worker_id=worker_id,
                    role_value=role_value,
                    project_id=settings.jira.project_key,
                    workspace_path=workspace_path,
                    stage=DetachedWorkerCheckpointStage.ASSIGNMENT_CLAIMED,
                    last_command=_worker_command_summary(
                        role_value,
                        dry_run=dry_run,
                        codex_execution_mode=codex_execution_mode,
                    ),
                    resume_action=DetachedWorkerResumeAction.RECHECK_GATES,
                    resume_recommendation=message,
                    timestamp=timestamp,
                    evidence_path=evidence_path,
                )
                return DockerWorkerRunResult(
                    worker_id=worker_id,
                    role=role_value,
                    startup_passed=True,
                    worker_status=worker.status,
                    message=message,
                    log_path=log_path,
                    assignment_id=assignment.id,
                    assignment_status=assignment.status,
                    limit_action=limit_gate.action,
                    limit_gate_allowed=limit_gate.allowed,
                    limit_gate_reason=limit_gate.reason,
                    assignment_lock_allowed=False,
                    assignment_lock_reason="; ".join(race_decision.reasons),
                    workspace_path=workspace_path,
                    workspace_gate_allowed=True,
                    resume_after=limit_gate.resume_after,
                    dry_run=dry_run,
                    checkpoint_path=checkpoint_path,
                    evidence_path=Path(evidence_path),
                    git_ssh_enabled=git_ssh_runtime.enabled,
                    git_ssh_key_source=git_ssh_runtime.key_source,
                )

    if dry_run:
        worker = WorkerInstance(
            id=worker_id,
            role=role_value,
            status=WorkerStatus.PAUSED,
            display_name=f"{role_value.value} Docker worker",
            container_name=container_name,
            workspace_path=workspace_path,
            current_assignment_id=assignment.id,
            registered_at=timestamp,
            updated_at=timestamp,
        )
        _save_worker_and_registry(assignment_store, worker, timestamp)
        message = "Queued assignment was observed and left unchanged because dry-run mode does not execute Codex-backed work."
        _write_worker_log(
            log_path,
            startup,
            message,
            limit_action=limit_gate.action,
            assignment=assignment,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            assignment_lock=lock_decision,
            workspace_plan=workspace_plan,
            git_ssh_runtime=git_ssh_runtime,
        )
        evidence_path = _write_assignment_evidence(
            log_root,
            role_value=role_value,
            worker_id=worker_id,
            assignment=assignment,
            message=message,
            stage=DetachedWorkerCheckpointStage.LIMIT_CHECKED,
            dry_run=dry_run,
            limit_gate=limit_gate,
            instruction_gate=assignment_instruction_gate,
            codex_job_path=None,
            failed_request_path=None,
            assignment_lock=lock_decision,
            assignment_lock_path=None,
            workspace_plan=workspace_plan,
            git_ssh_runtime=git_ssh_runtime,
        )
        checkpoint_path = _write_assignment_checkpoint(
            checkpoint_store,
            assignment=assignment,
            worker_id=worker_id,
            role_value=role_value,
            project_id=settings.jira.project_key,
            workspace_path=workspace_path,
            stage=DetachedWorkerCheckpointStage.LIMIT_CHECKED,
            last_command=_worker_command_summary(
                role_value,
                dry_run=dry_run,
                codex_execution_mode=codex_execution_mode,
            ),
            resume_action=DetachedWorkerResumeAction.RECHECK_GATES,
            resume_recommendation=(
                "Dry-run observed one eligible assignment. Re-run with --execute to create a host-side Codex job."
            ),
            timestamp=timestamp,
            evidence_path=evidence_path,
            codex_job_id=assignment.codex_job_id,
        )
        return DockerWorkerRunResult(
            worker_id=worker_id,
            role=role_value,
            startup_passed=True,
            worker_status=worker.status,
            message=message,
            log_path=log_path,
            assignment_id=assignment.id,
            assignment_status=assignment.status,
            limit_action=limit_gate.action,
            limit_gate_allowed=limit_gate.allowed,
            limit_gate_reason=limit_gate.reason,
            assignment_lock_allowed=lock_decision.allowed,
            assignment_lock_reason="; ".join(lock_decision.reasons),
            workspace_path=workspace_path,
            workspace_gate_allowed=True,
            resume_after=limit_gate.resume_after,
            dry_run=dry_run,
            checkpoint_path=checkpoint_path,
            evidence_path=Path(evidence_path),
            git_ssh_enabled=git_ssh_runtime.enabled,
            git_ssh_key_source=git_ssh_runtime.key_source,
        )

    bridge = HostSideCodexExecutionBridge(
        assignment_store=assignment_store,
        job_store=FileCodexJobStore(settings.paths.codex_jobs),
        pause_store=FileCodexPauseStore(settings.paths.codex_jobs),
        mode=codex_execution_mode,
    )
    bridge_outcome = bridge.create_request(
        assignment,
        worker_id=worker_id,
        target_repo_path=workspace_path,
        model=settings.codex.default_model,
        reasoning=settings.codex.default_reasoning,
        speed=settings.codex.default_speed,
        effort_mode=CodexEffortMode.STANDARD,
        created_at=timestamp,
    )
    worker = WorkerInstance(
        id=worker_id,
        role=role_value,
        status=WorkerStatus.ASSIGNED if bridge_outcome.status is AssignmentStatus.ASSIGNED else WorkerStatus.PAUSED,
        display_name=f"{role_value.value} Docker worker",
        container_name=container_name,
        workspace_path=workspace_path,
        current_assignment_id=assignment.id if bridge_outcome.status is AssignmentStatus.ASSIGNED else "",
        registered_at=timestamp,
        updated_at=timestamp,
    )
    _save_worker_and_registry(assignment_store, worker, timestamp)
    message = bridge_outcome.message
    _write_worker_log(
        log_path,
        startup,
        message,
        limit_action=limit_gate.action,
        assignment=bridge_outcome.assignment,
        dry_run=dry_run,
        limit_gate=limit_gate,
        instruction_gate=assignment_instruction_gate,
        assignment_lock=lock_decision,
        assignment_lock_path=assignment_lock_path,
        workspace_plan=workspace_plan,
        git_ssh_runtime=git_ssh_runtime,
    )
    stage = (
        DetachedWorkerCheckpointStage.CODEX_JOB_CREATED
        if bridge_outcome.codex_job_path
        else DetachedWorkerCheckpointStage.FAILED
    )
    resume_action = (
        DetachedWorkerResumeAction.NONE
        if bridge_outcome.codex_job_path
        else DetachedWorkerResumeAction.MANUAL_RECOVERY
    )
    codex_job_path = str(bridge_outcome.codex_job_path) if bridge_outcome.codex_job_path else ""
    failed_request_path = str(bridge_outcome.failed_request_path) if bridge_outcome.failed_request_path else ""
    evidence_path = _write_assignment_evidence(
        log_root,
        role_value=role_value,
        worker_id=worker_id,
        assignment=bridge_outcome.assignment,
        message=message,
        stage=stage,
        dry_run=dry_run,
        limit_gate=limit_gate,
        instruction_gate=assignment_instruction_gate,
        codex_job_path=codex_job_path,
        failed_request_path=failed_request_path,
        assignment_lock=lock_decision,
        assignment_lock_path=assignment_lock_path,
        workspace_plan=workspace_plan,
        git_ssh_runtime=git_ssh_runtime,
    )
    checkpoint_path = _write_assignment_checkpoint(
        checkpoint_store,
        assignment=bridge_outcome.assignment,
        worker_id=worker_id,
        role_value=role_value,
        project_id=settings.jira.project_key,
        workspace_path=workspace_path,
        stage=stage,
        last_command=_worker_command_summary(
            role_value,
            dry_run=dry_run,
            codex_execution_mode=codex_execution_mode,
        ),
        resume_action=resume_action,
        resume_recommendation=message,
        timestamp=timestamp,
        evidence_path=evidence_path,
        codex_job_id=bridge_outcome.assignment.codex_job_id,
        failed_request_path=failed_request_path,
        output_path=bridge_outcome.assignment.paths.output_path,
    )
    return DockerWorkerRunResult(
        worker_id=worker_id,
        role=role_value,
        startup_passed=True,
        worker_status=worker.status,
        message=message,
        log_path=log_path,
        assignment_id=assignment.id,
        assignment_status=bridge_outcome.assignment.status,
        limit_action=limit_gate.action,
        limit_gate_allowed=limit_gate.allowed,
        limit_gate_reason=limit_gate.reason,
        assignment_lock_allowed=lock_decision.allowed,
        assignment_lock_reason="; ".join(lock_decision.reasons),
        assignment_lock_path=assignment_lock_path,
        workspace_path=workspace_path,
        workspace_gate_allowed=True,
        resume_after=limit_gate.resume_after,
        dry_run=dry_run,
        checkpoint_path=checkpoint_path,
        evidence_path=Path(evidence_path),
        codex_job_path=bridge_outcome.codex_job_path,
        failed_request_path=bridge_outcome.failed_request_path,
        git_ssh_enabled=git_ssh_runtime.enabled,
        git_ssh_key_source=git_ssh_runtime.key_source,
    )


def docker_worker_run_result_to_dict(result: DockerWorkerRunResult) -> dict[str, object]:
    """Convert a worker run result into JSON-safe CLI output."""

    return {
        "worker_id": result.worker_id,
        "role": result.role.value,
        "startup_passed": result.startup_passed,
        "worker_status": result.worker_status.value,
        "message": result.message,
        "log_path": str(result.log_path),
        "assignment_id": result.assignment_id,
        "assignment_status": result.assignment_status.value if result.assignment_status else "",
        "limit_action": result.limit_action.value if result.limit_action else "",
        "limit_gate_allowed": result.limit_gate_allowed,
        "limit_gate_reason": result.limit_gate_reason,
        "assignment_lock_allowed": result.assignment_lock_allowed,
        "assignment_lock_reason": result.assignment_lock_reason,
        "assignment_lock_path": str(result.assignment_lock_path) if result.assignment_lock_path else "",
        "instruction_gate_allowed": result.instruction_gate_allowed,
        "instruction_gate_reason": result.instruction_gate_reason,
        "workspace_path": result.workspace_path,
        "workspace_gate_allowed": result.workspace_gate_allowed,
        "workspace_gate_reason": result.workspace_gate_reason,
        "resume_after": result.resume_after,
        "dry_run": result.dry_run,
        "checkpoint_path": str(result.checkpoint_path) if result.checkpoint_path else "",
        "evidence_path": str(result.evidence_path) if result.evidence_path else "",
        "codex_job_path": str(result.codex_job_path) if result.codex_job_path else "",
        "failed_request_path": str(result.failed_request_path) if result.failed_request_path else "",
        "git_ssh_enabled": result.git_ssh_enabled,
        "git_ssh_key_source": result.git_ssh_key_source,
    }


def _coerce_role(role: AgentRole | str) -> AgentRole:
    if isinstance(role, AgentRole):
        return role
    return AgentRole(str(role).strip())


def _next_queued_assignment(store: FileAgentAssignmentStore, role: AgentRole) -> AgentAssignment | None:
    for assignment in store.list_assignments():
        if assignment.role == role and assignment.status == AssignmentStatus.QUEUED:
            return assignment
    return None


def _latest_limit_record(
    store: FileCodexLimitAvailabilityStore,
    *,
    account_scope_id: str = "",
    bucket_id: str = "",
) -> CodexLimitAvailabilityRecord | None:
    return store.latest_record(
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )


def _prepare_git_ssh_runtime(settings: PlatformSettings, worker_id: str) -> GitSSHRuntimeEnvironment:
    ssh_root = os.environ.get("AGENTIC_GIT_SSH_DIR", "").strip()
    ssh_dir = Path(ssh_root) if ssh_root else Path("/tmp/agentic-git-ssh") / worker_id
    return prepare_git_ssh_runtime_environment(
        git_ssh_auth_config_from_settings(settings),
        ssh_dir=ssh_dir,
    )


def _assignment_with_workspace_defaults(
    assignment: AgentAssignment,
    *,
    settings: PlatformSettings,
    fallback_project_root: str,
) -> AgentAssignment:
    return replace(
        assignment,
        project_root=assignment.project_root or fallback_project_root or settings.workers.target_project_path,
        repository=assignment.repository or settings.github.repository,
        jira_project_key=assignment.jira_project_key or settings.jira.project_key,
    )


def _shared_durable_paths(settings: PlatformSettings) -> tuple[SharedDurablePath, ...]:
    return (
        SharedDurablePath(name="po-inbox", path=str(settings.paths.po_inbox)),
        SharedDurablePath(name="agent-logs", path=str(settings.paths.agent_logs)),
        SharedDurablePath(name="agent-state", path=str(settings.paths.agent_state)),
        SharedDurablePath(name="codex-limits", path=str(settings.paths.codex_limits)),
        SharedDurablePath(name="codex-jobs", path=str(settings.paths.codex_jobs)),
        SharedDurablePath(name="codex-results", path=str(settings.paths.codex_results)),
        SharedDurablePath(name="context-packs", path=str(settings.paths.context_packs)),
    )


def _git_credentials_available(settings: PlatformSettings, runtime: GitSSHRuntimeEnvironment) -> bool:
    return bool(settings.github.token or runtime.enabled or settings.github.auth_mode == "local")


def _workspace_gate_reason(plan: AssignmentWorkspacePlan) -> str:
    if plan.can_provision:
        return "Workspace provisioning plan is valid."
    return "; ".join(f"{issue.kind.value}: {issue.message}" for issue in plan.issues)


def _save_worker_and_registry(store: FileAgentAssignmentStore, worker: WorkerInstance, timestamp: str) -> None:
    store.save_worker(worker)
    registry = AgentRegistry(
        id="docker-workers",
        workers=store.list_workers(),
        assignments=store.list_assignments(),
        created_at=timestamp,
        updated_at=timestamp,
    )
    store.save_registry(registry)


def _write_worker_log(
    path: Path,
    startup: StartupValidationResult,
    message: str,
    *,
    limit_action: CodexLimitRecommendedAction | None,
    assignment: AgentAssignment | None,
    dry_run: bool,
    limit_gate: CodexLimitGateDecision | None = None,
    instruction_gate: WorkerInstructionBundleValidation | None = None,
    assignment_lock: AssignmentLockDecision | None = None,
    assignment_lock_path: Path | None = None,
    workspace_plan: AssignmentWorkspacePlan | None = None,
    git_ssh_runtime: GitSSHRuntimeEnvironment | None = None,
) -> None:
    payload = {
        "message": message,
        "dry_run": dry_run,
        "startup_passed": startup.passed,
        "startup_checklist": format_startup_checklist(startup),
        "limit_action": limit_action.value if limit_action else "",
        "limit_gate_allowed": limit_gate.allowed if limit_gate else "",
        "limit_gate_reason": limit_gate.reason if limit_gate else "",
        "instruction_gate_allowed": instruction_gate.passed if instruction_gate else "",
        "instruction_gate_reason": worker_instruction_failure_reason(instruction_gate) if instruction_gate else "",
        "instruction_checklist": (
            format_worker_instruction_bundle_validation(instruction_gate) if instruction_gate else ""
        ),
        "assignment_lock_allowed": assignment_lock.allowed if assignment_lock else "",
        "assignment_lock_reason": "; ".join(assignment_lock.reasons) if assignment_lock else "",
        "assignment_lock_path": str(assignment_lock_path) if assignment_lock_path else "",
        "workspace_path": workspace_plan.workspace_path if workspace_plan else "",
        "workspace_gate_allowed": workspace_plan.can_provision if workspace_plan else "",
        "workspace_gate_reason": _workspace_gate_reason(workspace_plan) if workspace_plan else "",
        "workspace_plan": assignment_workspace_plan_to_dict(workspace_plan) if workspace_plan else {},
        "resume_after": limit_gate.resume_after if limit_gate else "",
        "assignment_id": assignment.id if assignment else "",
        "assignment_status": assignment.status.value if assignment else "",
        "git_ssh": redacted_git_ssh_runtime_summary(git_ssh_runtime) if git_ssh_runtime else {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_assignment_evidence(
    log_root: Path,
    *,
    role_value: AgentRole,
    worker_id: str,
    assignment: AgentAssignment,
    message: str,
    stage: DetachedWorkerCheckpointStage,
    dry_run: bool,
    limit_gate: CodexLimitGateDecision | None,
    instruction_gate: WorkerInstructionBundleValidation | None,
    codex_job_path: str | None,
    failed_request_path: str | None,
    assignment_lock: AssignmentLockDecision | None = None,
    assignment_lock_path: Path | None = None,
    workspace_plan: AssignmentWorkspacePlan | None = None,
    git_ssh_runtime: GitSSHRuntimeEnvironment | None = None,
) -> str:
    evidence_path = log_root / role_value.value / assignment.id / "worker-run-evidence.json"
    payload = {
        "assignment_id": assignment.id,
        "assignment_status": assignment.status.value,
        "codex_job_id": assignment.codex_job_id,
        "codex_job_path": codex_job_path or "",
        "context_pack_path": assignment.paths.context_pack_path,
        "dry_run": dry_run,
        "evidence_type": "bounded_worker_assignment",
        "failed_request_path": failed_request_path or "",
        "git_ssh": redacted_git_ssh_runtime_summary(git_ssh_runtime) if git_ssh_runtime else {},
        "instruction_gate_allowed": instruction_gate.passed if instruction_gate else "",
        "instruction_gate_reason": worker_instruction_failure_reason(instruction_gate) if instruction_gate else "",
        "assignment_lock_allowed": assignment_lock.allowed if assignment_lock else "",
        "assignment_lock_reason": "; ".join(assignment_lock.reasons) if assignment_lock else "",
        "assignment_lock_path": str(assignment_lock_path) if assignment_lock_path else "",
        "workspace_path": workspace_plan.workspace_path if workspace_plan else assignment.paths.workspace_path,
        "workspace_gate_allowed": workspace_plan.can_provision if workspace_plan else "",
        "workspace_gate_reason": _workspace_gate_reason(workspace_plan) if workspace_plan else "",
        "workspace_plan": assignment_workspace_plan_to_dict(workspace_plan) if workspace_plan else {},
        "jira_issue_key": assignment.jira_issue_key,
        "limit_action": limit_gate.action.value if limit_gate else "",
        "limit_gate_allowed": limit_gate.allowed if limit_gate else "",
        "limit_gate_reason": limit_gate.reason if limit_gate else "",
        "message": message,
        "output_path": assignment.paths.output_path,
        "resume_after": limit_gate.resume_after if limit_gate else "",
        "role": role_value.value,
        "stage": stage.value,
        "worker_id": worker_id,
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(evidence_path)


def _write_assignment_checkpoint(
    store: FileDetachedWorkerCheckpointStore,
    *,
    assignment: AgentAssignment,
    worker_id: str,
    role_value: AgentRole,
    project_id: str,
    workspace_path: str,
    stage: DetachedWorkerCheckpointStage,
    last_command: str,
    resume_action: DetachedWorkerResumeAction,
    resume_recommendation: str,
    timestamp: str,
    evidence_path: str,
    codex_job_id: str = "",
    failed_request_path: str = "",
    output_path: str = "",
    resume_after: str = "",
) -> Path:
    checkpoint = DetachedWorkerCheckpoint(
        id=f"checkpoint-{assignment.id}-{stage.value}",
        assignment_id=assignment.id,
        worker_id=worker_id,
        role=role_value,
        project_id=project_id or "unknown",
        sprint="unknown",
        jira_issue_key=assignment.jira_issue_key,
        branch_name=assignment.branch_name,
        worktree_path=workspace_path,
        stage=stage,
        last_command=last_command,
        resume_action=resume_action,
        resume_recommendation=resume_recommendation,
        created_at=assignment.started_at or timestamp,
        updated_at=timestamp,
        attempt_count=assignment.attempt_count + 1,
        codex_job_id=codex_job_id or assignment.codex_job_id,
        context_pack_path=assignment.paths.context_pack_path,
        failed_request_path=failed_request_path or assignment.paths.failed_request_path,
        output_path=output_path or assignment.paths.output_path,
        evidence_path=evidence_path,
        resume_after=resume_after,
    )
    return store.write(checkpoint).path


def _resume_action_from_limit_gate(limit_gate: CodexLimitGateDecision) -> DetachedWorkerResumeAction:
    if limit_gate.action is CodexLimitRecommendedAction.WAIT:
        return DetachedWorkerResumeAction.WAIT_FOR_LIMITS
    if limit_gate.action is CodexLimitRecommendedAction.ASK_PRODUCT_OWNER:
        return DetachedWorkerResumeAction.ASK_PRODUCT_OWNER
    if limit_gate.action is CodexLimitRecommendedAction.DOWNGRADE_MODEL:
        return DetachedWorkerResumeAction.MANUAL_RECOVERY
    return DetachedWorkerResumeAction.RECHECK_GATES


def _worker_command_summary(
    role_value: AgentRole,
    *,
    dry_run: bool,
    codex_execution_mode: str,
) -> str:
    execute_flag = "" if dry_run else " --execute"
    return f"agentic worker run-once --role {role_value.value}{execute_flag} --codex-execution-mode {codex_execution_mode}"


def _lock_expires_at(acquired_at: str) -> str:
    text = acquired_at[:-1] + "+00:00" if acquired_at.endswith("Z") else acquired_at
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    expires = parsed.astimezone(timezone.utc) + timedelta(seconds=DEFAULT_ASSIGNMENT_LOCK_STALE_AFTER_SECONDS)
    return expires.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
