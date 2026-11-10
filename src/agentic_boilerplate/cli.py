"""Command line interface for the agentic boilerplate platform."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from agentic_boilerplate.api.local import serve_local_api
from agentic_boilerplate.config import load_settings
from agentic_boilerplate.domain import (
    AgentCommunicationChannel,
    AgentMessagePriority,
    AgentMessageStatus,
    AgentMessageType,
    AgentRole,
    CodexLimitAvailabilityError,
    CodexLimitObservationSource,
    CodexLimitPlanMode,
    CodexLimitWindowAvailability,
    CodexLimitWindowStatus,
    ContextPackSchemaError,
    InboxAuditEvent,
    InboxMessageType,
    InboxSchemaError,
    InboxStatus,
    OrchestrationEventStatus,
    OrchestrationEventType,
    POInboxItem,
    GitHubPagesReportPublicationError,
    RoleHandoffTriggerInput,
    StoryPathEvent,
    StoryPathRole,
    AssignmentLockReleaseReason,
    AssignmentLockStatus,
    agent_message_idempotency_key,
    agent_message_to_dict,
    build_blocked_role_handoff_message,
    build_orchestration_event,
    build_agent_message,
    build_role_handoff_trigger_message,
    BacklogContextPackGenerationConfig,
    ContextPackDocumentationReference,
    backlog_approval_gate_decision_to_dict,
    backlog_context_pack_generation_result_to_dict,
    backlog_draft_from_dict,
    backlog_draft_to_dict,
    build_backlog_creation_approval_request,
    build_docs_site,
    build_missing_business_decision_questions,
    create_backlog_draft,
    build_codex_limit_availability_record,
    build_context_pack,
    codex_limit_availability_record_to_dict,
    codex_limit_windows_for_display,
    context_pack_build_input_from_dict,
    decide_codex_limit_gate,
    docs_site_build_to_dict,
    docs_site_validation_to_dict,
    failed_request_artifact_to_dict,
    failed_request_replay_guard_key,
    format_integration_readiness_report,
    inbox_item_to_dict,
    integration_readiness_report_to_dict,
    mark_orchestration_event_processed,
    orchestration_event_idempotency_key,
    orchestration_event_to_dict,
    pause_assignment_for_po_inbox,
    publish_report_artifacts_to_docs,
    redact_integration_readiness_text,
    reject_orchestration_event,
    generate_context_packs_from_backlog_draft,
    evaluate_backlog_creation_approval_gate,
    requirement_input_from_dict,
    report_publication_input_from_dict,
    report_publication_result_to_dict,
    validate_docs_site,
)
from agentic_boilerplate.domain.first_project_setup import (
    FirstProjectSetupValidation,
    format_first_project_setup_validation,
    validate_first_project_setup,
)
from agentic_boilerplate.domain.documentation_traceability import (
    DocumentationTraceabilityAuditConfig,
    DocumentationTraceabilityIssue,
    DocumentationTraceabilityProject,
    TraceabilityFollowUpPolicy,
    audit_documentation_traceability,
    build_traceability_follow_up_plan,
    documentation_traceability_report_to_dict,
    traceability_follow_up_plan_to_dict,
)
from agentic_boilerplate.domain.release_intake import (
    ReleaseIntakeInput,
    build_release_intake_report,
    format_release_intake_report,
    release_intake_report_markdown,
    release_intake_report_paths,
    release_intake_report_to_dict,
    release_intake_summary_table,
)
from agentic_boilerplate.domain.assignment_status import (
    assignment_status_item_to_dict,
    build_assignment_status_items,
)
from agentic_boilerplate.domain.po_inbox_path_guard import (
    format_po_inbox_path_guard_result,
    load_external_po_inbox_item,
    validate_po_inbox_paths,
)
from agentic_boilerplate.integrations.github import (
    github_config_from_settings,
    github_https_remote_url,
    github_token_credential_output,
)
from agentic_boilerplate.integrations.git_ssh_auth import (
    git_ssh_auth_config_from_settings,
    prepare_git_ssh_runtime_environment,
    redacted_git_ssh_auth_summary,
    redacted_git_ssh_runtime_summary,
    redact_git_ssh_text,
    validate_git_ssh_auth,
)
from agentic_boilerplate.integrations.live_readiness import (
    LiveIntegrationReadinessOptions,
    build_live_integration_readiness_report,
)
from agentic_boilerplate.runtime import (
    CodexAppServerLimitReader,
    CodexLimitSentinelError,
    build_unknown_codex_limit_record,
    codex_resume_scheduler_result_to_dict,
    docker_worker_run_result_to_dict,
    load_rate_limit_payload,
    po_inbox_resume_scheduler_result_to_dict,
    refresh_codex_limit_from_payload,
    resume_po_inbox_blocked_assignments,
    resume_paused_limit_jobs,
    run_docker_worker_once,
)
from agentic_boilerplate.storage import (
    AgentCommunicationStoreError,
    CodexLimitAvailabilityStoreError,
    ContextPackStoreError,
    FileCodexJobStore,
    FileCodexLimitAvailabilityStore,
    FileCodexPauseStore,
    FileContextPackStore,
    FileAgentAssignmentStore,
    FileAgentCommunicationStore,
    AgentAssignmentStoreError,
    FileAssignmentLockStore,
    FileOrchestrationEventQueue,
    FilePOInboxStore,
    InboxItemAlreadyExistsError,
    BacklogDraftStoreError,
    FileBacklogDraftStore,
    OrchestrationEventQueueStoreError,
    POInboxStoreError,
    assignment_lock_to_dict,
    resolve_codex_limit_write_bucket_id,
)
from agentic_boilerplate.storage.documentation_traceability import (
    DocumentationTraceabilityStoreError,
    FileDocumentationTraceabilityReportStore,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""

    parser = argparse.ArgumentParser(prog="agentic", description="Agentic boilerplate local worker tools.")
    parser.add_argument("--env-file", default=".env", help="Path to the dotenv file used for local settings.")
    parser.add_argument("--inbox-root", default="", help="Override the durable PO inbox root directory.")

    subparsers = parser.add_subparsers(dest="resource", required=True)
    _add_setup_parser(subparsers)
    _add_po_inbox_parser(subparsers)
    _add_api_parser(subparsers)
    _add_backlog_draft_parser(subparsers)
    _add_docs_traceability_parser(subparsers)
    _add_context_pack_parser(subparsers)
    _add_docs_site_parser(subparsers)
    _add_codex_limits_parser(subparsers)
    _add_github_parser(subparsers)
    _add_agent_messages_parser(subparsers)
    _add_orchestration_events_parser(subparsers)
    _add_worker_parser(subparsers)
    return parser


def _add_api_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    api = subparsers.add_parser("api", help="Run local API services for operator surfaces.")
    commands = api.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="Serve the local PO inbox/operator API over HTTP.")
    serve.add_argument("--host", default="127.0.0.1", help="Host interface for the local API server.")
    serve.add_argument("--port", default=8000, type=int, help="Port for the local API server.")
    serve.add_argument("--data-root", default="", help="Override the durable platform data root.")
    serve.set_defaults(handler=_handle_api_serve)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.error("No command handler configured.")
    try:
        return handler(args)
    except (
        CodexLimitAvailabilityError,
        CodexLimitAvailabilityStoreError,
        ContextPackSchemaError,
        BacklogDraftStoreError,
        ContextPackStoreError,
        InboxSchemaError,
        GitHubPagesReportPublicationError,
        AgentAssignmentStoreError,
        AgentCommunicationStoreError,
        OrchestrationEventQueueStoreError,
        DocumentationTraceabilityStoreError,
        POInboxStoreError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _add_setup_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    setup = subparsers.add_parser("setup", help="Validate local setup before starting project agents.")
    commands = setup.add_subparsers(dest="command", required=True)

    validate_parser = commands.add_parser("validate", help="Validate first-project configuration and durable paths.")
    validate_parser.add_argument("--project-root", default=".", help="Repository root used for Docker data mount checks.")
    validate_parser.add_argument("--codex-limits-root", default="", help="Override the durable Codex limits root.")
    validate_parser.add_argument("--json", action="store_true", help="Print machine-readable validation output.")
    validate_parser.set_defaults(handler=_handle_setup_validate)

    intake_parser = commands.add_parser(
        "intake",
        help="Run guided project/release intake and create PO inbox blockers for missing start data.",
    )
    intake_parser.add_argument("--project-id", required=True, help="Stable local project identifier.")
    intake_parser.add_argument("--project-name", default="", help="Human-readable project name.")
    intake_parser.add_argument("--release-id", required=True, help="Release or phase identifier for the intake.")
    intake_parser.add_argument("--project-root", default="", help="Target project root. Defaults to TARGET_PROJECT_PATH.")
    intake_parser.add_argument("--target-repository", default="", help="Target implementation repository as owner/name.")
    intake_parser.add_argument("--jira-project-key", default="", help="Jira project key. Defaults to JIRA_PROJECT_KEY.")
    intake_parser.add_argument("--jira-board-id", default="", help="Jira board id. Defaults to JIRA_BOARD_ID.")
    intake_parser.add_argument(
        "--product-docs-root",
        default="docs/product",
        help="Product Owner source document directory, relative to project root unless absolute.",
    )
    intake_parser.add_argument(
        "--architecture-root",
        default="docs/architecture",
        help="Architecture input/output directory, relative to project root unless absolute.",
    )
    intake_parser.add_argument("--evidence-root", default="", help="Durable evidence root.")
    intake_parser.add_argument("--durable-data-root", default="", help="Durable platform data root.")
    intake_parser.add_argument("--report-root", default="", help="Root for generated intake reports.")
    intake_parser.add_argument("--codex-limits-root", default="", help="Override durable Codex limit root.")
    intake_parser.add_argument(
        "--require-confluence",
        action="store_true",
        help="Block readiness when Confluence publication is not configured.",
    )
    intake_parser.add_argument(
        "--no-require-agiletest",
        action="store_true",
        help="Do not block readiness on missing AgileTest credentials.",
    )
    intake_parser.add_argument("--generated-at", default="", help="Override report timestamp.")
    intake_parser.add_argument("--json", action="store_true", help="Print machine-readable intake output.")
    intake_parser.set_defaults(handler=_handle_setup_intake)

    live_diagnostic = commands.add_parser(
        "live-diagnostic",
        help="Run non-mutating integration readiness probes before worker assignment.",
    )
    live_diagnostic.add_argument("--project-root", default=".", help="Boilerplate repository root.")
    live_diagnostic.add_argument(
        "--sample-issue-key",
        default="",
        help="Optional non-critical Jira issue key used to probe transition visibility.",
    )
    live_diagnostic.add_argument(
        "--skip-network",
        action="store_true",
        help="Validate local/configuration contract without external HTTP probes.",
    )
    live_diagnostic.add_argument("--timeout-seconds", default=15, type=int, help="HTTP timeout for live probes.")
    live_diagnostic.add_argument("--json", action="store_true", help="Print machine-readable diagnostic output.")
    live_diagnostic.set_defaults(handler=_handle_setup_live_diagnostic)


def _add_po_inbox_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    po_inbox = subparsers.add_parser("po-inbox", help="Manage durable Product Owner inbox items.")
    commands = po_inbox.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List PO inbox items.")
    list_parser.add_argument("--status", choices=_enum_values(InboxStatus), help="Filter items by status.")
    list_parser.add_argument("--project-id", default="", help="Filter inbox items by project id.")
    list_parser.set_defaults(handler=_handle_list)

    read_parser = commands.add_parser("read", help="Read one PO inbox item.")
    read_parser.add_argument("item_id")
    read_parser.set_defaults(handler=_handle_read)

    create_parser = commands.add_parser("create", help="Create a manual PO inbox item.")
    create_parser.add_argument("--id", required=True, dest="item_id")
    create_parser.add_argument("--type", required=True, choices=_enum_values(InboxMessageType), dest="message_type")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--message", required=True)
    create_parser.add_argument("--agent-role", default=AgentRole.PLATFORM.value, choices=_enum_values(AgentRole))
    create_parser.add_argument("--business-impact", default="")
    create_parser.add_argument("--recommendation", default="")
    create_parser.add_argument("--jira-issue-key", default="")
    create_parser.add_argument("--project-id", default="")
    create_parser.add_argument("--project-name", default="")
    create_parser.add_argument("--project-root", default="")
    create_parser.add_argument("--repository", default="")
    create_parser.add_argument("--jira-project-key", default="")
    create_parser.add_argument("--agent-id", default="")
    create_parser.set_defaults(handler=_handle_create)

    answer_parser = commands.add_parser("answer", help="Answer a blocking question or assumption.")
    answer_parser.add_argument("item_id")
    answer_parser.add_argument("--answer", required=True)
    answer_parser.add_argument("--actor", default="po")
    answer_parser.set_defaults(handler=_handle_answer)

    approve_parser = commands.add_parser("approve", help="Approve an approval request.")
    approve_parser.add_argument("item_id")
    approve_parser.add_argument("--answer", required=True)
    approve_parser.add_argument("--actor", default="po")
    approve_parser.set_defaults(handler=_handle_approve)

    reject_parser = commands.add_parser("reject", help="Reject an approval request.")
    reject_parser.add_argument("item_id")
    reject_parser.add_argument("--answer", required=True)
    reject_parser.add_argument("--actor", default="po")
    reject_parser.set_defaults(handler=_handle_reject)

    resolve_parser = commands.add_parser("resolve", help="Archive a resolvable inbox item.")
    resolve_parser.add_argument("item_id")
    resolve_parser.add_argument("--actor", default="po")
    resolve_parser.add_argument("--note", default="")
    resolve_parser.set_defaults(handler=_handle_resolve)

    import_parser = commands.add_parser("import", help="Import one schema-valid external PO inbox JSON item.")
    import_parser.add_argument("--input", required=True, type=Path, help="External PO inbox JSON item to import.")
    import_parser.set_defaults(handler=_handle_import)

    validate_paths_parser = commands.add_parser(
        "validate-paths",
        help="Detect misplaced target-project PO inbox paths.",
    )
    validate_paths_parser.add_argument(
        "--platform-inbox-root",
        default="",
        help="Override the configured durable platform PO inbox root.",
    )
    validate_paths_parser.add_argument(
        "--target-project-root",
        default="",
        help="Target project root to inspect. Defaults to TARGET_PROJECT_PATH.",
    )
    validate_paths_parser.add_argument("--json", action="store_true", help="Print machine-readable validation output.")
    validate_paths_parser.set_defaults(handler=_handle_validate_po_inbox_paths)


def _add_backlog_draft_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    backlog_draft = subparsers.add_parser(
        "backlog-draft",
        help="Generate and inspect Product Planning backlog draft artifacts.",
    )
    commands = backlog_draft.add_subparsers(dest="command", required=True)

    generate = commands.add_parser(
        "generate",
        help="Generate a durable backlog draft from approved structured source JSON.",
    )
    generate.add_argument("--input", required=True, type=Path, help="Approved backlog source JSON.")
    generate.add_argument("--backlog-draft-root", default="data/backlog-drafts", help="Durable backlog draft root.")
    generate.add_argument("--created-at", default="", help="Override draft timestamp.")
    generate.add_argument("--jira-issue-key", default="", help="Planning story key that produced this draft.")
    generate.add_argument("--context-pack-path", default="", help="Context pack or intake report used for the draft.")
    generate.add_argument("--project-id", default="", help="Project id for generated PO inbox questions.")
    generate.add_argument("--project-name", default="", help="Project name for generated PO inbox questions.")
    generate.add_argument("--project-root", default="", help="Project root for generated PO inbox questions.")
    generate.add_argument("--repository", default="", help="Repository for generated PO inbox questions.")
    generate.add_argument("--jira-project-key", default="", help="Jira project key for generated PO inbox questions.")
    generate.add_argument("--json", action="store_true", help="Print machine-readable generation output.")
    generate.set_defaults(handler=_handle_backlog_draft_generate)

    request_approval = commands.add_parser(
        "request-approval",
        help="Create a PO approval request before creating Jira issues from a draft.",
    )
    request_approval.add_argument("--draft-path", required=True, type=Path, help="Backlog draft JSON path.")
    request_approval.add_argument("--created-at", default="", help="Override approval request timestamp.")
    request_approval.add_argument("--jira-issue-key", default="", help="Planning story key.")
    request_approval.add_argument("--context-pack-path", default="", help="Draft context pack or summary path.")
    request_approval.add_argument("--project-id", default="")
    request_approval.add_argument("--project-name", default="")
    request_approval.add_argument("--project-root", default="")
    request_approval.add_argument("--repository", default="")
    request_approval.add_argument("--jira-project-key", default="")
    request_approval.add_argument("--json", action="store_true")
    request_approval.set_defaults(handler=_handle_backlog_draft_request_approval)

    approval_gate = commands.add_parser(
        "approval-gate",
        help="Check whether a backlog draft has PO approval for Jira creation.",
    )
    approval_gate.add_argument("--draft-path", required=True, type=Path, help="Backlog draft JSON path.")
    approval_gate.add_argument("--approval-item-id", required=True, help="PO inbox approval request id.")
    approval_gate.add_argument("--json", action="store_true")
    approval_gate.set_defaults(handler=_handle_backlog_draft_approval_gate)


def _add_docs_traceability_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    docs_traceability = subparsers.add_parser(
        "docs-traceability",
        help="Audit documentation commitments against Jira/backlog traceability.",
    )
    commands = docs_traceability.add_subparsers(dest="command", required=True)

    audit = commands.add_parser(
        "audit",
        help="Create a durable documentation-to-backlog traceability report.",
    )
    audit.add_argument("--docs-root", action="append", default=[], help="Local Markdown docs root or file.")
    audit.add_argument(
        "--confluence-mirror-root",
        action="append",
        default=[],
        help="Local Markdown mirror root or file for Confluence/source docs.",
    )
    audit.add_argument("--jira-issues-json", required=True, type=Path, help="JSON array of Jira-like issue metadata.")
    audit.add_argument(
        "--report-root",
        default="data/documentation-traceability-reports",
        help="Durable traceability report root.",
    )
    audit.add_argument("--report-id", required=True, help="Stable report id.")
    audit.add_argument("--created-at", default="", help="Override report timestamp.")
    audit.add_argument("--project-id", required=True, help="Project id included in every report row.")
    audit.add_argument("--project-name", default="", help="Human-readable project name.")
    audit.add_argument("--jira-project-key", required=True, help="Jira project key included in every report row.")
    audit.add_argument("--confluence-space", default="", help="Optional Confluence space key/name.")
    audit.add_argument("--release-target", default="", help="Release target included in every report row.")
    audit.add_argument(
        "--follow-up-policy",
        choices=[policy.value for policy in TraceabilityFollowUpPolicy],
        default=TraceabilityFollowUpPolicy.REPORT_ONLY.value,
        help="How missing implementation-worthy items are routed.",
    )
    audit.add_argument("--json", action="store_true", help="Print machine-readable audit output.")
    audit.set_defaults(handler=_handle_docs_traceability_audit)


def _add_context_pack_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    context_pack = subparsers.add_parser("context-pack", help="Generate durable worker context packs.")
    commands = context_pack.add_subparsers(dest="command", required=True)

    generate_parser = commands.add_parser("generate", help="Generate a context pack from approved source JSON.")
    generate_parser.add_argument("--input", required=True, type=Path, help="Approved context source JSON file.")
    generate_parser.add_argument(
        "--context-pack-root",
        default="",
        help="Override the durable context pack root directory.",
    )
    generate_parser.add_argument(
        "--codex-jobs-root",
        default="data/codex-jobs",
        help="Root used when recording the expected Codex job path.",
    )
    generate_parser.add_argument(
        "--codex-results-root",
        default="data/codex-results",
        help="Root used when recording the expected Codex result path.",
    )
    generate_parser.set_defaults(handler=_handle_context_pack_generate)

    generate_from_draft = commands.add_parser(
        "generate-from-backlog-draft",
        help="Generate one draft context pack per story in a saved backlog draft.",
    )
    generate_from_draft.add_argument("--draft-path", required=True, type=Path, help="Backlog draft JSON path.")
    generate_from_draft.add_argument("--context-pack-root", default="data/context-packs")
    generate_from_draft.add_argument("--codex-jobs-root", default="data/codex-jobs")
    generate_from_draft.add_argument("--codex-results-root", default="data/codex-results")
    generate_from_draft.add_argument("--target-repo-path", required=True)
    generate_from_draft.add_argument("--created-at", default="")
    generate_from_draft.add_argument("--default-role", default=AgentRole.DEVELOPER.value, choices=_enum_values(AgentRole))
    generate_from_draft.add_argument("--default-sprint", default="Draft backlog")
    generate_from_draft.add_argument("--role-instruction-version", default="release-1.2")
    generate_from_draft.add_argument(
        "--documentation-reference",
        action="append",
        default=[],
        help="Approved documentation reference as path or path=description. Repeat for multiple references.",
    )
    generate_from_draft.add_argument(
        "--shared-context",
        action="append",
        default=[],
        help="Extra shared context line included in every generated pack.",
    )
    generate_from_draft.add_argument("--json", action="store_true")
    generate_from_draft.set_defaults(handler=_handle_context_pack_generate_from_backlog_draft)


def _add_docs_site_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    docs_site = subparsers.add_parser("docs-site", help="Build and validate the GitHub Pages docs scaffold.")
    commands = docs_site.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate docs site navigation and local links.")
    validate.add_argument("--docs-root", default="docs")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(handler=_handle_docs_site_validate)

    build = commands.add_parser("build", help="Build a static HTML docs site from Markdown.")
    build.add_argument("--docs-root", default="docs")
    build.add_argument("--output-root", default="site")
    build.add_argument("--json", action="store_true")
    build.set_defaults(handler=_handle_docs_site_build)

    publish_reports = commands.add_parser(
        "publish-reports",
        help="Publish curated report summaries into the GitHub Pages docs tree.",
    )
    publish_reports.add_argument("--input", required=True, type=Path, help="Report publication source JSON.")
    publish_reports.add_argument("--docs-root", default="docs")
    publish_reports.add_argument("--retry-root", default="data/publication-retries")
    publish_reports.add_argument("--project-root", default=".")
    publish_reports.add_argument("--json", action="store_true")
    publish_reports.set_defaults(handler=_handle_docs_site_publish_reports)


def _add_codex_limits_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    codex_limits = subparsers.add_parser("codex-limits", help="Manage Codex limit availability records.")
    commands = codex_limits.add_subparsers(dest="command", required=True)

    record_parser = commands.add_parser("record", help="Record the current Codex limit availability.")
    record_parser.add_argument("--id", required=True, dest="record_id")
    record_parser.add_argument(
        "--plan-mode",
        default=CodexLimitPlanMode.DUAL_WINDOW.value,
        choices=_enum_values(CodexLimitPlanMode),
        help="How visible Codex limit windows should be interpreted.",
    )
    record_parser.add_argument(
        "--short-status",
        "--five-hour-status",
        required=True,
        choices=_enum_values(CodexLimitWindowStatus),
    )
    record_parser.add_argument("--short-remaining", "--five-hour-remaining", type=int)
    record_parser.add_argument("--short-reset-at", "--five-hour-reset-at", default="")
    record_parser.add_argument("--short-window-id", "--five-hour-window-id", default="")
    record_parser.add_argument("--short-label", "--five-hour-label", default="")
    record_parser.add_argument(
        "--broad-status",
        "--weekly-status",
        "--monthly-status",
        choices=_enum_values(CodexLimitWindowStatus),
    )
    record_parser.add_argument("--broad-remaining", "--weekly-remaining", "--monthly-remaining", type=int)
    record_parser.add_argument("--broad-reset-at", "--weekly-reset-at", "--monthly-reset-at", default="")
    record_parser.add_argument("--broad-window-id", "--weekly-window-id", "--monthly-window-id", default="")
    record_parser.add_argument("--broad-label", "--weekly-label", "--monthly-label", default="")
    record_parser.add_argument(
        "--source",
        default=CodexLimitObservationSource.OPERATOR.value,
        choices=_enum_values(CodexLimitObservationSource),
    )
    record_parser.add_argument("--observed-at", default="")
    record_parser.add_argument("--note", default="")
    record_parser.add_argument("--account-scope-id", default="")
    record_parser.add_argument("--bucket-id", default="")
    record_parser.add_argument("--codex-limits-root", default="")
    record_parser.set_defaults(handler=_handle_codex_limits_record)

    refresh_parser = commands.add_parser("refresh", help="Refresh Codex limits from a host-side sentinel.")
    refresh_parser.add_argument("--id", default="", dest="record_id")
    refresh_parser.add_argument(
        "--payload-json",
        type=Path,
        default=None,
        help="Offline app-server payload JSON for diagnostics/tests. If omitted, the configured app-server is called.",
    )
    refresh_parser.add_argument("--app-server-command", default="")
    refresh_parser.add_argument(
        "--bucket-id",
        default="",
        help="Applicable metered bucket. Empty uses the App Server rateLimits.limitId.",
    )
    refresh_parser.add_argument("--timeout-seconds", default=15, type=int)
    refresh_parser.add_argument("--cutoff-percent", default=None, type=int)
    refresh_parser.add_argument("--observed-at", default="")
    refresh_parser.add_argument("--note", default="")
    refresh_parser.add_argument("--account-scope-id", default="")
    refresh_parser.add_argument("--codex-limits-root", default="")
    refresh_parser.set_defaults(handler=_handle_codex_limits_refresh)

    latest_parser = commands.add_parser("latest", help="Print the latest Codex limit gate decision.")
    latest_parser.add_argument("--codex-limits-root", default="")
    latest_parser.add_argument("--stale-after-seconds", default=None, type=int)
    latest_parser.add_argument("--now", default="")
    latest_parser.add_argument("--account-scope-id", default="")
    latest_parser.add_argument("--bucket-id", default="")
    latest_parser.add_argument("--json", action="store_true")
    latest_parser.set_defaults(handler=_handle_codex_limits_latest)

    status_parser = commands.add_parser("status", help="Print readable Codex limit capacity for operators.")
    status_parser.add_argument("--codex-limits-root", default="")
    status_parser.add_argument("--stale-after-seconds", default=None, type=int)
    status_parser.add_argument("--now", default="")
    status_parser.add_argument("--account-scope-id", default="")
    status_parser.add_argument("--bucket-id", default="")
    status_parser.set_defaults(handler=_handle_codex_limits_status)


def _add_agent_messages_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    messages = subparsers.add_parser("agent-messages", help="Manage durable agent communication messages.")
    commands = messages.add_subparsers(dest="command", required=True)

    publish = commands.add_parser("publish", help="Publish one durable agent communication message.")
    publish.add_argument("--message-root", default="", help="Override the durable agent message store root.")
    publish.add_argument("--id", required=True, dest="message_id")
    publish.add_argument("--type", required=True, choices=_enum_values(AgentMessageType), dest="message_type")
    publish.add_argument("--idempotency-key", default="")
    publish.add_argument("--source-role", required=True, choices=_enum_values(AgentRole))
    publish.add_argument("--target-role", default="", choices=["", *_enum_values(AgentRole)])
    publish.add_argument("--target-channel", default="", choices=["", *_enum_values(AgentCommunicationChannel)])
    publish.add_argument("--target-worker-id", default="")
    publish.add_argument("--source-worker-id", default="")
    publish.add_argument("--origin-actor", default="worker")
    publish.add_argument("--project-id", required=True)
    publish.add_argument("--project-name", default="")
    publish.add_argument("--project-root", default="")
    publish.add_argument("--repository", default="")
    publish.add_argument("--jira-project-key", default="")
    publish.add_argument("--sprint-id", default="")
    publish.add_argument("--sprint-name", default="")
    publish.add_argument("--jira-issue-key", default="")
    publish.add_argument("--assignment-id", default="")
    publish.add_argument("--priority", default=AgentMessagePriority.NORMAL.value, choices=_enum_values(AgentMessagePriority))
    publish.add_argument("--correlation-id", default="")
    publish.add_argument("--causation-id", default="")
    publish.add_argument("--payload-json", default="{}", help="Small JSON object carried with the message.")
    publish.add_argument("--artifact-ref", action="append", default=[])
    publish.add_argument("--requires-acknowledgement", action="store_true")
    publish.add_argument("--expires-at", default="")
    publish.add_argument("--created-at", default="")
    publish.add_argument("--json", action="store_true")
    publish.set_defaults(handler=_handle_agent_messages_publish)

    publish_handoff = commands.add_parser(
        "publish-handoff",
        help="Publish the deterministic next-role handoff message for one story-path event.",
    )
    publish_handoff.add_argument("--message-root", default="", help="Override the durable agent message store root.")
    publish_handoff.add_argument("--id", required=True, dest="message_id")
    publish_handoff.add_argument("--current-status", required=True)
    publish_handoff.add_argument("--event", required=True, choices=_enum_values(StoryPathEvent))
    publish_handoff.add_argument("--actor", required=True, choices=_enum_values(StoryPathRole))
    publish_handoff.add_argument("--target-status", default="")
    publish_handoff.add_argument("--project-id", required=True)
    publish_handoff.add_argument("--project-name", default="")
    publish_handoff.add_argument("--project-root", default="")
    publish_handoff.add_argument("--repository", default="")
    publish_handoff.add_argument("--jira-project-key", default="")
    publish_handoff.add_argument("--sprint-id", default="")
    publish_handoff.add_argument("--sprint-name", default="")
    publish_handoff.add_argument("--jira-issue-key", required=True)
    publish_handoff.add_argument("--assignment-id", required=True)
    publish_handoff.add_argument("--workspace-path", required=True)
    publish_handoff.add_argument("--context-pack-path", required=True)
    publish_handoff.add_argument("--evidence-path", required=True)
    publish_handoff.add_argument("--communication-channel-id", required=True)
    publish_handoff.add_argument("--source-worker-id", default="")
    publish_handoff.add_argument("--branch-name", default="")
    publish_handoff.add_argument("--pull-request-url", default="")
    publish_handoff.add_argument("--merge-sha", default="")
    publish_handoff.add_argument("--correlation-id", default="")
    publish_handoff.add_argument("--causation-id", default="")
    publish_handoff.add_argument("--artifact", action="append", default=[], help="Required artifact as name=value.")
    publish_handoff.add_argument("--payload-json", default="{}", help="Small JSON object carried with the message.")
    publish_handoff.add_argument("--created-at", default="")
    publish_handoff.add_argument(
        "--no-blocked-message",
        action="store_true",
        help="Return blocked decision without persisting the blocked handoff message.",
    )
    publish_handoff.add_argument("--json", action="store_true")
    publish_handoff.set_defaults(handler=_handle_agent_messages_publish_handoff)

    list_messages = commands.add_parser("list", help="List durable agent communication messages.")
    list_messages.add_argument("--message-root", default="", help="Override the durable agent message store root.")
    list_messages.add_argument("--status", choices=_enum_values(AgentMessageStatus))
    list_messages.add_argument("--project-id", default="")
    list_messages.add_argument("--jira-issue-key", default="")
    list_messages.add_argument("--assignment-id", default="")
    list_messages.add_argument("--target-role", default="", choices=["", *_enum_values(AgentRole)])
    list_messages.add_argument("--target-channel", default="", choices=["", *_enum_values(AgentCommunicationChannel)])
    list_messages.add_argument("--type", default="", choices=["", *_enum_values(AgentMessageType)], dest="message_type")
    list_messages.add_argument("--json", action="store_true")
    list_messages.set_defaults(handler=_handle_agent_messages_list)

    acknowledge = commands.add_parser("ack", help="Acknowledge one agent communication message.")
    acknowledge.add_argument("message_id")
    acknowledge.add_argument("--message-root", default="", help="Override the durable agent message store root.")
    acknowledge.add_argument("--acknowledged-at", default="")
    acknowledge.add_argument("--json", action="store_true")
    acknowledge.set_defaults(handler=_handle_agent_messages_ack)

    consume = commands.add_parser("consume", help="Mark one agent communication message consumed.")
    consume.add_argument("message_id")
    consume.add_argument("--message-root", default="", help="Override the durable agent message store root.")
    consume.add_argument("--consumed-at", default="")
    consume.add_argument("--json", action="store_true")
    consume.set_defaults(handler=_handle_agent_messages_consume)

    reject = commands.add_parser("reject", help="Reject one agent communication message with a durable reason.")
    reject.add_argument("message_id")
    reject.add_argument("--message-root", default="", help="Override the durable agent message store root.")
    reject.add_argument("--reason", required=True)
    reject.add_argument("--rejected-at", default="")
    reject.add_argument("--json", action="store_true")
    reject.set_defaults(handler=_handle_agent_messages_reject)


def _add_orchestration_events_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    events = subparsers.add_parser("orchestration-events", help="Manage durable orchestration trigger events.")
    commands = events.add_subparsers(dest="command", required=True)

    enqueue = commands.add_parser("enqueue", help="Create one durable orchestration event idempotently.")
    enqueue.add_argument("--event-store-root", default="", help="Override the durable event store root.")
    enqueue.add_argument("--id", required=True, dest="event_id")
    enqueue.add_argument("--type", required=True, choices=_enum_values(OrchestrationEventType), dest="event_type")
    enqueue.add_argument("--idempotency-key", default="")
    enqueue.add_argument("--source-role", required=True, choices=_enum_values(AgentRole))
    enqueue.add_argument("--target-role", default="", choices=["", *_enum_values(AgentRole)])
    enqueue.add_argument("--jira-issue-key", default="")
    enqueue.add_argument("--source-assignment-id", default="")
    enqueue.add_argument("--project-id", default="")
    enqueue.add_argument("--project-name", default="")
    enqueue.add_argument("--project-root", default="")
    enqueue.add_argument("--repository", default="")
    enqueue.add_argument("--jira-project-key", default="")
    enqueue.add_argument("--correlation-id", default="")
    enqueue.add_argument("--scope-key", default="")
    enqueue.add_argument("--payload-json", default="{}", help="Small JSON object carried with the event.")
    enqueue.add_argument("--evidence-path", action="append", default=[])
    enqueue.add_argument("--created-at", default="")
    enqueue.add_argument("--json", action="store_true")
    enqueue.set_defaults(handler=_handle_orchestration_events_enqueue)

    list_events = commands.add_parser("list", help="List orchestration events.")
    list_events.add_argument("--event-store-root", default="", help="Override the durable event store root.")
    list_events.add_argument("--status", choices=_enum_values(OrchestrationEventStatus))
    list_events.add_argument("--project-id", default="", help="Filter orchestration events by project id.")
    list_events.add_argument("--json", action="store_true")
    list_events.set_defaults(handler=_handle_orchestration_events_list)

    claim_next = commands.add_parser("claim-next", help="Claim the oldest queued event for worker processing.")
    claim_next.add_argument("--event-store-root", default="", help="Override the durable event store root.")
    claim_next.add_argument("--updated-at", default="")
    claim_next.add_argument("--json", action="store_true")
    claim_next.set_defaults(handler=_handle_orchestration_events_claim_next)

    complete = commands.add_parser("complete", help="Mark one orchestration event processed.")
    complete.add_argument("event_id")
    complete.add_argument("--event-store-root", default="", help="Override the durable event store root.")
    complete.add_argument("--processed-at", default="")
    complete.add_argument("--json", action="store_true")
    complete.set_defaults(handler=_handle_orchestration_events_complete)

    reject = commands.add_parser("reject", help="Reject one orchestration event with a durable reason.")
    reject.add_argument("event_id")
    reject.add_argument("--event-store-root", default="", help="Override the durable event store root.")
    reject.add_argument("--reason", required=True)
    reject.add_argument("--rejected-at", default="")
    reject.add_argument("--json", action="store_true")
    reject.set_defaults(handler=_handle_orchestration_events_reject)


def _add_worker_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    worker = subparsers.add_parser("worker", help="Run local Docker worker loops.")
    commands = worker.add_subparsers(dest="command", required=True)

    run_once = commands.add_parser("run-once", help="Register a worker and poll one durable assignment.")
    run_once.add_argument("--role", required=True, choices=_enum_values(AgentRole))
    run_once.add_argument("--worker-id", default="")
    run_once.add_argument("--container-name", default="")
    run_once.add_argument("--workspace-path", default="")
    run_once.add_argument("--assignment-store-root", default="")
    run_once.add_argument("--lock-store-root", default="")
    run_once.add_argument("--limit-store-root", default="")
    run_once.add_argument("--logs-root", default="")
    run_once.add_argument("--checkpoint-store-root", default="")
    run_once.add_argument(
        "--codex-execution-mode",
        default="host_side",
        choices=("host_side", "direct_container"),
        help="Execution bridge mode. direct_container fails safely in this release.",
    )
    run_once.add_argument("--check-integrations", action="store_true")
    run_once.add_argument(
        "--execute",
        action="store_true",
        help="Leave dry-run mode. Codex-backed execution is still delegated to the host runner boundary.",
    )
    run_once.set_defaults(handler=_handle_worker_run_once)

    status = commands.add_parser("status", help="List paused and blocked worker assignments.")
    status.add_argument("--assignment-store-root", default="")
    status.add_argument("--project-id", default="", help="Filter assignments by project id.")
    status.add_argument("--json", action="store_true", help="Print machine-readable status output.")
    status.set_defaults(handler=_handle_worker_status)

    pause_for_po = commands.add_parser(
        "pause-for-po",
        help="Create a PO inbox blocker and pause one assignment with resume context.",
    )
    pause_for_po.add_argument("--assignment-store-root", default="")
    pause_for_po.add_argument("--assignment-id", required=True)
    pause_for_po.add_argument("--worker-id", required=True)
    pause_for_po.add_argument("--project-id", required=True)
    pause_for_po.add_argument("--question", required=True)
    pause_for_po.add_argument("--response-needed", required=True)
    pause_for_po.add_argument("--resume-context", required=True)
    pause_for_po.add_argument("--resume-context-path", default="")
    pause_for_po.add_argument("--title", default="")
    pause_for_po.add_argument("--business-impact", default="")
    pause_for_po.add_argument("--recommendation", default="")
    pause_for_po.add_argument("--agent-id", default="")
    pause_for_po.add_argument("--paused-at", default="")
    pause_for_po.add_argument("--inbox-item-id", default="")
    pause_for_po.add_argument("--json", action="store_true", help="Print machine-readable pause result.")
    pause_for_po.set_defaults(handler=_handle_worker_pause_for_po)

    resume_po = commands.add_parser(
        "resume-po-inbox",
        help="Requeue PO-inbox paused assignments after answered or approved blockers.",
    )
    resume_po.add_argument("--assignment-store-root", default="")
    resume_po.add_argument("--resumed-at", default="")
    resume_po.add_argument(
        "--eligible-issue-key",
        action="append",
        default=[],
        help="Jira issue key that passed normal gates. Repeat for multiple keys.",
    )
    resume_po.add_argument("--json", action="store_true", help="Print machine-readable resume result.")
    resume_po.set_defaults(handler=_handle_worker_resume_po_inbox)

    failed_requests = commands.add_parser("failed-requests", help="List durable failed Codex request artifacts.")
    failed_requests.add_argument("--codex-jobs-root", default="")
    failed_requests.add_argument("--json", action="store_true", help="Print machine-readable failed request output.")
    failed_requests.set_defaults(handler=_handle_worker_failed_requests)

    resume_paused = commands.add_parser("resume-paused", help="Requeue paused Codex jobs when limit capacity allows.")
    resume_paused.add_argument("--codex-jobs-root", default="")
    resume_paused.add_argument("--limit-store-root", default="")
    resume_paused.add_argument("--resumed-at", default="")
    resume_paused.add_argument("--stale-after-seconds", default=None, type=int)
    resume_paused.add_argument(
        "--eligible-issue-key",
        action="append",
        default=[],
        help="Optional Jira issue key that remains dependency/status eligible. Repeat for multiple keys.",
    )
    resume_paused.add_argument("--json", action="store_true", help="Print machine-readable resume result.")
    resume_paused.set_defaults(handler=_handle_worker_resume_paused)

    locks = commands.add_parser("locks", help="Inspect and safely release assignment locks.")
    lock_commands = locks.add_subparsers(dest="lock_command", required=True)

    list_locks = lock_commands.add_parser("list", help="List durable assignment locks.")
    list_locks.add_argument("--lock-store-root", default="")
    list_locks.add_argument("--status", choices=_enum_values(AssignmentLockStatus))
    list_locks.add_argument("--json", action="store_true")
    list_locks.set_defaults(handler=_handle_worker_locks_list)

    mark_stale = lock_commands.add_parser("mark-stale", help="Mark active locks stale when they exceed the stale window.")
    mark_stale.add_argument("--lock-store-root", default="")
    mark_stale.add_argument("--checked-at", required=True)
    mark_stale.add_argument("--stale-after-seconds", required=True, type=int)
    mark_stale.add_argument("--json", action="store_true")
    mark_stale.set_defaults(handler=_handle_worker_locks_mark_stale)

    release_lock = lock_commands.add_parser("release", help="Release one selected assignment lock.")
    release_lock.add_argument("--lock-store-root", default="")
    release_lock.add_argument("--jira-issue-key", required=True)
    release_lock.add_argument("--role", required=True, choices=_enum_values(AgentRole))
    release_lock.add_argument("--worker-session-id", required=True)
    release_lock.add_argument("--released-at", required=True)
    release_lock.add_argument(
        "--reason",
        required=True,
        choices=_enum_values(AssignmentLockReleaseReason),
    )
    release_lock.add_argument("--audit-note", required=True)
    release_lock.add_argument("--confirm", action="store_true")
    release_lock.add_argument("--allow-active", action="store_true")
    release_lock.add_argument("--json", action="store_true")
    release_lock.set_defaults(handler=_handle_worker_locks_release)


def _add_github_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    github = subparsers.add_parser("github", help="Manage local GitHub integration helpers.")
    commands = github.add_subparsers(dest="command", required=True)

    configure = commands.add_parser(
        "configure-token-auth",
        help="Configure the local Git repository to use GITHUB_TOKEN/GH_TOKEN over HTTPS.",
    )
    configure.add_argument("--repo-path", default=".", help="Local Git repository path to configure.")
    configure.add_argument("--remote", default="origin", help="Git remote name to update.")
    configure.add_argument(
        "--helper-source-root",
        default="",
        help=(
            "Optional boilerplate src path for target repos that do not have "
            "agentic installed as a console command."
        ),
    )
    configure.set_defaults(handler=_handle_github_configure_token_auth)

    credential_fill = commands.add_parser(
        "credential-fill",
        help="Git credential helper that reads GITHUB_TOKEN/GH_TOKEN from the configured env file.",
    )
    credential_fill.add_argument("operation", nargs="?", default="get")
    credential_fill.set_defaults(handler=_handle_github_credential_fill)

    ssh_diagnostic = commands.add_parser(
        "ssh-auth-diagnostic",
        help="Validate Docker Git SSH auth configuration and optionally run safe Git permission probes.",
    )
    ssh_diagnostic.add_argument("--ssh-dir", default="", help="Ephemeral directory for value-supplied SSH keys.")
    ssh_diagnostic.add_argument("--repo-path", default=".", help="Local Git repository path used for push dry-runs.")
    ssh_diagnostic.add_argument(
        "--probe-branch",
        default="agentic/ssh-auth-diagnostic",
        help="Temporary branch ref used for git push --dry-run permission checks.",
    )
    ssh_diagnostic.add_argument(
        "--execute",
        action="store_true",
        help="Run network Git probes. Without this flag, print the redacted plan only.",
    )
    ssh_diagnostic.add_argument("--json", action="store_true", help="Print machine-readable diagnostic output.")
    ssh_diagnostic.set_defaults(handler=_handle_github_ssh_auth_diagnostic)


def _handle_list(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    status = InboxStatus(args.status) if args.status else None
    items = store.list_items(status=status, project_id=args.project_id)
    for item in items:
        print(f"{item.id}\t{item.status.value}\t{item.message_type.value}\t{item.title}\t{item.project_id}")
    return 0


def _handle_api_serve(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    inbox_root = Path(args.inbox_root) if args.inbox_root else settings.paths.po_inbox
    data_root = Path(args.data_root) if args.data_root else _infer_data_root(inbox_root)
    stale_after_seconds = settings.codex_limit_sentinel.stale_after_seconds
    serve_local_api(
        inbox_root=inbox_root,
        data_root=data_root,
        host=args.host,
        port=args.port,
        limit_account_scope_id=settings.codex_limit_sentinel.account_scope_id,
        limit_bucket_id=settings.codex_limit_sentinel.bucket_id,
        limit_stale_after_seconds=(
            stale_after_seconds if stale_after_seconds > 0 else None
        ),
        limit_future_tolerance_seconds=(
            settings.codex_limit_sentinel.future_tolerance_seconds
        ),
    )
    return 0


def _handle_read(args: argparse.Namespace) -> int:
    item = _store_from_args(args).read(args.item_id)
    print(json.dumps(inbox_item_to_dict(item), indent=2, sort_keys=True))
    return 0


def _handle_create(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    timestamp = _utc_now()
    item = POInboxItem(
        id=args.item_id,
        message_type=InboxMessageType(args.message_type),
        status=InboxStatus.OPEN,
        title=args.title,
        message=args.message,
        agent_role=AgentRole(args.agent_role),
        created_at=timestamp,
        agent_id=args.agent_id,
        jira_issue_key=args.jira_issue_key,
        project_id=args.project_id,
        project_name=args.project_name,
        project_root=args.project_root,
        repository=args.repository,
        jira_project_key=args.jira_project_key,
        business_impact=args.business_impact,
        recommendation=args.recommendation,
        audit=(
            InboxAuditEvent(
                timestamp=timestamp,
                actor=args.agent_id or args.agent_role,
                action="created",
                note="Created by PO inbox CLI.",
            ),
        ),
    )
    location = store.create(item)
    print(f"created\t{location.item_id}\t{location.status.value}\t{location.path}")
    return 0


def _handle_import(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    item = load_external_po_inbox_item(args.input)
    location = store.create(item)
    print(f"imported\t{location.item_id}\t{location.status.value}\t{location.path}")
    return 0


def _handle_validate_po_inbox_paths(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    platform_inbox_root = (
        Path(args.platform_inbox_root)
        if args.platform_inbox_root
        else (Path(args.inbox_root) if args.inbox_root else settings.paths.po_inbox)
    )
    target_project_root = Path(args.target_project_root) if args.target_project_root else Path(settings.workers.target_project_path)
    result = validate_po_inbox_paths(
        platform_inbox_root=platform_inbox_root,
        target_project_root=target_project_root,
    )
    if args.json:
        print(json.dumps(_po_inbox_path_guard_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(format_po_inbox_path_guard_result(result))
    return 0 if result.passed else 1


def _handle_backlog_draft_generate(args: argparse.Namespace) -> int:
    with args.input.open("r", encoding="utf-8-sig") as file:
        source = json.load(file)
    requirement = requirement_input_from_dict(source)
    created_at = args.created_at or _utc_now()
    draft = create_backlog_draft(requirement, created_at=created_at)
    store = FileBacklogDraftStore(args.backlog_draft_root)
    location = store.save(draft)
    question_items = build_missing_business_decision_questions(
        draft,
        created_at=created_at,
        jira_issue_key=args.jira_issue_key,
        context_pack_path=args.context_pack_path,
    )
    inbox_locations = _create_backlog_draft_po_questions(args, question_items)
    payload = {
        "draft_key": draft.key,
        "draft_path": str(location.path),
        "epic_count": len(draft.epics),
        "story_count": sum(len(epic.stories) for epic in draft.epics),
        "dependency_count": sum(
            len(story.dependencies)
            for epic in draft.epics
            for story in epic.stories
        ),
        "sprint_ring_count": len(draft.sprint_rings),
        "missing_business_decision_count": len(draft.missing_business_decisions),
        "po_inbox_items": [
            {
                "id": location.item_id,
                "status": location.status.value,
                "path": str(location.path),
            }
            for location in inbox_locations
        ],
        "draft": backlog_draft_to_dict(draft),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "generated\t"
            f"{draft.key}\t{location.path}\t"
            f"epics={payload['epic_count']}\t"
            f"stories={payload['story_count']}\t"
            f"sprint_rings={payload['sprint_ring_count']}"
        )
        for inbox_location in inbox_locations:
            print(f"po_inbox\t{inbox_location.item_id}\t{inbox_location.status.value}\t{inbox_location.path}")
    return 0 if not draft.missing_business_decisions else 1


def _handle_backlog_draft_request_approval(args: argparse.Namespace) -> int:
    draft = _backlog_draft_from_path(args.draft_path)
    item = build_backlog_creation_approval_request(
        draft,
        created_at=args.created_at or _utc_now(),
        jira_issue_key=args.jira_issue_key,
        project_id=args.project_id,
        project_name=args.project_name,
        project_root=args.project_root,
        repository=args.repository,
        jira_project_key=args.jira_project_key,
        context_pack_path=args.context_pack_path,
    )
    store = _store_from_args(args)
    try:
        location = store.create(item)
    except InboxItemAlreadyExistsError:
        location = store.locate(item.id)
    payload = {
        "draft_key": draft.key,
        "approval_item_id": item.id,
        "status": location.status.value,
        "path": str(location.path),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"approval-request\t{item.id}\t{location.status.value}\t{location.path}")
    return 0


def _handle_backlog_draft_approval_gate(args: argparse.Namespace) -> int:
    draft = _backlog_draft_from_path(args.draft_path)
    try:
        approval_item = _store_from_args(args).read(args.approval_item_id)
    except POInboxStoreError:
        approval_item = None
    decision = evaluate_backlog_creation_approval_gate(draft, approval_item)
    payload = {
        "draft_key": draft.key,
        **backlog_approval_gate_decision_to_dict(decision),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "approval-gate\t"
            f"{draft.key}\t{decision.status.value}\t"
            f"can_create_jira={decision.can_create_jira}\t{decision.reason}"
        )
    return 0 if decision.can_create_jira else 1


def _handle_docs_traceability_audit(args: argparse.Namespace) -> int:
    created_at = args.created_at or _utc_now()
    project = DocumentationTraceabilityProject(
        project_id=args.project_id,
        project_name=args.project_name,
        jira_project_key=args.jira_project_key,
        docs_roots=tuple(args.docs_root),
        confluence_mirror_roots=tuple(args.confluence_mirror_root),
        confluence_space=args.confluence_space,
        release_target=args.release_target,
    )
    report = audit_documentation_traceability(
        DocumentationTraceabilityAuditConfig(
            report_id=args.report_id,
            created_at=created_at,
            project=project,
        ),
        jira_issues=_load_documentation_traceability_issues(args.jira_issues_json),
    )
    location = FileDocumentationTraceabilityReportStore(args.report_root).save(report)
    follow_up_plan = build_traceability_follow_up_plan(
        report,
        policy=TraceabilityFollowUpPolicy(args.follow_up_policy),
        created_at=created_at,
    )
    inbox_locations = _create_traceability_po_questions(args, follow_up_plan.po_inbox_questions)
    payload = {
        "report_id": report.id,
        "report_path": str(location.path),
        "summary": report.summary,
        "follow_up_policy": follow_up_plan.policy.value,
        "draft_candidates": traceability_follow_up_plan_to_dict(follow_up_plan)["draft_candidates"],
        "po_inbox_items": [
            {
                "id": location.item_id,
                "status": location.status.value,
                "path": str(location.path),
            }
            for location in inbox_locations
        ],
        "report": documentation_traceability_report_to_dict(report),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "docs-traceability\t"
            f"{report.id}\t{location.path}\t"
            f"missing={report.summary['missing-jira-reflection']}\t"
            f"po_needed={report.summary['needs-po-decision']}"
        )
        for candidate in payload["draft_candidates"]:
            print(f"draft-candidate\t{candidate['id']}\t{candidate['target_status']}\t{candidate['title']}")
        for inbox_location in inbox_locations:
            print(f"po_inbox\t{inbox_location.item_id}\t{inbox_location.status.value}\t{inbox_location.path}")
    return 1 if report.has_missing_or_po_needed else 0


def _handle_context_pack_generate(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    with args.input.open("r", encoding="utf-8-sig") as file:
        source = context_pack_build_input_from_dict(json.load(file))
    context_pack_root = Path(args.context_pack_root) if args.context_pack_root else settings.paths.context_packs
    context_pack = build_context_pack(
        source,
        context_pack_root=str(context_pack_root),
        codex_jobs_root=args.codex_jobs_root,
        codex_results_root=args.codex_results_root,
    )
    location = FileContextPackStore(context_pack_root).write(context_pack)
    print(f"created\t{location.issue_key}\t{location.markdown_path}\t{location.json_path}")
    return 0


def _handle_context_pack_generate_from_backlog_draft(args: argparse.Namespace) -> int:
    with args.draft_path.open("r", encoding="utf-8-sig") as file:
        draft = backlog_draft_from_dict(json.load(file))
    references = _context_pack_documentation_references(args.documentation_reference)
    result = generate_context_packs_from_backlog_draft(
        draft,
        BacklogContextPackGenerationConfig(
            created_at=args.created_at or _utc_now(),
            target_repo_path=args.target_repo_path,
            context_pack_root=args.context_pack_root,
            codex_jobs_root=args.codex_jobs_root,
            codex_results_root=args.codex_results_root,
            default_role=AgentRole(args.default_role),
            default_sprint=args.default_sprint,
            role_instruction_version=args.role_instruction_version,
            documentation_references=references,
            shared_context=tuple(args.shared_context),
        ),
    )
    store = FileContextPackStore(args.context_pack_root)
    locations = tuple(store.write(item.context_pack) for item in result.items)
    payload = {
        **backlog_context_pack_generation_result_to_dict(result),
        "locations": [
            {
                "issue_key": location.issue_key,
                "markdown_path": str(location.markdown_path),
                "json_path": str(location.json_path),
            }
            for location in locations
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"created\t{result.draft_key}\tcontext_packs={len(locations)}")
        for location in locations:
            print(f"context_pack\t{location.issue_key}\t{location.markdown_path}\t{location.json_path}")
    return 0


def _handle_docs_site_validate(args: argparse.Namespace) -> int:
    result = validate_docs_site(args.docs_root)
    payload = docs_site_validation_to_dict(result)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"docs-site\tvalidate\tpassed={result.passed}\tmissing={len(result.missing_paths)}\tbroken={len(result.broken_links)}")
        for item in result.missing_paths:
            print(f"missing\t{item}")
        for item in result.broken_links:
            print(f"broken-link\t{item}")
    return 0 if result.passed else 1


def _handle_docs_site_build(args: argparse.Namespace) -> int:
    result = build_docs_site(args.docs_root, args.output_root)
    payload = docs_site_build_to_dict(result)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"docs-site\tbuild\t{result.output_root}\tfiles={len(result.written_files)}")
        for item in result.written_files:
            print(f"written\t{item}")
    return 0


def _handle_docs_site_publish_reports(args: argparse.Namespace) -> int:
    with args.input.open("r", encoding="utf-8-sig") as file:
        source = json.load(file)
    publication_input = report_publication_input_from_dict(source)
    result = publish_report_artifacts_to_docs(
        publication_input,
        docs_root=args.docs_root,
        retry_root=args.retry_root,
        project_root=args.project_root,
    )
    payload = report_publication_result_to_dict(result)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "docs-site\tpublish-reports\t"
            f"passed={result.passed}\tpublished={len(result.published_pages)}\t"
            f"skipped={len(result.skipped_internal_artifacts)}\tfailures={len(result.failures)}\t"
            f"index={result.index_path}"
        )
        for page in result.published_pages:
            print(f"published\t{page.artifact_title}\t{page.visibility.value}\t{page.docs_path}")
        for failure in result.failures:
            print(f"retry\t{failure.artifact_title}\t{failure.reason}\t{failure.retry_record_path}")
    return 0 if result.passed else 1


def _handle_setup_validate(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    store = _codex_limits_store_from_args(args, settings)
    result = validate_first_project_setup(
        settings,
        project_root=Path(args.project_root),
        latest_limit_record=store.latest_record(
            account_scope_id=settings.codex_limit_sentinel.account_scope_id,
            bucket_id=settings.codex_limit_sentinel.bucket_id,
        ),
    )
    if args.json:
        print(json.dumps(_first_project_setup_validation_to_dict(result), indent=2, sort_keys=True))
    else:
        print(format_first_project_setup_validation(result))
    return 0 if result.passed else 1


def _handle_setup_intake(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    limit_store = _codex_limits_store_from_args(args, settings)
    generated_at = args.generated_at or _utc_now()
    project_root = _intake_project_root(args, settings)
    durable_data_root = Path(args.durable_data_root) if args.durable_data_root else _infer_data_root(settings.paths.po_inbox)
    report_root = Path(args.report_root) if args.report_root else durable_data_root / "intake-reports"
    target_repository = args.target_repository or _default_target_repository(settings)
    report = build_release_intake_report(
        settings,
        ReleaseIntakeInput(
            project_id=args.project_id,
            project_name=args.project_name,
            release_id=args.release_id,
            generated_at=generated_at,
            project_root=project_root,
            target_repository=target_repository,
            jira_project_key=args.jira_project_key or settings.jira.project_key,
            jira_board_id=args.jira_board_id or settings.jira.board_id,
            product_docs_root=Path(args.product_docs_root),
            architecture_root=Path(args.architecture_root),
            evidence_root=Path(args.evidence_root) if args.evidence_root else settings.paths.agent_logs,
            durable_data_root=durable_data_root,
            report_root=report_root,
            require_confluence=args.require_confluence,
            require_agiletest=not args.no_require_agiletest,
        ),
        latest_limit_record=limit_store.latest_record(
            account_scope_id=settings.codex_limit_sentinel.account_scope_id,
            bucket_id=settings.codex_limit_sentinel.bucket_id,
        ),
    )
    report_root_path = _release_intake_path_by_name(report, "report_root")
    report_json_path, report_markdown_path = release_intake_report_paths(report, report_root=report_root_path)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_file(report_json_path, release_intake_report_to_dict(report))
    report_markdown_path.write_text(release_intake_report_markdown(report), encoding="utf-8")
    inbox_locations = _create_intake_po_questions(
        args,
        report,
        report_json_path=report_json_path,
    )
    payload = {
        **release_intake_summary_table(report),
        "report_json_path": str(report_json_path),
        "report_markdown_path": str(report_markdown_path),
        "po_inbox_items": [
            {
                "id": location.item_id,
                "status": location.status.value,
                "path": str(location.path),
            }
            for location in inbox_locations
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_release_intake_report(report))
        print(f"report_json\t{report_json_path}")
        print(f"report_markdown\t{report_markdown_path}")
        for location in inbox_locations:
            print(f"po_inbox\t{location.item_id}\t{location.status.value}\t{location.path}")
    return 0 if report.ready else 1


def _handle_setup_live_diagnostic(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    report = build_live_integration_readiness_report(
        settings,
        LiveIntegrationReadinessOptions(
            project_root=Path(args.project_root),
            sample_issue_key=args.sample_issue_key,
            skip_network=args.skip_network,
            timeout_seconds=args.timeout_seconds,
        ),
    )
    if args.json:
        print(json.dumps(integration_readiness_report_to_dict(report), indent=2, sort_keys=True))
    else:
        print(format_integration_readiness_report(report))
    return 0 if report.assignment_allowed else 1


def _handle_codex_limits_record(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    observed_at = args.observed_at or _utc_now()
    source = CodexLimitObservationSource(args.source)
    plan_mode = CodexLimitPlanMode(args.plan_mode)
    short_window = _build_limit_window(
        status=args.short_status,
        remaining_percent=args.short_remaining,
        reset_at=args.short_reset_at,
        source=source,
        observed_at=observed_at,
        window_id=args.short_window_id,
        label=args.short_label,
        default_window_id="primary",
        default_label=(
            "Agentic usage pool"
            if plan_mode is CodexLimitPlanMode.SINGLE_POOL
            else "Primary window"
        ),
        bucket_id=args.bucket_id or settings.codex_limit_sentinel.bucket_id,
    )
    if plan_mode is CodexLimitPlanMode.SINGLE_POOL:
        broad_quota = short_window
        windows = (short_window,)
    else:
        if not args.broad_status:
            print("error: --broad-status is required unless --plan-mode single_pool is used", file=sys.stderr)
            return 1
        broad_quota = _build_limit_window(
            status=args.broad_status,
            remaining_percent=args.broad_remaining,
            reset_at=args.broad_reset_at,
            source=source,
            observed_at=observed_at,
            window_id=args.broad_window_id,
            label=args.broad_label,
            default_window_id="secondary",
            default_label="Secondary quota",
            bucket_id=args.bucket_id or settings.codex_limit_sentinel.bucket_id,
        )
        windows = (short_window, broad_quota)
    record = build_codex_limit_availability_record(
        record_id=args.record_id,
        short_window=short_window,
        broad_quota=broad_quota,
        plan_mode=plan_mode,
        windows=windows,
        note=args.note,
        account_scope_id=(
            args.account_scope_id
            or settings.codex_limit_sentinel.account_scope_id
        ),
    )
    store = _codex_limits_store_from_args(args, settings)
    location = store.write_record(record)
    gate = decide_codex_limit_gate(record)
    print(f"recorded\t{location.record_id}\t{record.recommended_action.value}\t{gate.allowed}\t{gate.resume_after}\t{location.path}")
    return 0


def _handle_codex_limits_refresh(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    observed_at = args.observed_at or _utc_now()
    account_scope_id = (
        args.account_scope_id
        or settings.codex_limit_sentinel.account_scope_id
    )
    bucket_id = args.bucket_id or settings.codex_limit_sentinel.bucket_id
    record_id = (
        args.record_id
        or f"availability-{_safe_timestamp(observed_at)}-{uuid.uuid4().hex[:12]}"
    )
    cutoff_percent = (
        args.cutoff_percent
        if args.cutoff_percent is not None
        else settings.codex_limit_sentinel.guard_cutoff_percent
    )
    note = args.note or "Codex limit state refreshed from host-side sentinel."
    store = _codex_limits_store_from_args(args, settings)
    observation_source = (
        CodexLimitObservationSource.OFFLINE_FIXTURE
        if args.payload_json is not None
        else settings.codex_limit_sentinel.record_source
    )
    try:
        if args.payload_json is not None:
            payload = load_rate_limit_payload(args.payload_json)
        else:
            command = args.app_server_command or settings.codex_limit_sentinel.app_server_command
            payload = CodexAppServerLimitReader(
                command=command,
                timeout_seconds=args.timeout_seconds,
            ).read()
        result = refresh_codex_limit_from_payload(
            payload,
            record_id=record_id,
            observed_at=observed_at,
            cutoff_percent=cutoff_percent,
            account_scope_id=account_scope_id,
            selected_bucket_id=bucket_id,
            source=observation_source,
            note=note,
        )
        location = store.write_record(result.record)
        selected_record = store.latest_record(
            account_scope_id=account_scope_id,
            bucket_id=bucket_id,
        )
        stale_after_seconds = settings.codex_limit_sentinel.stale_after_seconds
        gate = decide_codex_limit_gate(
            selected_record,
            stale_after_seconds=(
                stale_after_seconds if stale_after_seconds > 0 else None
            ),
            future_tolerance_seconds=(
                settings.codex_limit_sentinel.future_tolerance_seconds
            ),
        )
        selected_record_id = selected_record.id if selected_record else ""
        selected_path = (
            store.record_path(selected_record_id) if selected_record_id else location.path
        )
        print(
            "refreshed\t"
            f"{selected_record_id}\t{gate.action.value}\t"
            f"{gate.allowed}\t{gate.resume_after}\t{result.raw_window_count}\t{selected_path}"
        )
        return 0 if gate.allowed else 2
    except (CodexLimitSentinelError, CodexLimitAvailabilityError, ValueError) as error:
        failure_bucket_id = resolve_codex_limit_write_bucket_id(
            store.list_records(),
            account_scope_id=account_scope_id,
            configured_bucket_id=bucket_id,
        )
        record = build_unknown_codex_limit_record(
            record_id=record_id,
            observed_at=observed_at,
            source=observation_source,
            note=redact_integration_readiness_text(
                f"Automatic Codex limit refresh failed; manual fallback required. {error}"
            ),
            account_scope_id=account_scope_id,
            bucket_id=failure_bucket_id,
        )
        location = store.write_record(record)
        gate = decide_codex_limit_gate(record)
        print(
            "refresh_failed\t"
            f"{location.record_id}\t{record.recommended_action.value}\t"
            f"{gate.allowed}\t{gate.resume_after}\t{location.path}"
        )
        return 1


def _handle_codex_limits_latest(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    store = _codex_limits_store_from_args(args, settings)
    record = store.latest_record(
        account_scope_id=(
            args.account_scope_id
            or settings.codex_limit_sentinel.account_scope_id
        ),
        bucket_id=args.bucket_id or settings.codex_limit_sentinel.bucket_id,
    )
    gate = _decide_codex_limit_gate_from_args(record, args, settings)
    if args.json:
        payload = {
            "record": codex_limit_availability_record_to_dict(record) if record else None,
            "gate": {
                "allowed": gate.allowed,
                "action": gate.action.value,
                "reason": gate.reason,
                "resume_after": gate.resume_after,
            },
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        record_id = record.id if record else ""
        print(f"latest\t{record_id}\t{gate.action.value}\t{gate.allowed}\t{gate.resume_after}\t{gate.reason}")
    return 0


def _handle_codex_limits_status(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    store = _codex_limits_store_from_args(args, settings)
    record = store.latest_record(
        account_scope_id=(
            args.account_scope_id
            or settings.codex_limit_sentinel.account_scope_id
        ),
        bucket_id=args.bucket_id or settings.codex_limit_sentinel.bucket_id,
    )
    gate = _decide_codex_limit_gate_from_args(record, args, settings)
    print(_format_codex_limit_status(record, gate))
    return 0


def _handle_agent_messages_publish(args: argparse.Namespace) -> int:
    store = _agent_message_store_from_args(args)
    message_type = AgentMessageType(args.message_type)
    target_role = AgentRole(args.target_role) if args.target_role else None
    target_channel = AgentCommunicationChannel(args.target_channel) if args.target_channel else None
    created_at = args.created_at or _utc_now()
    payload = _load_payload_json(args.payload_json)
    idempotency_key = args.idempotency_key or agent_message_idempotency_key(
        message_type=message_type,
        project_id=args.project_id,
        jira_issue_key=args.jira_issue_key,
        assignment_id=args.assignment_id,
        target_role=target_role,
        target_channel=target_channel,
        correlation_id=args.correlation_id,
        causation_id=args.causation_id,
    )
    message = build_agent_message(
        message_id=args.message_id,
        message_type=message_type,
        idempotency_key=idempotency_key,
        source_role=AgentRole(args.source_role),
        target_role=target_role,
        target_channel=target_channel,
        target_worker_id=args.target_worker_id,
        source_worker_id=args.source_worker_id,
        origin_actor=args.origin_actor,
        created_at=created_at,
        project_id=args.project_id,
        project_name=args.project_name,
        project_root=args.project_root,
        repository=args.repository,
        jira_project_key=args.jira_project_key,
        sprint_id=args.sprint_id,
        sprint_name=args.sprint_name,
        jira_issue_key=args.jira_issue_key,
        assignment_id=args.assignment_id,
        priority=AgentMessagePriority(args.priority),
        correlation_id=args.correlation_id,
        causation_id=args.causation_id,
        payload=payload,
        artifact_refs=tuple(args.artifact_ref),
        requires_acknowledgement=args.requires_acknowledgement,
        expires_at=args.expires_at,
    )
    location = store.publish_message(message)
    stored = store.read_message(location.id)
    if args.json:
        print(
            json.dumps(
                {
                    "created": location.created,
                    "duplicate_of": location.duplicate_of,
                    "path": str(location.path),
                    "message": agent_message_to_dict(stored),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        action = "published" if location.created else "duplicate"
        print(f"{action}\t{location.id}\t{stored.message_type.value}\t{stored.status.value}\t{location.path}")
    return 0


def _handle_agent_messages_publish_handoff(args: argparse.Namespace) -> int:
    store = _agent_message_store_from_args(args)
    trigger_input = RoleHandoffTriggerInput(
        message_id=args.message_id,
        current_status=args.current_status,
        event=StoryPathEvent(args.event),
        actor=StoryPathRole(args.actor),
        target_status=args.target_status,
        project_id=args.project_id,
        project_name=args.project_name,
        project_root=args.project_root,
        repository=args.repository,
        jira_project_key=args.jira_project_key,
        sprint_id=args.sprint_id,
        sprint_name=args.sprint_name,
        jira_issue_key=args.jira_issue_key,
        assignment_id=args.assignment_id,
        workspace_path=args.workspace_path,
        context_pack_path=args.context_pack_path,
        evidence_path=args.evidence_path,
        communication_channel_id=args.communication_channel_id,
        source_worker_id=args.source_worker_id,
        branch_name=args.branch_name,
        pull_request_url=args.pull_request_url,
        merge_sha=args.merge_sha,
        correlation_id=args.correlation_id,
        causation_id=args.causation_id,
        artifact_values=_parse_named_artifacts(args.artifact),
        payload=_load_payload_json(args.payload_json),
        created_at=args.created_at or _utc_now(),
    )
    decision = build_role_handoff_trigger_message(trigger_input)
    blocked_location = None
    if not decision.allowed:
        if not args.no_blocked_message:
            blocked = build_blocked_role_handoff_message(
                trigger_input,
                blockers=decision.blockers,
                message_id=f"{args.message_id}-blocked",
            )
            blocked_location = store.publish_message(blocked)
        if args.json:
            print(
                json.dumps(
                    {
                        "allowed": False,
                        "blockers": decision.blockers,
                        "route_id": decision.route.id if decision.route else "",
                        "blocked_message": str(blocked_location.path) if blocked_location else "",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("blocked\t" + "; ".join(decision.blockers))
        return 2

    assert decision.message is not None
    location = store.publish_message(decision.message)
    stored = store.read_message(location.id)
    if args.json:
        print(
            json.dumps(
                {
                    "allowed": True,
                    "created": location.created,
                    "duplicate_of": location.duplicate_of,
                    "route_id": decision.route.id if decision.route else "",
                    "path": str(location.path),
                    "message": agent_message_to_dict(stored),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        action = "published" if location.created else "duplicate"
        route_id = decision.route.id if decision.route else ""
        print(f"{action}\t{location.id}\t{route_id}\t{stored.message_type.value}\t{location.path}")
    return 0


def _handle_agent_messages_list(args: argparse.Namespace) -> int:
    messages = _agent_message_store_from_args(args).list_messages(
        status=AgentMessageStatus(args.status) if args.status else None,
        project_id=args.project_id,
        jira_issue_key=args.jira_issue_key,
        assignment_id=args.assignment_id,
        target_role=AgentRole(args.target_role) if args.target_role else None,
        target_channel=AgentCommunicationChannel(args.target_channel) if args.target_channel else None,
        message_type=AgentMessageType(args.message_type) if args.message_type else None,
    )
    if args.json:
        print(json.dumps({"items": [agent_message_to_dict(message) for message in messages]}, indent=2, sort_keys=True))
        return 0
    if not messages:
        print("No agent messages found.")
        return 0
    print("id\tmessage_type\tstatus\tproject_id\tjira_issue_key\tsource_role\ttarget_role\ttarget_channel")
    for message in messages:
        print(
            "\t".join(
                (
                    message.id,
                    message.message_type.value,
                    message.status.value,
                    message.project_id,
                    message.jira_issue_key,
                    message.source_role.value,
                    message.target_role.value if message.target_role else "",
                    message.target_channel.value if message.target_channel else "",
                )
            )
        )
    return 0


def _handle_agent_messages_ack(args: argparse.Namespace) -> int:
    message = _agent_message_store_from_args(args).acknowledge_message(
        args.message_id,
        acknowledged_at=args.acknowledged_at or _utc_now(),
    )
    if args.json:
        print(json.dumps({"message": agent_message_to_dict(message)}, indent=2, sort_keys=True))
    else:
        print(f"acknowledged\t{message.id}\t{message.status.value}\t{message.acknowledged_at}")
    return 0


def _handle_agent_messages_consume(args: argparse.Namespace) -> int:
    message = _agent_message_store_from_args(args).consume_message(
        args.message_id,
        consumed_at=args.consumed_at or _utc_now(),
    )
    if args.json:
        print(json.dumps({"message": agent_message_to_dict(message)}, indent=2, sort_keys=True))
    else:
        print(f"consumed\t{message.id}\t{message.status.value}\t{message.consumed_at}")
    return 0


def _handle_agent_messages_reject(args: argparse.Namespace) -> int:
    message = _agent_message_store_from_args(args).reject_message(
        args.message_id,
        rejected_reason=args.reason,
        rejected_at=args.rejected_at or _utc_now(),
    )
    if args.json:
        print(json.dumps({"message": agent_message_to_dict(message)}, indent=2, sort_keys=True))
    else:
        print(f"rejected\t{message.id}\t{message.status.value}\t{message.rejected_reason}")
    return 0


def _handle_orchestration_events_enqueue(args: argparse.Namespace) -> int:
    store = _orchestration_event_store_from_args(args)
    event_type = OrchestrationEventType(args.event_type)
    source_role = AgentRole(args.source_role)
    target_role = AgentRole(args.target_role) if args.target_role else None
    created_at = args.created_at or _utc_now()
    payload = _load_payload_json(args.payload_json)
    idempotency_key = args.idempotency_key or orchestration_event_idempotency_key(
        event_type=event_type,
        jira_issue_key=args.jira_issue_key,
        source_assignment_id=args.source_assignment_id,
        scope_key=args.scope_key,
    )
    event = build_orchestration_event(
        event_id=args.event_id,
        event_type=event_type,
        idempotency_key=idempotency_key,
        source_role=source_role,
        target_role=target_role,
        created_at=created_at,
        jira_issue_key=args.jira_issue_key,
        source_assignment_id=args.source_assignment_id,
        project_id=args.project_id,
        project_name=args.project_name,
        project_root=args.project_root,
        repository=args.repository,
        jira_project_key=args.jira_project_key,
        correlation_id=args.correlation_id,
        scope_key=args.scope_key,
        payload=payload,
        evidence_paths=tuple(args.evidence_path),
    )
    location = store.enqueue_event(event)
    stored = store.read_event(location.id)
    if args.json:
        print(
            json.dumps(
                {
                    "created": location.created,
                    "duplicate_of": location.duplicate_of,
                    "path": str(location.path),
                    "event": orchestration_event_to_dict(stored),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        action = "enqueued" if location.created else "duplicate"
        print(f"{action}\t{location.id}\t{stored.event_type.value}\t{stored.status.value}\t{location.path}")
    return 0


def _handle_orchestration_events_list(args: argparse.Namespace) -> int:
    status = OrchestrationEventStatus(args.status) if args.status else None
    events = _orchestration_event_store_from_args(args).list_events(status=status, project_id=args.project_id)
    if args.json:
        print(json.dumps({"items": [orchestration_event_to_dict(event) for event in events]}, indent=2, sort_keys=True))
        return 0
    if not events:
        print("No orchestration events found.")
        return 0
    print("id\tevent_type\tstatus\tjira_issue_key\tsource_role\ttarget_role\tidempotency_key\tproject_id")
    for event in events:
        print(
            "\t".join(
                (
                    event.id,
                    event.event_type.value,
                    event.status.value,
                    event.jira_issue_key,
                    event.source_role.value,
                    event.target_role.value if event.target_role else "",
                    event.idempotency_key,
                    event.project_id,
                )
            )
        )
    return 0


def _handle_orchestration_events_claim_next(args: argparse.Namespace) -> int:
    event = _orchestration_event_store_from_args(args).claim_next_event(updated_at=args.updated_at or _utc_now())
    if args.json:
        print(
            json.dumps(
                {
                    "claimed": event is not None,
                    "event": orchestration_event_to_dict(event) if event else None,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if event is None:
        print("no-event")
        return 0
    print(f"claimed\t{event.id}\t{event.event_type.value}\t{event.status.value}")
    return 0


def _handle_orchestration_events_complete(args: argparse.Namespace) -> int:
    store = _orchestration_event_store_from_args(args)
    event = store.read_event(args.event_id)
    processed_at = args.processed_at or _utc_now()
    processed = mark_orchestration_event_processed(event, processed_at=processed_at)
    location = store.save_event(processed)
    if args.json:
        print(json.dumps({"path": str(location.path), "event": orchestration_event_to_dict(processed)}, indent=2, sort_keys=True))
    else:
        print(f"processed\t{processed.id}\t{processed.status.value}\t{location.path}")
    return 0


def _handle_orchestration_events_reject(args: argparse.Namespace) -> int:
    store = _orchestration_event_store_from_args(args)
    event = store.read_event(args.event_id)
    rejected = reject_orchestration_event(
        event,
        rejected_reason=args.reason,
        updated_at=args.rejected_at or _utc_now(),
    )
    location = store.save_event(rejected)
    if args.json:
        print(json.dumps({"path": str(location.path), "event": orchestration_event_to_dict(rejected)}, indent=2, sort_keys=True))
    else:
        print(f"rejected\t{rejected.id}\t{rejected.status.value}\t{location.path}")
    return 0


def _handle_worker_run_once(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    result = run_docker_worker_once(
        settings,
        role=AgentRole(args.role),
        worker_id=args.worker_id,
        container_name=args.container_name,
        workspace_path=args.workspace_path,
        dry_run=not args.execute,
        check_integrations=args.check_integrations,
        assignment_store_root=Path(args.assignment_store_root) if args.assignment_store_root else None,
        lock_store_root=Path(args.lock_store_root) if args.lock_store_root else None,
        limit_store_root=Path(args.limit_store_root) if args.limit_store_root else None,
        logs_root=Path(args.logs_root) if args.logs_root else None,
        checkpoint_store_root=Path(args.checkpoint_store_root) if args.checkpoint_store_root else None,
        codex_execution_mode=args.codex_execution_mode,
    )
    print(json.dumps(docker_worker_run_result_to_dict(result), indent=2, sort_keys=True))
    return 0 if result.startup_passed else 1


def _handle_worker_status(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    store_root = Path(args.assignment_store_root) if args.assignment_store_root else settings.paths.agent_state
    items = build_assignment_status_items(FileAgentAssignmentStore(store_root).list_assignments(project_id=args.project_id))
    if args.json:
        print(json.dumps({"items": [assignment_status_item_to_dict(item) for item in items]}, indent=2, sort_keys=True))
        return 0
    if not items:
        print("No paused or blocked assignments.")
        return 0
    print("assignment_id\tjira_issue_key\trole\tstatus\tcategory\treason\trecommended_next_action\tproject_id")
    for item in items:
        print(
            "\t".join(
                (
                    item.assignment_id,
                    item.jira_issue_key,
                    item.role,
                    item.status,
                    item.category,
                    item.reason,
                    item.recommended_next_action,
                    item.project_id,
                )
            )
        )
    return 0


def _handle_worker_pause_for_po(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    assignment_root = Path(args.assignment_store_root) if args.assignment_store_root else settings.paths.agent_state
    assignment_store = FileAgentAssignmentStore(assignment_root)
    inbox_store = _store_from_args(args)
    assignment = assignment_store.read_assignment(args.assignment_id)
    timestamp = args.paused_at or _utc_now()
    inbox_item_id = args.inbox_item_id or f"po-blocker-{assignment.id}"
    resume_context_path = Path(args.resume_context_path) if args.resume_context_path else (
        assignment_root / "po-inbox-resume-contexts" / f"{assignment.id}.json"
    )
    pause_reason = f"PO input required: {args.question}"
    paused_assignment = pause_assignment_for_po_inbox(
        assignment,
        worker_id=args.worker_id,
        po_inbox_item_id=inbox_item_id,
        resume_context_path=str(resume_context_path),
        pause_reason=pause_reason,
        updated_at=timestamp,
    )
    resume_context = {
        "project_id": args.project_id,
        "assignment_id": assignment.id,
        "jira_issue_key": assignment.jira_issue_key,
        "role": assignment.role.value,
        "worker_id": args.worker_id,
        "question": args.question,
        "response_needed": args.response_needed,
        "resume_context": args.resume_context,
        "context_pack_path": assignment.paths.context_pack_path,
        "branch_name": assignment.branch_name,
        "paused_at": timestamp,
    }
    _write_json_file(resume_context_path, resume_context)
    item = POInboxItem(
        id=inbox_item_id,
        message_type=InboxMessageType.BLOCKING_QUESTION,
        status=InboxStatus.OPEN,
        title=args.title or f"PO blocker for {assignment.jira_issue_key} {assignment.role.value}",
        message=_format_worker_po_blocker_message(
            project_id=args.project_id,
            assignment_id=assignment.id,
            role=assignment.role.value,
            jira_issue_key=assignment.jira_issue_key,
            question=args.question,
            response_needed=args.response_needed,
            resume_context=args.resume_context,
            resume_context_path=str(resume_context_path),
        ),
        agent_role=assignment.role,
        created_at=timestamp,
        agent_id=args.agent_id or args.worker_id,
        jira_issue_key=assignment.jira_issue_key,
        context_pack_path=assignment.paths.context_pack_path,
        business_impact=args.business_impact
        or "Detached worker assignment is paused until Product Owner input is recorded.",
        recommendation=args.recommendation
        or "Answer this inbox item, then run worker resume-po-inbox after normal gates pass.",
        audit=(
            InboxAuditEvent(
                timestamp=timestamp,
                actor=args.agent_id or args.worker_id,
                action="created",
                note=f"Created by worker pause-for-po for assignment {assignment.id}.",
            ),
        ),
    )
    inbox_location = inbox_store.create(item)
    assignment_location = assignment_store.save_assignment(paused_assignment)
    payload = {
        "assignment_id": assignment.id,
        "jira_issue_key": assignment.jira_issue_key,
        "status": paused_assignment.status.value,
        "po_inbox_item_id": inbox_item_id,
        "po_inbox_path": str(inbox_location.path),
        "assignment_path": str(assignment_location.path),
        "resume_context_path": str(resume_context_path),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "paused-for-po\t"
            f"{payload['assignment_id']}\t{payload['jira_issue_key']}\t"
            f"{payload['po_inbox_item_id']}\t{payload['resume_context_path']}"
        )
    return 0


def _handle_worker_resume_po_inbox(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    assignment_root = Path(args.assignment_store_root) if args.assignment_store_root else settings.paths.agent_state
    result = resume_po_inbox_blocked_assignments(
        assignment_store=FileAgentAssignmentStore(assignment_root),
        inbox_store=_store_from_args(args),
        resumed_at=args.resumed_at or _utc_now(),
        eligible_issue_keys=args.eligible_issue_key,
    )
    if args.json:
        print(json.dumps(po_inbox_resume_scheduler_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(
            "resume-po-inbox\t"
            f"resumed={len(result.resumed_assignment_ids)}\t"
            f"skipped={len(result.skipped_assignment_ids)}"
        )
        for request in result.resume_requests:
            print(
                "resume_request\t"
                f"{request.assignment_id}\t{request.jira_issue_key}\t"
                f"{request.po_inbox_item_id}\t{request.action}"
            )
        for skip in result.skips:
            print(f"skip\t{skip.assignment_id}\t{skip.jira_issue_key}\t{skip.reason}\t{skip.next_action}")
    return 0


def _handle_worker_failed_requests(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    store_root = Path(args.codex_jobs_root) if args.codex_jobs_root else settings.paths.codex_jobs
    failed_requests = FileCodexPauseStore(store_root).list_failed_requests()
    if args.json:
        print(
            json.dumps(
                {
                    "items": [
                        {
                            **failed_request_artifact_to_dict(item),
                            "replay_guard_key": failed_request_replay_guard_key(item),
                        }
                        for item in failed_requests
                    ]
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not failed_requests:
        print("No failed Codex requests found.")
        return 0
    print(
        "id\tjira_issue_key\trole\treason\tnext_action\tretry_policy\tstage_id\t"
        "replay_guard_key\tsuggested_next_role_action\tfailed_at"
    )
    for item in failed_requests:
        print(
            "\t".join(
                (
                    item.id,
                    item.jira_issue_key,
                    item.worker_role.value,
                    item.reason.value,
                    item.next_action.value,
                    item.retry_policy,
                    item.stage_id,
                    failed_request_replay_guard_key(item),
                    item.suggested_next_role_action,
                    item.failed_at,
                )
            )
        )
    return 0


def _handle_worker_resume_paused(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    codex_jobs_root = Path(args.codex_jobs_root) if args.codex_jobs_root else settings.paths.codex_jobs
    limit_store_root = Path(args.limit_store_root) if args.limit_store_root else settings.paths.codex_limits
    stale_after_seconds = (
        args.stale_after_seconds
        if args.stale_after_seconds is not None
        else settings.codex_limit_sentinel.stale_after_seconds
    )
    stale_after_seconds_value = (
        stale_after_seconds
        if stale_after_seconds is not None and stale_after_seconds > 0
        else None
    )
    result = resume_paused_limit_jobs(
        job_store=FileCodexJobStore(codex_jobs_root),
        limit_store=FileCodexLimitAvailabilityStore(limit_store_root),
        resumed_at=args.resumed_at or _utc_now(),
        eligible_issue_keys=args.eligible_issue_key,
        stale_after_seconds=stale_after_seconds_value,
        future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
        account_scope_id=settings.codex_limit_sentinel.account_scope_id,
        bucket_id=settings.codex_limit_sentinel.bucket_id,
    )
    if args.json:
        print(json.dumps(codex_resume_scheduler_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(
            "resume-paused\t"
            f"allowed={result.gate.allowed}\t"
            f"action={result.gate.action.value}\t"
            f"resumed={len(result.resumed_job_ids)}\t"
            f"skipped={len(result.skipped_job_ids)}\t"
            f"next_check_at={result.next_check_at}"
        )
    return 0 if result.gate.allowed else 2


def _handle_worker_locks_list(args: argparse.Namespace) -> int:
    store = _assignment_lock_store_from_args(args)
    status = AssignmentLockStatus(args.status) if args.status else None
    locks = store.list_locks(status=status)
    if args.json:
        print(json.dumps({"items": [assignment_lock_to_dict(lock) for lock in locks]}, indent=2, sort_keys=True))
        return 0
    if not locks:
        print("No assignment locks found.")
        return 0
    print(
        "jira_issue_key\trole\tworker_session_id\tstatus\tupdated_at\tworkspace_path\texpires_at\t"
        "release_reason\taudit_note"
    )
    for lock in locks:
        print(
            "\t".join(
                (
                    lock.jira_issue_key,
                    lock.role.value,
                    lock.worker_session_id,
                    lock.status.value,
                    lock.updated_at,
                    lock.workspace_path,
                    lock.expires_at,
                    lock.release_reason,
                    lock.audit_note,
                )
            )
        )
    return 0


def _handle_worker_locks_mark_stale(args: argparse.Namespace) -> int:
    locks = _assignment_lock_store_from_args(args).mark_stale_locks(
        checked_at=args.checked_at,
        stale_after_seconds=args.stale_after_seconds,
    )
    if args.json:
        print(json.dumps({"items": [assignment_lock_to_dict(lock) for lock in locks]}, indent=2, sort_keys=True))
        return 0
    print(f"marked_stale\t{len(locks)}")
    for lock in locks:
        print(f"{lock.jira_issue_key}\t{lock.role.value}\t{lock.worker_session_id}\t{lock.updated_at}")
    return 0


def _handle_worker_locks_release(args: argparse.Namespace) -> int:
    if not args.confirm:
        print("error: refusing to release assignment lock without --confirm", file=sys.stderr)
        return 1
    if not args.audit_note.strip():
        print("error: refusing to release assignment lock without --audit-note", file=sys.stderr)
        return 1
    store = _assignment_lock_store_from_args(args)
    lock = store.read_lock(args.jira_issue_key, args.role, args.worker_session_id)
    if lock.status is AssignmentLockStatus.ACTIVE and not args.allow_active:
        print("error: refusing to release active assignment lock without --allow-active", file=sys.stderr)
        return 1
    released = store.release_lock(
        args.jira_issue_key,
        args.role,
        args.worker_session_id,
        released_at=args.released_at,
        reason=args.reason,
        audit_note=args.audit_note,
    )
    if args.json:
        print(json.dumps(assignment_lock_to_dict(released), indent=2, sort_keys=True))
    else:
        print(f"released\t{released.jira_issue_key}\t{released.role.value}\t{released.worker_session_id}")
    return 0


def _handle_github_configure_token_auth(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    config = github_config_from_settings(settings)
    if not config.token:
        print("error: GITHUB_TOKEN or GH_TOKEN is required for token-based GitHub auth", file=sys.stderr)
        return 1
    repo_path = Path(args.repo_path).expanduser().resolve()
    if not (repo_path / ".git").exists():
        print(f"error: not a Git repository: {repo_path}", file=sys.stderr)
        return 1
    env_file = Path(args.env_file).expanduser()
    if not env_file.is_absolute():
        env_file = (Path.cwd() / env_file).resolve()
    remote_url = github_https_remote_url(config)
    import shlex

    helper_source_root = Path(args.helper_source_root).expanduser().resolve() if args.helper_source_root else None
    helper = _github_credential_helper_command(repo_path, env_file, helper_source_root=helper_source_root)
    _run_git_config(repo_path, "remote." + args.remote + ".url", remote_url)
    _run_git_config(repo_path, "credential.https://github.com.helper", helper)
    print(f"configured\t{repo_path}\t{args.remote}\t{remote_url}\ttoken=<redacted>")
    return 0


def _handle_github_credential_fill(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    output = github_token_credential_output(
        github_config_from_settings(settings),
        sys.stdin.read(),
        operation=args.operation,
    )
    if output:
        print(output, end="")
    return 0


def _handle_github_ssh_auth_diagnostic(args: argparse.Namespace) -> int:
    settings = load_settings(args.env_file)
    config = git_ssh_auth_config_from_settings(settings)
    issues = validate_git_ssh_auth(config)
    payload: dict[str, object] = {
        "configuration": redacted_git_ssh_auth_summary(config),
        "issues": [{"field": issue.field, "message": issue.message} for issue in issues],
        "executed": bool(args.execute),
        "checks": [],
    }
    if issues:
        return _print_github_ssh_diagnostic(payload, args.json, exit_code=1)
    if config.auth_mode != "ssh":
        payload["checks"] = [
            {
                "name": "ssh_auth_enabled",
                "passed": True,
                "message": "GITHUB_AUTH_MODE is https; Docker SSH auth diagnostic is not required.",
            }
        ]
        return _print_github_ssh_diagnostic(payload, args.json, exit_code=0)

    ssh_dir = Path(args.ssh_dir) if args.ssh_dir else Path("/tmp/agentic-git-ssh-diagnostic")
    runtime = prepare_git_ssh_runtime_environment(config, ssh_dir=ssh_dir)
    payload["runtime"] = redacted_git_ssh_runtime_summary(runtime)
    planned_checks = [
        {
            "name": "repository_read",
            "command": "git ls-remote <ssh-remote> HEAD",
            "purpose": "Verify SSH authentication can read repository refs.",
        },
        {
            "name": "branch_push_permission",
            "command": "git push --dry-run <ssh-remote> HEAD:refs/heads/<probe-branch>",
            "purpose": "Verify branch creation/update permission without changing the remote.",
        },
    ]
    if not args.execute:
        payload["checks"] = [
            {
                "name": "dry_run_plan",
                "passed": True,
                "message": "No network Git probes were executed. Re-run with --execute to verify live access.",
                "planned_checks": planned_checks,
            }
        ]
        return _print_github_ssh_diagnostic(payload, args.json, exit_code=0)

    checks: list[dict[str, object]] = []
    git_env = {**os.environ, **runtime.env}
    checks.append(
        _run_git_probe(
            ["git", "ls-remote", runtime.remote_url, "HEAD"],
            env=git_env,
            config=config,
            name="repository_read",
            success_message="Repository refs are readable over SSH.",
        )
    )
    repo_path = Path(args.repo_path).expanduser().resolve()
    if (repo_path / ".git").exists():
        checks.append(
            _run_git_probe(
                [
                    "git",
                    "-C",
                    str(repo_path),
                    "push",
                    "--dry-run",
                    runtime.remote_url,
                    f"HEAD:refs/heads/{args.probe_branch}",
                ],
                env=git_env,
                config=config,
                name="branch_push_permission",
                success_message="Dry-run push confirmed branch create/update permission.",
            )
        )
    else:
        checks.append(
            {
                "name": "branch_push_permission",
                "passed": False,
                "message": "Local repo path is not a Git repository, so push dry-run could not execute.",
            }
        )
    payload["checks"] = checks
    return _print_github_ssh_diagnostic(payload, args.json, exit_code=0 if all(check["passed"] for check in checks) else 1)


def _print_github_ssh_diagnostic(payload: dict[str, object], as_json: bool, *, exit_code: int) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return exit_code
    print("GitHub SSH auth diagnostic")
    configuration = payload.get("configuration", {})
    print(json.dumps(configuration, indent=2, sort_keys=True))
    issues = payload.get("issues", [])
    if issues:
        print("Issues:")
        for issue in issues:
            print(f"- {issue['field']}: {issue['message']}")
    for check in payload.get("checks", []):
        marker = "PASS" if check.get("passed") else "FAIL"
        print(f"- [{marker}] {check.get('name')}: {check.get('message', '')}")
    return exit_code


def _run_git_probe(
    command: list[str],
    *,
    env: dict[str, str],
    config,
    name: str,
    success_message: str,
) -> dict[str, object]:
    import subprocess

    completed = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    output = redact_git_ssh_text((completed.stdout or "") + (completed.stderr or ""), config)
    return {
        "name": name,
        "passed": completed.returncode == 0,
        "message": success_message if completed.returncode == 0 else "Git SSH probe failed.",
        "return_code": completed.returncode,
        "output_excerpt": output.strip()[:500],
    }


def _handle_answer(args: argparse.Namespace) -> int:
    return _update_decision(args, InboxStatus.ANSWERED, "answered", answer=args.answer)


def _handle_approve(args: argparse.Namespace) -> int:
    return _update_decision(args, InboxStatus.APPROVED, "approved", answer=args.answer)


def _handle_reject(args: argparse.Namespace) -> int:
    return _update_decision(args, InboxStatus.REJECTED, "rejected", answer=args.answer)


def _handle_resolve(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    timestamp = _utc_now()

    def apply_resolution(item: POInboxItem) -> POInboxItem:
        return replace(
            item,
            status=InboxStatus.ARCHIVED,
            audit=item.audit
            + (
                InboxAuditEvent(
                    timestamp=timestamp,
                    actor=args.actor,
                    action="resolved",
                    note=args.note,
                ),
            ),
        )

    location = store.update(args.item_id, apply_resolution)
    print(f"resolved\t{location.item_id}\t{location.status.value}\t{location.path}")
    return 0


def _update_decision(args: argparse.Namespace, status: InboxStatus, action: str, *, answer: str) -> int:
    store = _store_from_args(args)
    timestamp = _utc_now()

    def apply_decision(item: POInboxItem) -> POInboxItem:
        return replace(
            item,
            status=status,
            answer=answer,
            answered_at=timestamp,
            audit=item.audit
            + (
                InboxAuditEvent(
                    timestamp=timestamp,
                    actor=args.actor,
                    action=action,
                ),
            ),
        )

    location = store.update(args.item_id, apply_decision)
    print(f"{action}\t{location.item_id}\t{location.status.value}\t{location.path}")
    return 0


def _store_from_args(args: argparse.Namespace) -> FilePOInboxStore:
    root = Path(args.inbox_root) if args.inbox_root else load_settings(args.env_file).paths.po_inbox
    return FilePOInboxStore(root)


def _intake_project_root(args: argparse.Namespace, settings) -> Path:
    if args.project_root:
        return Path(args.project_root)
    if settings.workers.target_project_path:
        return Path(settings.workers.target_project_path)
    return Path(".")


def _default_target_repository(settings) -> str:
    return (
        settings.repositories.target_implementation.repository
        or settings.github.repository
    )


def _release_intake_path_by_name(report, name: str) -> Path:
    for intake_path in report.paths:
        if intake_path.name == name:
            return intake_path.path
    raise ValueError(f"Release intake report is missing path {name!r}.")


def _create_intake_po_questions(
    args: argparse.Namespace,
    report,
    *,
    report_json_path: Path,
):
    store = _store_from_args(args)
    timestamp = report.generated_at
    locations = []
    for question in report.po_questions:
        item = POInboxItem(
            id=question.id,
            message_type=InboxMessageType.BLOCKING_QUESTION,
            status=InboxStatus.OPEN,
            title=question.title,
            message=question.message,
            agent_role=AgentRole.PRODUCT_PLANNING,
            created_at=timestamp,
            agent_id="setup-intake",
            project_id=report.project_id,
            project_name=report.project_name,
            project_root=str(report.project_root),
            repository=report.target_repository,
            jira_project_key=report.jira_project_key,
            context_pack_path=str(report_json_path),
            business_impact=question.business_impact,
            recommendation=question.recommendation,
            audit=(
                InboxAuditEvent(
                    timestamp=timestamp,
                    actor="setup-intake",
                    action="created",
                    note=f"Created by guided release intake for check {question.related_check}.",
                ),
            ),
        )
        try:
            locations.append(store.create(item))
        except InboxItemAlreadyExistsError:
            locations.append(store.locate(question.id))
    return tuple(locations)


def _create_backlog_draft_po_questions(
    args: argparse.Namespace,
    questions: Sequence[POInboxItem],
):
    store = _store_from_args(args)
    locations = []
    for question in questions:
        scoped_question = replace(
            question,
            project_id=args.project_id,
            project_name=args.project_name,
            project_root=args.project_root,
            repository=args.repository,
            jira_project_key=args.jira_project_key,
            audit=question.audit
            + (
                InboxAuditEvent(
                    timestamp=question.created_at,
                    actor="backlog-draft-generator",
                    action="created",
                    note="Created while generating durable backlog draft.",
                ),
            ),
        )
        try:
            locations.append(store.create(scoped_question))
        except InboxItemAlreadyExistsError:
            locations.append(store.locate(scoped_question.id))
    return tuple(locations)


def _create_traceability_po_questions(
    args: argparse.Namespace,
    questions: Sequence[POInboxItem],
):
    store = _store_from_args(args)
    locations = []
    for question in questions:
        try:
            locations.append(store.create(question))
        except InboxItemAlreadyExistsError:
            locations.append(store.locate(question.id))
    return tuple(locations)


def _load_documentation_traceability_issues(path: Path) -> tuple[DocumentationTraceabilityIssue, ...]:
    with path.open("r", encoding="utf-8-sig") as file:
        raw = json.load(file)
    if not isinstance(raw, list):
        raise ValueError("jira issues JSON must be an array")
    issues: list[DocumentationTraceabilityIssue] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"jira issues JSON item {index} must be an object")
        labels = item.get("labels", ())
        issues.append(
            DocumentationTraceabilityIssue(
                key=str(item.get("key", "")),
                summary=str(item.get("summary", "")),
                issue_type=str(item.get("issue_type") or item.get("issueType") or ""),
                status=str(item.get("status", "")),
                labels=tuple(str(label) for label in labels if str(label).strip()) if isinstance(labels, list) else (),
                description=str(item.get("description", "")),
            )
        )
    return tuple(issues)


def _context_pack_documentation_references(values: Sequence[str]) -> tuple[ContextPackDocumentationReference, ...]:
    if not values:
        return (
            ContextPackDocumentationReference(
                path="docs/backlog-draft-workflow.md",
                description="Backlog draft generation workflow.",
            ),
            ContextPackDocumentationReference(
                path="docs/context-pack-generator.md",
                description="Context pack schema and worker handoff rules.",
            ),
        )
    references: list[ContextPackDocumentationReference] = []
    for value in values:
        path, separator, description = value.partition("=")
        references.append(
            ContextPackDocumentationReference(
                path=path.strip(),
                description=description.strip() if separator else "",
            )
        )
    return tuple(references)


def _backlog_draft_from_path(path: Path):
    with path.open("r", encoding="utf-8-sig") as file:
        return backlog_draft_from_dict(json.load(file))


def _format_worker_po_blocker_message(
    *,
    project_id: str,
    assignment_id: str,
    role: str,
    jira_issue_key: str,
    question: str,
    response_needed: str,
    resume_context: str,
    resume_context_path: str,
) -> str:
    return "\n".join(
        (
            f"Project: {project_id}",
            f"Assignment: {assignment_id}",
            f"Role: {role}",
            f"Jira issue: {jira_issue_key}",
            f"Question: {question}",
            f"Response needed: {response_needed}",
            f"Resume context: {resume_context}",
            f"Resume context path: {resume_context_path}",
        )
    )


def _write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _infer_data_root(inbox_root: Path) -> Path:
    return inbox_root.parent if inbox_root.name in {"po-inbox", "po_inbox"} else inbox_root


def _codex_limits_store_from_args(args: argparse.Namespace, settings) -> FileCodexLimitAvailabilityStore:
    root = Path(args.codex_limits_root) if args.codex_limits_root else settings.paths.codex_limits
    return FileCodexLimitAvailabilityStore(root)


def _decide_codex_limit_gate_from_args(record, args: argparse.Namespace, settings):
    stale_after_seconds = (
        args.stale_after_seconds
        if args.stale_after_seconds is not None
        else settings.codex_limit_sentinel.stale_after_seconds
    )
    return decide_codex_limit_gate(
        record,
        now=args.now,
        stale_after_seconds=stale_after_seconds if stale_after_seconds > 0 else None,
        future_tolerance_seconds=settings.codex_limit_sentinel.future_tolerance_seconds,
    )


def _assignment_lock_store_from_args(args: argparse.Namespace) -> FileAssignmentLockStore:
    settings = load_settings(args.env_file)
    root = Path(args.lock_store_root) if args.lock_store_root else settings.paths.agent_state
    return FileAssignmentLockStore(root)


def _agent_message_store_from_args(args: argparse.Namespace) -> FileAgentCommunicationStore:
    settings = load_settings(args.env_file)
    root = Path(args.message_root) if args.message_root else settings.paths.agent_state
    return FileAgentCommunicationStore(root)


def _orchestration_event_store_from_args(args: argparse.Namespace) -> FileOrchestrationEventQueue:
    settings = load_settings(args.env_file)
    root = Path(args.event_store_root) if args.event_store_root else settings.paths.agent_state
    return FileOrchestrationEventQueue(root)


def _load_payload_json(raw: str) -> dict[str, object]:
    payload = json.loads(raw or "{}")
    if not isinstance(payload, dict):
        raise ValueError("--payload-json must decode to a JSON object.")
    return payload


def _parse_named_artifacts(values: Sequence[str]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--artifact values must use name=value format.")
        name, artifact_value = value.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError("--artifact name cannot be blank.")
        artifacts[name] = artifact_value.strip()
    return artifacts


def _run_git_config(repo_path: Path, key: str, value: str) -> None:
    import subprocess

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "config", "--local", key, value],
        check=False,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or f"git config failed for {key}"
        raise ValueError(message)


def _github_credential_helper_command(
    repo_path: Path,
    env_file: Path,
    *,
    helper_source_root: Path | None = None,
) -> str:
    import shlex

    source_root = helper_source_root or repo_path / "src"
    cli_module = source_root / "agentic_boilerplate" / "cli.py"
    if cli_module.exists():
        return (
            f"!PYTHONPATH={shlex.quote(str(source_root))} "
            f"{shlex.quote(sys.executable)} -m agentic_boilerplate.cli "
            f"--env-file {shlex.quote(str(env_file))} github credential-fill"
        )
    return f"!agentic --env-file {shlex.quote(str(env_file))} github credential-fill"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _enum_values(enum_type) -> list[str]:
    return [item.value for item in enum_type]


def _format_codex_limit_status(record, gate) -> str:
    lines = ["Codex limit capacity"]
    if record is None:
        lines.extend(
            [
                "Record: missing",
                f"Action: {gate.action.value}",
                f"Allowed: {_yes_no(gate.allowed)}",
                f"Reason: {gate.reason}",
                "Operator action: record current Codex limit windows with `agentic codex-limits record`.",
                "Automatic GUI scraping: not supported; use host app-server refresh or enter observed values manually.",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            f"Record: {record.id}",
            f"Plan mode: {record.plan_mode.value}",
            f"Action: {gate.action.value}",
            f"Allowed: {_yes_no(gate.allowed)}",
            f"Reason: {gate.reason}",
            f"Resume after: {gate.resume_after or 'not required'}",
        ]
    )
    for label, window in codex_limit_windows_for_display(record):
        lines.append(_format_limit_window(label, window))
    if record.note:
        lines.append(f"Note: {record.note}")
    lines.append(
        "Automatic GUI scraping: not supported; use host app-server refresh "
        "or enter observed values manually."
    )
    return "\n".join(lines)


def _build_limit_window(
    *,
    status: str,
    remaining_percent: int | None,
    reset_at: str,
    source: CodexLimitObservationSource,
    observed_at: str,
    window_id: str,
    label: str,
    default_window_id: str,
    default_label: str,
    bucket_id: str,
) -> CodexLimitWindowAvailability:
    return CodexLimitWindowAvailability(
        status=CodexLimitWindowStatus(status),
        remaining_percent=remaining_percent,
        reset_at=reset_at,
        observation_source=source,
        observed_at=observed_at,
        window_id=window_id or default_window_id,
        label=label or default_label,
        bucket_id=bucket_id,
    )


def _safe_timestamp(value: str) -> str:
    return (
        value.replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("+0000", "Z")
        .replace("+00:00", "Z")
    )


def _format_limit_window(label, window) -> str:
    remaining = "unknown" if window.remaining_percent is None else f"{window.remaining_percent}%"
    reset_at = window.reset_at or "unknown"
    return (
        f"{label}: status={window.status.value}, remaining={remaining}, "
        f"reset_at={reset_at}, source={window.observation_source.value}, observed_at={window.observed_at}"
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _first_project_setup_validation_to_dict(result: FirstProjectSetupValidation) -> dict[str, object]:
    return {
        "passed": result.passed,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "message": check.message,
            }
            for check in result.checks
        ],
    }


def _po_inbox_path_guard_result_to_dict(result) -> dict[str, object]:
    return {
        "passed": result.passed,
        "platform_inbox_root": str(result.platform_inbox_root),
        "target_project_root": str(result.target_project_root),
        "platform_inbox_inside_target": result.platform_inbox_inside_target,
        "misplaced_paths": [str(path) for path in result.misplaced_paths],
        "messages": list(result.messages),
    }


if __name__ == "__main__":
    raise SystemExit(main())
