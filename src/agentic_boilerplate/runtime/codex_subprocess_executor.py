"""Subprocess-backed host-side Codex executor."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any

from agentic_boilerplate.domain import redact_failed_request_text
from agentic_boilerplate.runtime.codex_runner import CodexRunnerExecution, CodexRunnerRequest

CODEX_RESULT_MARKER = "AGENTIC_CODEX_RESULT_JSON:"
DEFAULT_ALLOWED_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "HOME",
    "USER",
    "USERNAME",
    "SHELL",
    "TERM",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "CODEX_HOME",
)
FORBIDDEN_SUBSCRIPTION_ENV_KEYS: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
    }
)


@dataclass(frozen=True)
class CodexSubprocessExecutorConfig:
    """Configuration for one bounded host-side Codex CLI execution."""

    command: str | Sequence[str] = ("codex", "exec")
    timeout_seconds: float = 900
    model_argument: str = "--model"
    reasoning_argument: str = "--config"
    sandbox_argument: str = "--sandbox"
    approval_argument: str = "--config"
    sandbox: str = "workspace-write"
    approval_policy: str = "on-request"
    extra_args: tuple[str, ...] = field(default_factory=tuple)
    allowed_env_keys: tuple[str, ...] = DEFAULT_ALLOWED_ENV_KEYS
    env_overrides: Mapping[str, str] = field(default_factory=dict)
    require_chatgpt_auth: bool = True
    require_structured_result: bool = False
    expected_json_marker: str = CODEX_RESULT_MARKER
    output_limit_chars: int = 20_000


@dataclass(frozen=True)
class CodexSubprocessInvocation:
    """Inspectable process request sent to the subprocess boundary."""

    args: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    prompt: str
    timeout_seconds: float


@dataclass(frozen=True)
class CodexSubprocessTranscript:
    """Captured process transcript from one Codex subprocess attempt."""

    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False


SubprocessRunner = Callable[[CodexSubprocessInvocation, Event | None], CodexSubprocessTranscript]


class SubprocessCodexRunnerExecutor:
    """Execute one Codex runner request through a bounded local subprocess."""

    def __init__(
        self,
        config: CodexSubprocessExecutorConfig | None = None,
        *,
        run_process: SubprocessRunner | None = None,
        cancel_event: Event | None = None,
    ) -> None:
        self.config = config or CodexSubprocessExecutorConfig()
        self._run_process = run_process or _default_run_process
        self._cancel_event = cancel_event

    def execute(self, request: CodexRunnerRequest) -> CodexRunnerExecution:
        """Run one request and return classified, redacted execution metadata."""

        if self._cancel_event is not None and self._cancel_event.is_set():
            return _classified_execution(
                output_text="",
                error_summary="Codex execution was cancelled before process start.",
                failure_category="cancelled",
                failed=True,
            )

        blocked_key = _blocked_subscription_env_key(self.config.env_overrides)
        if self.config.require_chatgpt_auth and blocked_key:
            return _classified_execution(
                output_text="",
                error_summary=(
                    "Host ChatGPT subscription authentication is required; "
                    f"environment override {blocked_key} is not allowed for Codex execution."
                ),
                failure_category="authentication_blocked",
                failed=True,
            )

        invocation = CodexSubprocessInvocation(
            args=build_codex_subprocess_args(request, self.config),
            cwd=Path(request.target_repo_path),
            env=build_codex_subprocess_env(request, self.config),
            prompt=build_codex_stage_prompt(request, marker=self.config.expected_json_marker),
            timeout_seconds=self.config.timeout_seconds,
        )

        try:
            transcript = self._run_process(invocation, self._cancel_event)
        except FileNotFoundError as exc:
            return _classified_execution(
                output_text="",
                error_summary=f"Codex executable was not found: {exc}",
                failure_category="authentication_blocked",
                failed=True,
            )
        except PermissionError as exc:
            return _classified_execution(
                output_text="",
                error_summary=f"Codex executable permission denied: {exc}",
                failure_category="permission_blocked",
                failed=True,
            )
        except OSError as exc:
            return _classified_execution(
                output_text="",
                error_summary=f"Codex subprocess could not start: {exc}",
                failure_category="process_failed",
                failed=True,
            )

        return classify_codex_subprocess_transcript(transcript, self.config)


def build_codex_subprocess_args(
    request: CodexRunnerRequest,
    config: CodexSubprocessExecutorConfig | None = None,
) -> tuple[str, ...]:
    """Build structured CLI args without shell interpolation."""

    selected = config or CodexSubprocessExecutorConfig()
    args = list(_command_parts(selected.command))
    if request.model:
        args.extend((selected.model_argument, request.model))
    if request.reasoning:
        reasoning = request.reasoning
        if selected.reasoning_argument == "--config":
            reasoning = f"model_reasoning_effort={json.dumps(reasoning)}"
        args.extend((selected.reasoning_argument, reasoning))
    if selected.sandbox:
        args.extend((selected.sandbox_argument, selected.sandbox))
    if selected.approval_policy:
        approval = selected.approval_policy
        if selected.approval_argument == "--config":
            approval = f"approval_policy={json.dumps(approval)}"
        args.extend((selected.approval_argument, approval))
    if selected.require_chatgpt_auth:
        args.extend(("--config", 'forced_login_method="chatgpt"'))
    args.extend(selected.extra_args)
    return tuple(str(arg) for arg in args if str(arg).strip())


def build_codex_subprocess_env(
    request: CodexRunnerRequest,
    config: CodexSubprocessExecutorConfig | None = None,
) -> dict[str, str]:
    """Build a minimal env that avoids API-key fallback in subscription mode."""

    selected = config or CodexSubprocessExecutorConfig()
    allowed = {key.upper() for key in selected.allowed_env_keys}
    child_env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    if selected.require_chatgpt_auth:
        for key in FORBIDDEN_SUBSCRIPTION_ENV_KEYS:
            child_env.pop(key, None)
    for key, value in selected.env_overrides.items():
        if selected.require_chatgpt_auth and key.upper() in FORBIDDEN_SUBSCRIPTION_ENV_KEYS:
            continue
        child_env[key] = str(value)
    child_env.update(
        {
            "AGENTIC_CODEX_AUTH_MODE": "chatgpt_subscription" if selected.require_chatgpt_auth else "configured",
            "AGENTIC_CODEX_JOB_ID": request.job_id,
            "AGENTIC_JIRA_ISSUE_KEY": request.jira_issue_key,
            "AGENTIC_AGENT_ROLE": request.role.value,
            "AGENTIC_CONTEXT_PACK_PATH": request.context_pack_path,
            "AGENTIC_OUTPUT_PATH": request.output_path,
        }
    )
    return child_env


def build_codex_stage_prompt(request: CodexRunnerRequest, *, marker: str = CODEX_RESULT_MARKER) -> str:
    """Build the host-side prompt passed to Codex for one bounded stage."""

    return "\n".join(
        (
            f"Act as the {request.role.value} agent for Jira issue {request.jira_issue_key}.",
            "Read AGENTS.md when present; otherwise explicitly load docs/reference/platform-agent-instructions.md. "
            "Read the referenced role instruction files before changing files.",
            f"Work in repository path: {request.target_repo_path}",
            f"Use branch: {request.branch_name}",
            f"Load context pack: {request.context_pack_path}",
            f"The host runner will persist your final response and execution result to: {request.output_path}",
            "Do not write or overwrite the host-owned result file; return the structured marker below instead.",
            f"Model route: {request.model}; reasoning: {request.reasoning}; speed: {request.speed}; effort: {request.effort_mode}.",
            "Use the existing Jira, GitHub, evidence, review, and testing process for this assignment.",
            "Do not use API keys or copied tokens for Codex model calls; use the host ChatGPT subscription session only.",
            "Return a final single-line structured marker for the runner:",
            f'{marker} {{"status":"completed","summary":"short result"}}',
            "Allowed status values: completed, failed, quota_exhausted, authentication_blocked, permission_blocked.",
        )
    ) + "\n"


def classify_codex_subprocess_transcript(
    transcript: CodexSubprocessTranscript,
    config: CodexSubprocessExecutorConfig | None = None,
) -> CodexRunnerExecution:
    """Classify a subprocess transcript into the runner execution contract."""

    selected = config or CodexSubprocessExecutorConfig()
    stdout = _redact_and_limit(transcript.stdout, selected.output_limit_chars)
    stderr = _redact_and_limit(transcript.stderr, selected.output_limit_chars)
    combined_raw = "\n".join((transcript.stdout, transcript.stderr))
    combined_safe = _redact_and_limit(combined_raw, selected.output_limit_chars)
    log_text = _transcript_log(transcript, stdout=stdout, stderr=stderr)

    if transcript.cancelled:
        return _classified_execution(
            output_text=stdout,
            log_text=log_text,
            error_summary="Codex execution was cancelled and the child process was cleaned up.",
            failure_category="cancelled",
            failed=True,
        )
    if transcript.timed_out:
        return _classified_execution(
            output_text=stdout,
            log_text=log_text,
            error_summary="Codex execution timed out and the child process was cleaned up.",
            failure_category="timeout",
            failed=True,
        )

    keyword_category = _category_from_keywords(combined_raw) if transcript.returncode not in (0, None) else ""
    if keyword_category == "quota_exhausted":
        return _classified_execution(
            output_text=stdout,
            log_text=log_text,
            error_summary="Codex quota or rate limit was reached.",
            failure_category=keyword_category,
            limit_reached=True,
        )
    if keyword_category in {"authentication_blocked", "permission_blocked"}:
        return _classified_execution(
            output_text=stdout,
            log_text=log_text,
            error_summary=_first_non_empty(stderr, stdout, keyword_category.replace("_", " ")),
            failure_category=keyword_category,
            failed=True,
        )

    if transcript.returncode not in (0, None):
        return _classified_execution(
            output_text=stdout,
            log_text=log_text,
            error_summary=_first_non_empty(stderr, f"Codex subprocess exited with code {transcript.returncode}."),
            failure_category="process_failed",
            failed=True,
        )

    marker_payload = _extract_marker_payload(transcript.stdout, selected.expected_json_marker)
    if marker_payload is None:
        if selected.require_structured_result:
            return _classified_execution(
                output_text=stdout,
                log_text=log_text,
                error_summary="Codex output did not include the required structured result marker.",
                failure_category="malformed_output",
                failed=True,
            )
    else:
        try:
            parsed = json.loads(marker_payload)
        except json.JSONDecodeError as exc:
            return _classified_execution(
                output_text=stdout,
                log_text=log_text,
                error_summary=f"Codex structured result marker was malformed JSON: {exc.msg}",
                failure_category="malformed_output",
                failed=True,
            )
        if not isinstance(parsed, dict):
            return _classified_execution(
                output_text=stdout,
                log_text=log_text,
                error_summary="Codex structured result marker must contain a JSON object.",
                failure_category="malformed_output",
                failed=True,
            )
        return _execution_from_payload(parsed, stdout=stdout, log_text=log_text)

    return _classified_execution(output_text=combined_safe, log_text=log_text)


def codex_subprocess_executor_config_from_env(
    env: Mapping[str, str] | None = None,
) -> CodexSubprocessExecutorConfig:
    """Create executor config from environment values used by local operators."""

    source = env or os.environ
    timeout_seconds = _float_from_env(source.get("CODEX_RUNNER_TIMEOUT_SECONDS"), default=900)
    command = source.get("CODEX_RUNNER_COMMAND") or ("codex", "exec")
    extra_args = tuple(shlex.split(source.get("CODEX_RUNNER_EXTRA_ARGS", "")))
    require_structured = _bool_from_env(source.get("CODEX_RUNNER_REQUIRE_STRUCTURED_RESULT"), default=False)
    output_limit_chars = int(_float_from_env(source.get("CODEX_RUNNER_OUTPUT_LIMIT_CHARS"), default=20_000))
    return CodexSubprocessExecutorConfig(
        command=command,
        timeout_seconds=timeout_seconds,
        extra_args=extra_args,
        require_structured_result=require_structured,
        output_limit_chars=output_limit_chars,
    )


def _default_run_process(
    invocation: CodexSubprocessInvocation,
    cancel_event: Event | None,
) -> CodexSubprocessTranscript:
    process = subprocess.Popen(
        invocation.args,
        cwd=str(invocation.cwd),
        env=dict(invocation.env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    deadline = time.monotonic() + invocation.timeout_seconds
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(process.communicate, invocation.prompt)
        while True:
            try:
                stdout, stderr = future.result(timeout=0.2)
                return CodexSubprocessTranscript(
                    returncode=process.returncode,
                    stdout=stdout,
                    stderr=stderr,
                )
            except FutureTimeoutError:
                if cancel_event is not None and cancel_event.is_set():
                    stdout, stderr = _terminate_process(process, future)
                    return CodexSubprocessTranscript(
                        returncode=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        cancelled=True,
                    )
                if time.monotonic() >= deadline:
                    stdout, stderr = _terminate_process(process, future)
                    return CodexSubprocessTranscript(
                        returncode=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        timed_out=True,
                    )


def _terminate_process(process: subprocess.Popen[str], future) -> tuple[str, str]:
    process.terminate()
    try:
        return future.result(timeout=3)
    except FutureTimeoutError:
        process.kill()
        return future.result(timeout=3)


def _execution_from_payload(payload: Mapping[str, Any], *, stdout: str, log_text: str) -> CodexRunnerExecution:
    status = str(payload.get("status", "")).strip().lower()
    summary = str(payload.get("summary") or payload.get("message") or "").strip()
    resume_after = str(payload.get("resume_after") or "").strip()
    category = str(payload.get("failure_category") or status or "").strip().lower()
    if status in {"completed", "success", "passed"}:
        return _classified_execution(output_text=stdout, log_text=log_text)
    if status in {"quota_exhausted", "limit_reached", "rate_limited"}:
        return _classified_execution(
            output_text=stdout,
            log_text=log_text,
            error_summary=summary or "Codex quota or rate limit was reached.",
            failure_category="quota_exhausted",
            limit_reached=True,
            resume_after=resume_after,
        )
    if status in {"authentication_blocked", "permission_blocked", "timeout", "cancelled", "process_failed", "failed"}:
        failure_category = category if category and category != "failed" else "process_failed"
        return _classified_execution(
            output_text=stdout,
            log_text=log_text,
            error_summary=summary or failure_category.replace("_", " "),
            failure_category=failure_category,
            failed=True,
            resume_after=resume_after,
        )
    return _classified_execution(
        output_text=stdout,
        log_text=log_text,
        error_summary=f"Unsupported Codex structured result status: {status or 'missing'}.",
        failure_category="malformed_output",
        failed=True,
    )


def _classified_execution(
    *,
    output_text: str = "",
    log_text: str = "",
    error_summary: str = "",
    failure_category: str = "",
    limit_reached: bool = False,
    failed: bool = False,
    resume_after: str = "",
) -> CodexRunnerExecution:
    return CodexRunnerExecution(
        output_text=redact_failed_request_text(output_text).value,
        log_text=redact_failed_request_text(log_text).value,
        error_summary=redact_failed_request_text(error_summary).value,
        failure_category=failure_category,
        limit_reached=limit_reached,
        failed=failed,
        resume_after=resume_after,
    )


def _transcript_log(transcript: CodexSubprocessTranscript, *, stdout: str, stderr: str) -> str:
    return "\n".join(
        (
            "Codex subprocess transcript:",
            f"returncode={transcript.returncode}",
            f"timed_out={str(transcript.timed_out).lower()}",
            f"cancelled={str(transcript.cancelled).lower()}",
            "stdout:",
            stdout or "<empty>",
            "stderr:",
            stderr or "<empty>",
        )
    ) + "\n"


def _category_from_keywords(value: str) -> str:
    lower = value.lower()
    if any(token in lower for token in ("rate limit", "quota exceeded", "quota exhausted", "usage limit", "limit reached")):
        return "quota_exhausted"
    if any(token in lower for token in ("not logged in", "authentication failed", "unauthorized", "token expired", "expired token")):
        return "authentication_blocked"
    if any(token in lower for token in ("permission denied", "approval required", "sandbox denied", "denied by policy")):
        return "permission_blocked"
    return ""


def _extract_marker_payload(stdout: str, marker: str) -> str | None:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith(marker):
            return stripped[len(marker) :].strip()
    return None


def _blocked_subscription_env_key(env: Mapping[str, str]) -> str:
    for key in env:
        if key.upper() in FORBIDDEN_SUBSCRIPTION_ENV_KEYS:
            return key
    return ""


def _command_parts(command: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(command, str):
        return tuple(shlex.split(command))
    return tuple(str(part) for part in command)


def _redact_and_limit(value: str, limit: int) -> str:
    redacted = redact_failed_request_text(value).value
    if len(redacted) <= limit:
        return redacted
    return redacted[:limit] + "\n...[truncated]"


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value.strip():
            return value.strip()
    return ""


def _float_from_env(value: str | None, *, default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _bool_from_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
