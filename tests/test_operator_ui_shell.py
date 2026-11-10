import json
from pathlib import Path


def test_operator_ui_uses_modern_local_frontend_stack(project_root: Path) -> None:
    package = json.loads((project_root / "ui" / "operator" / "package.json").read_text(encoding="utf-8"))
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    assert package["scripts"]["dev"] == "vite --host 127.0.0.1"
    assert package["scripts"]["build"] == "tsc -b && vite build"
    assert package["scripts"]["smoke"] == "npm run build"
    assert "react" in package["dependencies"]
    assert "typescript" in package["devDependencies"]
    assert "vite" in package["devDependencies"]
    assert "@vitejs/plugin-react" in package["devDependencies"]

    assert "Vite, React, and TypeScript" in docs
    assert "npm --prefix ui/operator run dev" in docs
    assert "npm --prefix ui/operator run smoke" in docs


def test_operator_ui_shell_exposes_required_navigation(project_root: Path) -> None:
    app = (project_root / "ui" / "operator" / "src" / "App.tsx").read_text(encoding="utf-8")
    navigation = (project_root / "ui" / "operator" / "src" / "navigation.ts").read_text(
        encoding="utf-8"
    )
    config = (project_root / "ui" / "operator" / "src" / "operatorConfig.ts").read_text(
        encoding="utf-8"
    )

    for label in ("PO Inbox", "Agent Status", "Limits", "Logs", "Projects", "Agent Messages", "Settings"):
        assert label in navigation

    assert "Active Project" in app
    assert "hamburger-button" in app
    assert "operator-navigation-drawer" in app
    assert "ActiveSection" in app
    assert "platform durable data only" in config
    assert "VITE_AGENTIC_PROJECT_NAME" in config
    assert "VITE_AGENTIC_JIRA_PROJECT_KEY" in config
    assert "VITE_AGENTIC_API_BASE_URL" in config


