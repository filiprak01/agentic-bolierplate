from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.domain import (
    CodexLimitObservationSource,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    ReleaseIntakeInput,
    build_codex_limit_availability_record,
    build_release_intake_report,
    format_release_intake_report,
    release_intake_report_to_dict,
)


def test_release_intake_report_is_ready_with_docs_paths_and_limits(tmp_path: Path) -> None:
    project_root = tmp_path / "target-project"
    product_docs = project_root / "docs" / "product"
    architecture = project_root / "docs" / "architecture"
    product_docs.mkdir(parents=True)
    architecture.mkdir(parents=True)
    (product_docs / "requirements.md").write_text("# Requirements\n", encoding="utf-8")
    (architecture / "overview.md").write_text("# Architecture\n", encoding="utf-8")

    report = build_release_intake_report(
        _settings(tmp_path),
        _intake(project_root),
        latest_limit_record=_available_limit_record(),
    )

    payload = release_intake_report_to_dict(report)

    assert report.ready is True
    assert payload["ready"] is True
    assert payload["schema_version"] == "release-intake-report/v1"
    assert payload["po_questions"] == []
    assert str(project_root.resolve()) == payload["project_root"]
    assert "Ready: yes" in format_release_intake_report(report)


def test_release_intake_report_blocks_missing_docs_repo_agiletest_and_limits(tmp_path: Path) -> None:
    project_root = tmp_path / "target-project"
    project_root.mkdir()

    report = build_release_intake_report(
        _settings(
            tmp_path,
            extra={
                "AGILETEST_CLIENT_ID": "",
                "AGILETEST_API_TOKEN": "",
            },
        ),
        _intake(project_root, target_repository="invalid-repo"),
    )

    failed = {check.name for check in report.checks if check.blocks_readiness}
    payload = release_intake_report_to_dict(report)

    assert report.ready is False
    assert "target_repository" in failed
    assert "product_docs_root" in failed
    assert "product_docs.content" in failed
    assert "agiletest.client_id" in failed
    assert "codex_limits.latest" in failed
    assert {question["related_check"] for question in payload["po_questions"]} == failed
    assert "agiletest-token" not in str(payload)


def test_release_intake_applies_configured_limit_timestamp_policy(tmp_path: Path) -> None:
    project_root = tmp_path / "target-project"
    product_docs = project_root / "docs" / "product"
    architecture = project_root / "docs" / "architecture"
    product_docs.mkdir(parents=True)
    architecture.mkdir(parents=True)
    (product_docs / "requirements.md").write_text("# Requirements\n", encoding="utf-8")
    (architecture / "overview.md").write_text("# Architecture\n", encoding="utf-8")
    settings = _settings(
        tmp_path,
        extra={
            "CODEX_LIMIT_STALE_AFTER_SECONDS": "300",
            "CODEX_LIMIT_FUTURE_TOLERANCE_SECONDS": "30",
        },
    )
    now = datetime.now(UTC).replace(microsecond=0)

    fresh = build_release_intake_report(
        settings,
        _intake(project_root),
        latest_limit_record=_available_limit_record_at(now - timedelta(seconds=60)),
    )
    stale = build_release_intake_report(
        settings,
        _intake(project_root),
        latest_limit_record=_available_limit_record_at(now - timedelta(seconds=600)),
    )
    future = build_release_intake_report(
        settings,
        _intake(project_root),
        latest_limit_record=_available_limit_record_at(now + timedelta(seconds=120)),
    )
    invalid = build_release_intake_report(
        settings,
        _intake(project_root),
        latest_limit_record=_available_limit_record_at("not-a-timestamp"),
    )

    assert fresh.ready
    assert _limit_check(fresh).status.value == "passed"
    assert not stale.ready
    assert "stale" in _limit_check(stale).message
    assert not future.ready
    assert "materially future-dated" in _limit_check(future).message
    assert not invalid.ready
    assert "invalid timestamp" in _limit_check(invalid).message


def _intake(project_root: Path, *, target_repository: str = "example-org/demo") -> ReleaseIntakeInput:
    return ReleaseIntakeInput(
        project_id="ap",
        project_name="Airline Project",
        release_id="R1",
        generated_at="2026-07-10T12:00:00Z",
        project_root=project_root,
        target_repository=target_repository,
        jira_project_key="AP",
        jira_board_id="42",
        product_docs_root=Path("docs/product"),
        architecture_root=Path("docs/architecture"),
        evidence_root=Path("data/agent-logs"),
        durable_data_root=Path("data"),
        report_root=Path("data/intake-reports"),
    )


def _settings(project_root: Path, *, extra: dict[str, str] | None = None):
    values = {
        "GITHUB_TOKEN": "github-token",
        "GITHUB_REPOSITORY": "example-org/demo",
        "JIRA_PROJECT_KEY": "AP",
        "JIRA_BOARD_ID": "42",
        "JIRA_EMAIL": "po@example.com",
        "JIRA_API_TOKEN": "jira-token",
        "CONFLUENCE_SPACE_KEY": "",
        "CONFLUENCE_PARENT_PAGE_ID": "",
        "AGILETEST_CLIENT_ID": "agiletest-client",
        "AGILETEST_API_TOKEN": "agiletest-token",
        "TARGET_PROJECT_PATH": str(project_root),
        "DURABLE_PO_INBOX_PATH": str(project_root / "data" / "po-inbox"),
        "DURABLE_AGENT_LOGS_PATH": str(project_root / "data" / "agent-logs"),
        "DURABLE_CODEX_LIMITS_PATH": str(project_root / "data" / "codex-limits"),
    }
    if extra:
        values.update(extra)
    return settings_from_mapping(values)


def _available_limit_record():
    return _available_limit_record_at("2026-07-10T12:00:00Z")


def _available_limit_record_at(observed_at: datetime | str):
    if isinstance(observed_at, datetime):
        observed_at = observed_at.isoformat().replace("+00:00", "Z")
    return build_codex_limit_availability_record(
        record_id="available-20260710T120000Z",
        short_window=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=99,
            reset_at="2026-07-10T17:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
        ),
        broad_quota=CodexLimitWindowAvailability(
            status=CodexLimitWindowStatus.AVAILABLE,
            remaining_percent=80,
            reset_at="2026-07-17T12:00:00Z",
            observation_source=CodexLimitObservationSource.OPERATOR,
            observed_at=observed_at,
        ),
    )


def _limit_check(report):
    return next(check for check in report.checks if check.name == "codex_limits.latest")
