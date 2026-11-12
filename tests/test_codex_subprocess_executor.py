from pathlib import Path
from threading import Event

from agentic_boilerplate.domain import AgentRole
from agentic_boilerplate.runtime import (
    CODEX_RESULT_MARKER,
    CodexRunnerRequest,
    CodexSubprocessExecutorConfig,
    CodexSubprocessTranscript,
    SubprocessCodexRunnerExecutor,
)


class FakeSubprocessRunner:
    def __init__(self, transcript: CodexSubprocessTranscript) -> None:
        self.transcript = transcript
        self.invocations = []

    def __call__(self, invocation, cancel_event):
        self.invocations.append(invocation)
        return self.transcript


def test_executor_builds_args_prompt_and_subscription_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    runner = FakeSubprocessRunner(
        CodexSubprocessTranscript(
            returncode=0,
            stdout=f'stage done\n{CODEX_RESULT_MARKER} {{"status":"completed","summary":"done"}}\n',
        )
    )
    executor = SubprocessCodexRunnerExecutor(
        CodexSubprocessExecutorConfig(timeout_seconds=12, require_structured_result=True),
        run_process=runner,
    )

    execution = executor.execute(_request(tmp_path))

    assert not execution.failed
    assert not execution.limit_reached
    invocation = runner.invocations[0]
    assert invocation.args == (
        "codex",
        "exec",
        "--model",
        "gpt-5.4",
        "--config",
        'model_reasoning_effort="high"',
        "--sandbox",
        "workspace-write",
        "--config",
        'approval_policy="on-request"',
        "--config",
        'forced_login_method="chatgpt"',
    )
    assert invocation.cwd == tmp_path
    assert invocation.timeout_seconds == 12
    assert invocation.env["AGENTIC_CODEX_AUTH_MODE"] == "chatgpt_subscription"
    assert invocation.env["AGENTIC_JIRA_ISSUE_KEY"] == "AGENT-964"
    assert "OPENAI_API_KEY" not in invocation.env
    assert "Load context pack: data/context-packs/AGENT-964/context.json" in invocation.prompt
    assert "The host runner will persist your final response and execution result to:" in invocation.prompt
    assert "Do not write or overwrite the host-owned result file" in invocation.prompt
    assert "Write durable result to:" not in invocation.prompt
    assert "Read AGENTS.md when present" in invocation.prompt
    assert "otherwise explicitly load docs/reference/platform-agent-instructions.md" in invocation.prompt
    assert CODEX_RESULT_MARKER in invocation.prompt


def test_executor_blocks_api_key_override_when_subscription_auth_required(tmp_path: Path) -> None:
    runner = FakeSubprocessRunner(CodexSubprocessTranscript(returncode=0, stdout="should not run"))
    executor = SubprocessCodexRunnerExecutor(
        CodexSubprocessExecutorConfig(env_overrides={"OPENAI_API_KEY": "sk-test-secret"}),
        run_process=runner,
    )

    execution = executor.execute(_request(tmp_path))

    assert execution.failed
    assert execution.failure_category == "authentication_blocked"
    assert "OPENAI_API_KEY" in execution.error_summary
    assert runner.invocations == []


def test_executor_classifies_timeout(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path,
        CodexSubprocessTranscript(returncode=None, stdout="partial", timed_out=True),
    )

    assert execution.failed
    assert execution.failure_category == "timeout"
    assert "timed out" in execution.error_summary


def test_executor_classifies_malformed_structured_output(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path,
        CodexSubprocessTranscript(returncode=0, stdout=f"{CODEX_RESULT_MARKER} {{bad-json\n"),
        require_structured_result=True,
    )

    assert execution.failed
    assert execution.failure_category == "malformed_output"
    assert "malformed JSON" in execution.error_summary


def test_executor_classifies_missing_required_structured_output(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path,
        CodexSubprocessTranscript(returncode=0, stdout="plain text only"),
        require_structured_result=True,
    )

    assert execution.failed
    assert execution.failure_category == "malformed_output"
    assert "required structured result marker" in execution.error_summary


def test_executor_classifies_quota_exhaustion(tmp_path: Path) -> None:
    execution = _execute_with(tmp_path, CodexSubprocessTranscript(returncode=1, stderr="Rate limit reached."))

    assert execution.limit_reached
    assert not execution.failed
    assert execution.failure_category == "quota_exhausted"