def test_operator_ui_reads_open_po_inbox_items(project_root: Path) -> None:
    inbox_client = (project_root / "ui" / "operator" / "src" / "poInboxClient.ts").read_text(
        encoding="utf-8"
    )
    panel = (project_root / "ui" / "operator" / "src" / "POInboxPanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "new URLSearchParams" in inbox_client
    assert 'query.set("status", status)' in inbox_client
    assert 'query.set("project_id", filters.projectId)' in inbox_client
    assert "/po-inbox/export?" in inbox_client
    assert "POInboxExportEnvelope" in inbox_client
    assert "/po-inbox/${encodeURIComponent(itemId)}" in inbox_client
    assert "message_type: string" in inbox_client
    assert "project_identity?: string" in inbox_client
    assert "composite_id?: string" in inbox_client
    assert "source_project_id?: string" in inbox_client
    assert "project_errors?: POInboxProjectError[]" in inbox_client
    assert "inboxItemKey(item)" in inbox_client

    for field in (
        "message_type",
        "title",
        "agent_role",
        "agent_id",
        "status",
        "created_at",
        "business_impact",
        "recommendation",
        "options",
        "audit",
        "projectFilter",
        "messageTypeFilter",
        "agentRoleFilter",
        "jiraIssueFilter",
        "projectErrors",
        "Export Project",
        "Export All",
        "downloadInboxExport",
    ):
        assert field in panel


def test_operator_ui_has_empty_and_safe_error_states(project_root: Path) -> None:
    panel = (project_root / "ui" / "operator" / "src" / "POInboxPanel.tsx").read_text(
        encoding="utf-8"
    )
    inbox_client = (project_root / "ui" / "operator" / "src" / "poInboxClient.ts").read_text(
        encoding="utf-8"
    )
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    assert "No open inbox items" in panel
    assert "Inbox could not be loaded safely" in inbox_client
    assert "safe-error" in panel
    assert "Unknown future inbox item types must be displayed as raw labels" in docs
    assert "Invalid inbox files or API errors must be shown as safe" in docs


def test_operator_ui_supports_durable_po_inbox_actions(project_root: Path) -> None:
    inbox_client = (project_root / "ui" / "operator" / "src" / "poInboxClient.ts").read_text(
        encoding="utf-8"
    )
    panel = (project_root / "ui" / "operator" / "src" / "POInboxPanel.tsx").read_text(
        encoding="utf-8"
    )
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    for endpoint in (
        "/answer",
        "/approve",
        "/reject",
        "/resolve",
    ):
        assert endpoint in docs

    assert "submitInboxAction" in inbox_client
    assert "canApplyInboxAction" in inbox_client
    assert "blocking_question" in inbox_client
    assert "approval_request" in inbox_client
    assert "assumption" in inbox_client
    assert "fyi" in inbox_client
    assert "Only open inbox items can be changed." in inbox_client
    assert "Inbox action could not be saved safely" in inbox_client

    for label in ("Answer", "Approve", "Reject", "Archive"):
        assert label in panel

    assert "Decision text" in panel
    assert "Successful actions refresh the list from platform durable data" in docs


def test_operator_ui_supports_project_scoped_po_inbox_export(project_root: Path) -> None:
    inbox_client = (project_root / "ui" / "operator" / "src" / "poInboxClient.ts").read_text(
        encoding="utf-8"
    )
    panel = (project_root / "ui" / "operator" / "src" / "POInboxPanel.tsx").read_text(
        encoding="utf-8"
    )
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")
    api_docs = (project_root / "docs" / "po-inbox-api.md").read_text(encoding="utf-8")

    assert "exportInboxItems" in inbox_client
    assert "/po-inbox/export?" in inbox_client
    assert "POInboxExportEnvelope" in inbox_client
    assert "Export Project" in panel
    assert "Export All" in panel
    assert "downloadInboxExport" in panel
    assert "PO Inbox JSON Export" in docs
    assert "GET /po-inbox/export" in api_docs
    assert "po-inbox-export/v1" in api_docs


def test_operator_ui_docs_define_docker_first_operator_stack(project_root: Path) -> None:
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")
    po_api_docs = (project_root / "docs" / "po-inbox-api.md").read_text(encoding="utf-8")
    env_example = (project_root / ".env.example").read_text(encoding="utf-8")
    normalized_docs = " ".join(docs.split())

    for text in (docs, po_api_docs):
        assert "docker compose --profile operator up --build -d" in text
        assert "http://localhost:5173" in text
        assert "http://localhost:8000" in text
        assert "docker compose down" in text

    assert "Product Owner operation should use the Docker operator stack" in normalized_docs
    assert "/workspace/data/po-inbox" in docs
    assert "AGENTIC_OPERATOR_UI_PORT=5173" in env_example
    assert "VITE_AGENTIC_API_BASE_URL=http://localhost:8000" in env_example


def test_operator_ui_exposes_status_views_without_secret_fields(project_root: Path) -> None:
    status_client = (project_root / "ui" / "operator" / "src" / "operatorStatusClient.ts").read_text(
        encoding="utf-8"
    )
    status_panel = (project_root / "ui" / "operator" / "src" / "OperatorStatusPanel.tsx").read_text(
        encoding="utf-8"
    )
    app = (project_root / "ui" / "operator" / "src" / "App.tsx").read_text(encoding="utf-8")
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    assert "/operator-status" in status_client
    assert "OperatorStatusPanel" in app
    for label in ("Known Workers", "Assignments", "Codex Limits", "Recent Logs"):
        assert label in status_panel
    for field in ("workers", "assignments", "codex_limit", "codex_limit_gate", "recent_logs"):
        assert field in status_client
    assert "GET /operator-status" in docs
    assert "must not display secret-bearing configuration" in docs
    assert "token" not in status_panel.lower()


def test_operator_ui_exposes_worker_lifecycle_dashboard(project_root: Path) -> None:
    status_client = (project_root / "ui" / "operator" / "src" / "operatorStatusClient.ts").read_text(
        encoding="utf-8"
    )
    status_panel = (project_root / "ui" / "operator" / "src" / "OperatorStatusPanel.tsx").read_text(
        encoding="utf-8"
    )
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    for field in (
        "story_lifecycle",
        "stack_metadata",
        "stack_lanes",
        "StackedPrLaneSummary",
        "StackedPrLaneStorySummary",
        "artifact_refs",
        "next_expected_step",
        "blocked_reason",
        "needs_process_mapping",
    ):
        assert field in status_client

    for label in (
        "Story Lifecycle",
        "Stacked PR Lanes",
        "StackedPrLanesSection",
        "stale_retest_required",
        "evidence_state",
        "PR not recorded",
        "Blocked/Waiting",
        "Limit Gate",
        "Needs process mapping",
        "No safe artifact references recorded",
        "Sprint not recorded",
        "projectIdentity",
        "groupAssignmentsByProject",
    ):
        assert label in status_panel

    assert "story lifecycle" in docs.lower()
    assert "stacked PR operator visibility" in docs
    assert "stack_lanes" in docs
    assert "AGENT-671" in docs


def test_stacked_pr_operator_visibility_is_discoverable_by_roles(project_root: Path) -> None:
    agents = (project_root / "AGENTS.md").read_text(encoding="utf-8")
    index = (project_root / "docs" / "index.md").read_text(encoding="utf-8")
    resolver = (project_root / "docs" / "stacked-pr-sprint-path-resolver.md").read_text(encoding="utf-8")
    visibility = (project_root / "docs" / "stacked-pr-operator-visibility.md").read_text(
        encoding="utf-8"
    )

    for path in (
        "docs/stacked-pr-sprint-path-resolver.md",
        "docs/stacked-pr-operator-visibility.md",
    ):
        assert path in agents

    for role in ("orchestrator", "developer", "review", "tester", "release_manager"):
        role_doc = (project_root / "ai_agents" / "roles" / f"{role}.md").read_text(encoding="utf-8")
        assert "docs/stacked-pr-sprint-path-resolver.md" in role_doc
        assert "docs/stacked-pr-operator-visibility.md" in role_doc

    assert "Stacked PR Operator Visibility" in index
    assert "docs/stacked-pr-operator-visibility.md" in resolver
    assert "AgentAssignment.stack_metadata" in visibility
    assert "evidence_state" in visibility
    assert "GitHub stacked PR support is optional" in visibility


def test_operator_ui_exposes_operator_rescue_controls(project_root: Path) -> None:
    client = (project_root / "ui" / "operator" / "src" / "operatorRescueClient.ts").read_text(
        encoding="utf-8"
    )
    status_panel = (project_root / "ui" / "operator" / "src" / "OperatorStatusPanel.tsx").read_text(
        encoding="utf-8"
    )
    styles = (project_root / "ui" / "operator" / "src" / "styles.css").read_text(encoding="utf-8")
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    for endpoint in (
        "/operator-rescue",
        "/operator-rescue/${encodeURIComponent(assignmentId)}/${action}",
    ):
        assert endpoint in client

    for symbol in (
        "readOperatorRescue",
        "applyOperatorRescueAction",
        "OperatorRescueDecision",
        "OperatorRescueActionName",
    ):
        assert symbol in client

    for label in (
        "Operator Rescue",
        "Safe actions write audit and agent communication records.",
        "rescueActionIcon",
    ):
        assert label in status_panel
    assert "clear-stale-lock" in client
    assert "refresh-diagnostics" in client

    assert ".rescue-controls" in styles
    assert ".rescue-action-grid" in styles
    assert "GET /operator-rescue" in docs
    assert "POST /operator-rescue/{assignment_id}/{action}" in docs
    assert "AGENT-679" in docs


def test_operator_ui_exposes_agent_messages_timeline_and_graph(project_root: Path) -> None:
    app = (project_root / "ui" / "operator" / "src" / "App.tsx").read_text(encoding="utf-8")
    navigation = (project_root / "ui" / "operator" / "src" / "navigation.ts").read_text(encoding="utf-8")
    client = (project_root / "ui" / "operator" / "src" / "agentMessagesClient.ts").read_text(
        encoding="utf-8"
    )
    panel = (project_root / "ui" / "operator" / "src" / "AgentMessagesPanel.tsx").read_text(
        encoding="utf-8"
    )
    styles = (project_root / "ui" / "operator" / "src" / "styles.css").read_text(encoding="utf-8")
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    assert "AgentMessagesPanel" in app
    assert 'routeId === "agent-messages"' in app
    assert "Structured handoffs, resume requests, and agent communication flow." in navigation
    assert "/agent-messages?" in client
    for field in (
        "project_id",
        "jira_issue_key",
        "assignment_id",
        "message_type",
        "display_lane",
        "resume_gate",
        "linked_refs",
        "graph",
    ):
        assert field in client
    for label in (
        "Timeline",
        "Graph",
        "PO-visible",
        "Resume Requests",
        "No durable agent messages match the current filters.",
        "Requires PO inbox decision before work resumes.",
    ):
        assert label in panel
    assert ".message-layout" in styles
    assert ".message-card.po-required" in styles
    assert ".graph-node-list" in styles
    assert "GET /agent-messages" in docs
    assert "communication timeline" in docs.lower()


def test_operator_ui_supports_po_to_agent_composer_and_message_actions(project_root: Path) -> None:
    client = (project_root / "ui" / "operator" / "src" / "agentMessagesClient.ts").read_text(
        encoding="utf-8"
    )
    panel = (project_root / "ui" / "operator" / "src" / "AgentMessagesPanel.tsx").read_text(
        encoding="utf-8"
    )
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    for client_symbol in (
        "createAgentMessage",
        "acknowledgeAgentMessage",
        "consumeAgentMessage",
        "respondToAgentMessage",
        "AgentMessageCreateInput",
    ):
        assert client_symbol in client

    for endpoint in (
        "/agent-messages",
        "/acknowledge",
        "/consume",
        "/respond",
    ):
        assert endpoint in client

    for label in (
        "PO Outbox",
        "Send message to agent",
        "Response requested",
        "Reply To",
        "Send response",
        "Acknowledge",
        "Consume",
        "Product Owner message sent to durable agent channel.",
    ):
        assert label in panel

    assert "POST /agent-messages" in docs
    assert "does not mutate PO inbox item status" in docs


def test_operator_ui_routes_one_active_section_at_a_time(project_root: Path) -> None:
    app = (project_root / "ui" / "operator" / "src" / "App.tsx").read_text(encoding="utf-8")
    status_panel = (project_root / "ui" / "operator" / "src" / "OperatorStatusPanel.tsx").read_text(
        encoding="utf-8"
    )
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    assert 'useState<OperatorRouteId>("po-inbox")' in app
    assert "setDrawerOpen(false)" in app
    assert 'routeId === "po-inbox"' in app
    assert '<OperatorStatusPanel view="agent-status" />' in app
    assert "<CodexLimitsPanel />" in app
    assert '<OperatorStatusPanel view="logs" />' in app
    assert "view = \"all\"" in status_panel
    assert 'view === "all" || view === "agent-status"' in status_panel
    assert "renders one active section at a time" in docs
    assert "Option B - Compact Header With Hamburger Drawer" in docs


def test_operator_ui_supports_atomic_codex_limits_form(project_root: Path) -> None:
    app = (project_root / "ui" / "operator" / "src" / "App.tsx").read_text(encoding="utf-8")
    client = (project_root / "ui" / "operator" / "src" / "codexLimitsClient.ts").read_text(
        encoding="utf-8"
    )
    panel = (project_root / "ui" / "operator" / "src" / "CodexLimitsPanel.tsx").read_text(
        encoding="utf-8"
    )
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")

    assert "CodexLimitsPanel" in app
    assert "/codex-limits" in client
    assert "/codex-limits/records" in client
    assert "saveCodexLimitRecord" in client
    assert "CodexLimitRecordUpdate" in client
    assert "type=\"datetime-local\"" in panel
    assert "Save limit record" in panel
    assert "Preview ready" in panel
    assert "Single-pool Pro plan" in panel
    assert "Short and broad windows" in panel
    assert "Remaining percent" in panel
    assert "Codex limit record could not be saved safely" in panel
    assert "POST /codex-limits/records" in docs
    assert "GET /codex-limits" in docs
    assert "atomic" in docs.lower()


def test_operator_ui_docs_warn_against_secret_exposure(project_root: Path) -> None:
    docs = (project_root / "docs" / "operator-ui.md").read_text(encoding="utf-8")
    config = (project_root / "ui" / "operator" / "src" / "operatorConfig.ts").read_text(
        encoding="utf-8"
    )

    assert "Do not expose GitHub, Jira, Confluence, AgileTest, OpenAI, Codex, or database" in docs
    assert "must not read target project runtime folders directly" in docs
    assert "No-secret display rules" in docs
    assert "Never render raw `.env` data" in docs
    assert "Never render raw log contents" in docs
    assert "TARGET_PROJECT_PATH" not in config
    assert "TOKEN" not in config
    assert "PASSWORD" not in config
