import json
from pathlib import Path

from agentic_boilerplate.cli import main


def test_setup_validate_cli_returns_json_for_ready_setup(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    limits_root = project_root / "data" / "codex-limits"
    project_root.mkdir()
    target_project.mkdir()

    env_file = _write_env(project_root, target_project)
    assert (
        main(
            [
                "--env-file",
                str(env_file),
                "codex-limits",
                "record",
                "--id",
                "available-20260710T120000Z",
                "--short-status",
                "available",
                "--short-remaining",
                "99",
                "--short-reset-at",
                "2026-07-10T17:00:00Z",
                "--broad-status",
                "available",
                "--broad-remaining",
                "80",
                "--broad-reset-at",
                "2026-07-17T12:00:00Z",
                "--observed-at",
                "2026-07-10T12:00:00Z",
                "--codex-limits-root",
                str(limits_root),
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = main(
        [
            "--env-file",
            str(env_file),
            "setup",
            "validate",
            "--project-root",
            str(project_root),
            "--codex-limits-root",
            str(limits_root),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["passed"] is True
    assert all(check["passed"] for check in payload["checks"])


def test_setup_validate_cli_blocks_without_limit_record(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    target_project.mkdir()

    result = main(
        [
            "--env-file",
            str(_write_env(project_root, target_project)),
            "setup",
            "validate",
            "--project-root",
            str(project_root),
            "--codex-limits-root",
            str(project_root / "data" / "codex-limits"),
        ]
    )

    output = capsys.readouterr().out

    assert result == 1
    assert "codex_limits.latest" in output
    assert "ask_product_owner" in output
    assert "github-token" not in output
    assert "jira-token" not in output
    assert "confluence-token" not in output
    assert "agiletest-token" not in output


def test_setup_intake_cli_writes_ready_report_with_custom_dirs(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    limits_root = project_root / "data" / "codex-limits"
    report_root = project_root / "data" / "intake-reports"
    project_root.mkdir()
    target_project.mkdir()
    product_docs = target_project / "custom-product"
    architecture = target_project / "custom-architecture"
    product_docs.mkdir()
    architecture.mkdir()
    (product_docs / "scope.md").write_text("# Scope\n", encoding="utf-8")
    (architecture / "nfr.md").write_text("# NFR\n", encoding="utf-8")

    env_file = _write_env(project_root, target_project)
    assert (
        main(
            [
                "--env-file",
                str(env_file),
                "codex-limits",
                "record",
                "--id",
                "available-20260710T120000Z",
                "--short-status",
                "available",
                "--short-remaining",
                "99",
                "--short-reset-at",
                "2026-07-10T17:00:00Z",
                "--broad-status",
                "available",
                "--broad-remaining",
                "80",
                "--broad-reset-at",
                "2026-07-17T12:00:00Z",
                "--observed-at",
                "2026-07-10T12:00:00Z",
                "--codex-limits-root",
                str(limits_root),
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = main(
        [
            "--env-file",
            str(env_file),
            "setup",
            "intake",
            "--project-id",
            "ap",
            "--project-name",
            "Airline Project",
            "--release-id",
            "R1",
            "--project-root",
            str(target_project),
            "--product-docs-root",
            "custom-product",
            "--architecture-root",
            "custom-architecture",
            "--report-root",
            str(report_root),
            "--codex-limits-root",
            str(limits_root),
            "--generated-at",
            "2026-07-10T12:00:00Z",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["ready"] is True
    assert payload["po_inbox_items"] == []
    assert Path(payload["report_json_path"]).is_file()
    assert Path(payload["report_markdown_path"]).is_file()
    report_payload = json.loads(Path(payload["report_json_path"]).read_text(encoding="utf-8"))
    assert any(
        path["name"] == "product_docs_root" and path["path"] == str(product_docs)
        for path in report_payload["paths"]
    )
    assert "github-token" not in str(report_payload)


def test_setup_intake_cli_creates_idempotent_po_inbox_blockers(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    target_project.mkdir()
    env_file = _write_env(project_root, target_project)

    command = [
        "--env-file",
        str(env_file),
        "setup",
        "intake",
        "--project-id",
        "ap",
        "--release-id",
        "R1",
        "--project-root",
        str(target_project),
        "--target-repository",
        "missing-owner",
        "--report-root",
        str(project_root / "data" / "intake-reports"),
        "--codex-limits-root",
        str(project_root / "data" / "codex-limits"),
        "--generated-at",
        "2026-07-10T12:00:00Z",
        "--json",
    ]

    first_result = main(command)
    first_payload = json.loads(capsys.readouterr().out)
    second_result = main(command)
    second_payload = json.loads(capsys.readouterr().out)

    assert first_result == 1
    assert second_result == 1
    assert first_payload["ready"] is False
    assert "target_repository" in first_payload["failed_checks"]
    assert "product_docs_root" in first_payload["failed_checks"]
    assert "codex_limits.latest" in first_payload["failed_checks"]
    assert first_payload["po_inbox_items"] == second_payload["po_inbox_items"]
    for inbox_item in first_payload["po_inbox_items"]:
        path = Path(inbox_item["path"])
        assert path.is_file()
        item_payload = json.loads(path.read_text(encoding="utf-8"))
        assert item_payload["message_type"] == "blocking_question"
        assert item_payload["status"] == "open"


def test_setup_live_diagnostic_cli_reports_readiness_without_network(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "repo"
    target_project = tmp_path / "target-project"
    project_root.mkdir()
    (project_root / "data").mkdir()
    target_project.mkdir()
    (target_project / ".git").mkdir()

    result = main(
        [
            "--env-file",
            str(_write_env(project_root, target_project)),
            "setup",
            "live-diagnostic",
            "--project-root",
            str(project_root),
            "--skip-network",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["assignment_allowed"] is True
    assert any(check["status"] == "warning" for check in payload["checks"])
    assert "github-token" not in str(payload)


def _write_env(project_root: Path, target_project: Path) -> Path:
    data_root = project_root / "data"
    env_file = project_root / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GITHUB_TOKEN=github-token",
                "GITHUB_REPOSITORY=example-org/example",
                "JIRA_PROJECT_KEY=DEMO",
                "JIRA_BOARD_ID=42",
                "JIRA_EMAIL=po@example.com",
                "JIRA_API_TOKEN=jira-token",
                "CONFLUENCE_SPACE_KEY=DEMO",
                "CONFLUENCE_PARENT_PAGE_ID=123",
                "CONFLUENCE_EMAIL=po@example.com",
                "CONFLUENCE_API_TOKEN=confluence-token",
                "AGILETEST_CLIENT_ID=agiletest-client",
                "AGILETEST_API_TOKEN=agiletest-token",
                f"TARGET_PROJECT_PATH={target_project}",
                f"DURABLE_PO_INBOX_PATH={data_root / 'po-inbox'}",
                f"DURABLE_CONTEXT_PACKS_PATH={data_root / 'context-packs'}",
                f"DURABLE_CODEX_JOBS_PATH={data_root / 'codex-jobs'}",
                f"DURABLE_CODEX_RESULTS_PATH={data_root / 'codex-results'}",
                f"DURABLE_CODEX_LIMITS_PATH={data_root / 'codex-limits'}",
                f"DURABLE_AGENT_STATE_PATH={data_root / 'agent-state'}",
                f"DURABLE_AGENT_LOGS_PATH={data_root / 'agent-logs'}",
                f"DURABLE_PO_DECISIONS_PATH={data_root / 'po-decisions'}",
                f"DURABLE_SPRINTS_PATH={data_root / 'sprints'}",
                f"DURABLE_CONFLUENCE_MIRROR_PATH={data_root / 'confluence-mirror'}",
            ]
        ),
        encoding="utf-8",
    )
    return env_file