def test_successful_quota_discussion_and_echoed_prompt_are_not_failures(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path,
        CodexSubprocessTranscript(
            returncode=0,
            stdout=f'Quota guard verified.\n{CODEX_RESULT_MARKER} {{"status":"completed"}}\n',
            stderr="Allowed status values: quota_exhausted, authentication_blocked, permission_blocked.",
        ),
        require_structured_result=True,
    )

    assert not execution.failed
    assert not execution.limit_reached


def test_nonzero_exit_cannot_be_overridden_by_completed_marker(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path,
        CodexSubprocessTranscript(
            returncode=1,
            stdout=f'{CODEX_RESULT_MARKER} {{"status":"completed"}}\n',
            stderr="Unexpected executor error.",
        ),
    )

    assert execution.failed
    assert execution.failure_category == "process_failed"


def test_echoed_prompt_does_not_hide_generic_process_failure(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path,
        CodexSubprocessTranscript(
            returncode=2,
            stderr="Allowed status values: quota_exhausted, authentication_blocked. Invalid argument.",
        ),
    )

    assert execution.failed
    assert not execution.limit_reached
    assert execution.failure_category == "process_failed"


def test_structured_quota_status_is_preserved(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path,
        CodexSubprocessTranscript(returncode=0, stdout=f'{CODEX_RESULT_MARKER} {{"status":"quota_exhausted"}}'),
    )

    assert execution.limit_reached
    assert execution.failure_category == "quota_exhausted"


def test_non_object_marker_is_rejected_safely(tmp_path: Path) -> None:
    execution = _execute_with(
        tmp_path, CodexSubprocessTranscript(returncode=0, stdout=f"{CODEX_RESULT_MARKER} []")
    )

    assert execution.failed
    assert execution.failure_category == "malformed_output"


def test_executor_classifies_expired_auth(tmp_path: Path) -> None:
    execution = _execute_with(tmp_path, CodexSubprocessTranscript(returncode=1, stderr="Not logged in. Run codex login."))

    assert execution.failed
    assert execution.failure_category == "authentication_blocked"


def test_executor_classifies_denied_permission(tmp_path: Path) -> None:
    execution = _execute_with(tmp_path, CodexSubprocessTranscript(returncode=1, stderr="Permission denied by policy."))

    assert execution.failed
    assert execution.failure_category == "permission_blocked"


def test_executor_honors_pre_start_cancellation(tmp_path: Path) -> None:
    cancel_event = Event()
    cancel_event.set()
    runner = FakeSubprocessRunner(CodexSubprocessTranscript(returncode=0, stdout="should not run"))
    executor = SubprocessCodexRunnerExecutor(run_process=runner, cancel_event=cancel_event)

    execution = executor.execute(_request(tmp_path))

    assert execution.failed
    assert execution.failure_category == "cancelled"
    assert runner.invocations == []


def test_executor_redacts_secret_like_output(tmp_path: Path) -> None:
    token = "gh" "p_1234567890abcdefghijklmnop"
    runner = FakeSubprocessRunner(
        CodexSubprocessTranscript(
            returncode=0,
            stdout=f"completed with {token}\n{CODEX_RESULT_MARKER} {{\"status\":\"completed\"}}\n",
        )
    )
    executor = SubprocessCodexRunnerExecutor(
        CodexSubprocessExecutorConfig(require_structured_result=True),
        run_process=runner,
    )

    execution = executor.execute(_request(tmp_path))

    assert token not in execution.output_text
    assert token not in execution.log_text
    assert "***REDACTED***" in execution.output_text


def _execute_with(
    tmp_path: Path,
    transcript: CodexSubprocessTranscript,
    *,
    require_structured_result: bool = False,
):
    runner = FakeSubprocessRunner(transcript)
    executor = SubprocessCodexRunnerExecutor(
        CodexSubprocessExecutorConfig(require_structured_result=require_structured_result),
        run_process=runner,
    )
    return executor.execute(_request(tmp_path))


def _request(tmp_path: Path) -> CodexRunnerRequest:
    return CodexRunnerRequest(
        job_id="job-1",
        jira_issue_key="AGENT-964",
        role=AgentRole.DEVELOPER,
        target_repo_path=str(tmp_path),
        branch_name="feature/AGENT-964-bounded-host-codex-executor",
        context_pack_path="data/context-packs/AGENT-964/context.json",
        model="gpt-5.4",
        reasoning="high",
        speed="normal",
        effort_mode="complex",
        output_path=str(tmp_path / "codex-results" / "AGENT-964" / "result.json"),
        attempt_count=0,
    )
