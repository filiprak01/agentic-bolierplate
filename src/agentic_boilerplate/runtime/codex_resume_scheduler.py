"""Limit-aware scheduler for paused host-side Codex jobs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from agentic_boilerplate.domain import (
    CodexJobArtifact,
    CodexJobStatus,
    CodexLimitGateDecision,
    CodexResumeMetadata,
    decide_codex_limit_gate,
)
from agentic_boilerplate.storage import FileCodexJobStore, FileCodexLimitAvailabilityStore


@dataclass(frozen=True)
class CodexResumeSchedulerResult:
    """Outcome of one paused-job resume scheduling pass."""

    gate: CodexLimitGateDecision
    resumed_job_ids: tuple[str, ...] = ()
    skipped_job_ids: tuple[str, ...] = ()
    next_check_at: str = ""
    reason: str = ""


def resume_paused_limit_jobs(
    *,
    job_store: FileCodexJobStore,
    limit_store: FileCodexLimitAvailabilityStore,
    resumed_at: str,
    eligible_issue_keys: Iterable[str] | None = None,
    stale_after_seconds: int | None = None,
    future_tolerance_seconds: int = 30,
    account_scope_id: str = "",
    bucket_id: str = "",
) -> CodexResumeSchedulerResult:
    """Requeue resumable paused jobs when durable Codex capacity allows work."""

    record = limit_store.latest_record(
        account_scope_id=account_scope_id,
        bucket_id=bucket_id,
    )
    gate = decide_codex_limit_gate(
        record,
        now=resumed_at,
        stale_after_seconds=stale_after_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    paused_jobs = job_store.list_jobs(status=CodexJobStatus.PAUSED_LIMIT)
    if not gate.allowed:
        return CodexResumeSchedulerResult(
            gate=gate,
            skipped_job_ids=tuple(job.id for job in paused_jobs),
            next_check_at=gate.resume_after,
            reason=gate.reason,
        )

    eligible = set(eligible_issue_keys or ())
    resumed: list[str] = []
    skipped: list[str] = []
    for job in paused_jobs:
        if eligible and job.jira_issue_key not in eligible:
            skipped.append(job.id)
            continue
        if not job.resume.resumable:
            skipped.append(job.id)
            continue
        job_store.write(_requeue_job(job, resumed_at=resumed_at))
        resumed.append(job.id)

    return CodexResumeSchedulerResult(
        gate=gate,
        resumed_job_ids=tuple(resumed),
        skipped_job_ids=tuple(skipped),
        reason="Codex limit availability allows paused jobs to resume.",
    )


def codex_resume_scheduler_result_to_dict(result: CodexResumeSchedulerResult) -> dict[str, object]:
    """Convert scheduler result into CLI/API-friendly data."""

    return {
        "gate": {
            "allowed": result.gate.allowed,
            "action": result.gate.action.value,
            "reason": result.gate.reason,
            "resume_after": result.gate.resume_after,
        },
        "resumed_job_ids": list(result.resumed_job_ids),
        "skipped_job_ids": list(result.skipped_job_ids),
        "next_check_at": result.next_check_at,
        "reason": result.reason,
    }


def _requeue_job(job: CodexJobArtifact, *, resumed_at: str) -> CodexJobArtifact:
    return replace(
        job,
        status=CodexJobStatus.QUEUED,
        updated_at=resumed_at,
        resume=CodexResumeMetadata(
            resumable=True,
            resume_after="",
            last_checkpoint_path=job.resume.last_checkpoint_path,
            last_error="",
            paused_at=job.resume.paused_at,
        ),
    )
