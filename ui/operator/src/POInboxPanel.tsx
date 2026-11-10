import { AlertTriangle, CheckCircle2, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  canApplyInboxAction,
  exportInboxItems,
  formatInboxOption,
  inboxItemKey,
  inboxProjectIdentity,
  inboxProjectFilterKey,
  listOpenInboxItems,
  readInboxItem,
  submitInboxAction,
  type POInboxAction,
  type POInboxFilters,
  type POInboxItem,
  type POInboxListResult,
  type POInboxProject
} from "./poInboxClient";

type DetailState =
  | { state: "idle"; item?: undefined; message?: undefined }
  | { state: "loading"; item?: undefined; message?: undefined }
  | { state: "loaded"; item: POInboxItem; message?: undefined }
  | { state: "error"; item?: undefined; message: string };

type ExportState = { state: "idle" } | { state: "saved"; message: string } | { state: "error"; message: string };

export function POInboxPanel() {
  const [listState, setListState] = useState<POInboxListResult>({
    state: "empty",
    items: [],
    projects: [],
    projectErrors: []
  });
  const [detailState, setDetailState] = useState<DetailState>({ state: "idle" });
  const [selectedId, setSelectedId] = useState<string>("");
  const [projectFilter, setProjectFilter] = useState("all");
  const [messageTypeFilter, setMessageTypeFilter] = useState("all");
  const [agentRoleFilter, setAgentRoleFilter] = useState("all");
  const [jiraIssueFilter, setJiraIssueFilter] = useState("");
  const [exportState, setExportState] = useState<ExportState>({ state: "idle" });

  function currentFilters(projectId = projectFilter): POInboxFilters {
    return {
      status: "open",
      projectId,
      messageType: messageTypeFilter,
      agentRole: agentRoleFilter,
      jiraIssueKey: jiraIssueFilter.trim()
    };
  }

  async function loadInbox() {
    const filters = currentFilters();
    const result = await listOpenInboxItems(filters);
    setListState(result);
    const firstItem = result.items[0];
    if (firstItem) {
      await selectItem(inboxItemKey(firstItem));
    } else {
      setSelectedId("");
      setDetailState({ state: "idle" });
    }
  }

  async function exportInbox(scope: "project" | "all_projects") {
    const projectId =
      scope === "all_projects"
        ? "all"
        : projectFilter !== "all"
          ? projectFilter
          : projectOptions.length === 1
            ? inboxProjectFilterKey(projectOptions[0])
            : "";
    if (!projectId) {
      setExportState({ state: "error", message: "Select one project before exporting a project JSON." });
      return;
    }

    try {
      const envelope = await exportInboxItems(currentFilters(projectId));
      const filename = `po-inbox-${scope === "all_projects" ? "all-projects" : projectId}-${safeTimestamp()}.json`;
      downloadInboxExport(filename, envelope);
      setExportState({ state: "saved", message: `Export prepared: ${filename}` });
    } catch (error) {
      setExportState({
        state: "error",
        message: error instanceof Error ? error.message : "Inbox export could not be saved safely."
      });
    }
  }

  async function selectItem(itemId: string) {
    setSelectedId(itemId);
    setDetailState({ state: "loading" });
    try {
      setDetailState({ state: "loaded", item: await readInboxItem(itemId) });
    } catch (error) {
      setDetailState({
        state: "error",
        message: error instanceof Error ? error.message : "Inbox item could not be loaded safely."
      });
    }
  }

  async function submitAction(item: POInboxItem, action: POInboxAction, answer: string) {
    setDetailState({ state: "loading" });
    try {
      await submitInboxAction(item, action, answer);
      await loadInbox();
    } catch (error) {
      setDetailState({
        state: "error",
        message: error instanceof Error ? error.message : "Inbox action could not be saved safely."
      });
    }
  }

  useEffect(() => {
    void loadInbox();
  }, [projectFilter, messageTypeFilter, agentRoleFilter, jiraIssueFilter]);

  const loadedItems = useMemo(() => listState.items, [listState.items]);
  const projectOptions = useMemo(() => buildProjectOptions(listState), [listState]);
  const messageTypeOptions = useMemo(() => uniqueSorted(loadedItems.map((item) => item.message_type)), [loadedItems]);
  const agentRoleOptions = useMemo(() => uniqueSorted(loadedItems.map((item) => item.agent_role ?? "")), [loadedItems]);

  return (
    <section id="po-inbox" className="inbox-panel" aria-label="PO inbox">
      <div className="section-heading">
        <div>
          <p className="eyebrow">PO Inbox</p>
          <h3>Open decisions and questions</h3>
        </div>
        <button className="icon-button" type="button" onClick={() => void loadInbox()} title="Refresh inbox">
          <RefreshCcw size={17} aria-hidden="true" />
        </button>
      </div>

      <div className="inbox-toolbar" aria-label="PO inbox filters">
        <label>
          <span>Project</span>
          <select value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
            <option value="all">All Projects</option>
            {projectOptions.map((project) => (
              <option value={inboxProjectFilterKey(project)} key={inboxProjectFilterKey(project)}>
                {projectLabel(project)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Type</span>
          <select value={messageTypeFilter} onChange={(event) => setMessageTypeFilter(event.target.value)}>
            <option value="all">All Types</option>
            {messageTypeOptions.map((messageType) => (
              <option value={messageType} key={messageType}>
                {messageType}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Role</span>
          <select value={agentRoleFilter} onChange={(event) => setAgentRoleFilter(event.target.value)}>
            <option value="all">All Roles</option>
            {agentRoleOptions.map((agentRole) => (
              <option value={agentRole} key={agentRole}>
                {agentRole}
              </option>
            ))}
          </select>
        </label>
        <label className="jira-filter">
          <span>Jira</span>
          <input
            value={jiraIssueFilter}
            onChange={(event) => setJiraIssueFilter(event.target.value)}
            placeholder="AP-29"
          />
        </label>
        <div className="export-actions" aria-label="PO inbox export actions">
          <button type="button" onClick={() => void exportInbox("project")}>
            Export Project
          </button>
          <button type="button" onClick={() => void exportInbox("all_projects")}>
            Export All
          </button>
        </div>
      </div>

      {exportState.state !== "idle" && (
        <div className={exportState.state === "error" ? "safe-error" : "export-status"} role="status">
          <span>{exportState.message}</span>
        </div>
      )}

      {listState.state === "error" && (
        <div className="safe-error" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{listState.message}</span>
        </div>
      )}

      {listState.projectErrors.length > 0 && (
        <div className="project-error-list" aria-label="Project inbox read errors">
          {listState.projectErrors.map((error) => (
            <div className="safe-error" role="alert" key={`${error.project_id || error.jira_project_key}-${error.message}`}>
              <AlertTriangle size={18} aria-hidden="true" />
              <span>
                {projectLabel(error)}: {error.message}
              </span>
            </div>
          ))}
        </div>
      )}

      {listState.state === "empty" && (
        <div className="empty-state">
          <CheckCircle2 size={24} aria-hidden="true" />
          <strong>No open inbox items</strong>
          <p>Blocking questions, approvals, assumptions, and FYI items will appear here.</p>
        </div>
      )}

      {loadedItems.length > 0 && (
        <div className="inbox-layout">
          <div className="inbox-list" aria-label="Open inbox item list">
            {loadedItems.map((item) => (
              <button
                className={inboxItemKey(item) === selectedId ? "inbox-row selected" : "inbox-row"}
                key={inboxItemKey(item)}
                onClick={() => void selectItem(inboxItemKey(item))}
                type="button"
              >
                <span className="project-badge">{inboxProjectIdentity(item)}</span>
                <span className="row-title">{item.title}</span>
                <span className="row-meta">
                  {item.message_type} · {item.status} · {item.agent_role ?? "unknown role"}
                </span>
                <span className="row-meta">
                  {item.agent_id ? `${item.agent_id} · ` : ""}
                  {item.jira_issue_key || item.source_item_id || item.id}
                  {item.created_at ? ` · ${item.created_at}` : ""}
                </span>
              </button>
            ))}
          </div>

          <InboxDetail detailState={detailState} onSubmitAction={submitAction} />
        </div>
      )}
    </section>
  );
}

function InboxDetail({
  detailState,
  onSubmitAction
}: {
  detailState: DetailState;
  onSubmitAction: (item: POInboxItem, action: POInboxAction, answer: string) => Promise<void>;
}) {
  if (detailState.state === "loading") {
    return <div className="inbox-detail muted">Loading inbox item...</div>;
  }

  if (detailState.state === "error") {
    return (
      <div className="inbox-detail safe-error" role="alert">
        <AlertTriangle size={18} aria-hidden="true" />
        <span>{detailState.message}</span>
      </div>
    );
  }

  if (detailState.state !== "loaded") {
    return <div className="inbox-detail muted">Select an item to read the full decision context.</div>;
  }

  const { item } = detailState;
  return (
    <article className="inbox-detail" aria-label="Inbox item detail">
      <header>
        <p className="eyebrow">{item.message_type}</p>
        <h4>{item.title}</h4>
        <p className="detail-meta">
          {item.status} · {item.agent_role ?? "unknown role"} · {inboxProjectIdentity(item)}
          {item.jira_issue_key ? ` · ${item.jira_issue_key}` : ""}
        </p>
      </header>

      <section>
        <h5>Message</h5>
        <p>{item.message}</p>
      </section>

      <section>
        <h5>Business Impact</h5>
        <p>{item.business_impact || "No business impact was provided."}</p>
      </section>

      <section>
        <h5>Recommendation</h5>
        <p>{item.recommendation || "No recommendation was provided."}</p>
      </section>

      <section>
        <h5>Options</h5>
        {item.options && item.options.length > 0 ? (
          <ul>
            {item.options.map((option, index) => (
              <li key={`${item.id}-option-${index}`}>{formatInboxOption(option)}</li>
            ))}
          </ul>
        ) : (
          <p>No explicit options were provided.</p>
        )}
      </section>

      <section>
        <h5>Audit</h5>
        {item.audit && item.audit.length > 0 ? (
          <ol className="audit-list">
            {item.audit.map((event, index) => (
              <li key={`${item.id}-audit-${index}`}>
                <span>{event.timestamp ?? "unknown time"}</span>
                <span>{event.actor ?? "unknown actor"}</span>
                <span>{event.action ?? "unknown action"}</span>
                {event.note ? <span>{event.note}</span> : null}
              </li>
            ))}
          </ol>
        ) : (
          <p>No audit events were provided.</p>
        )}
      </section>

      <InboxActionForm item={item} onSubmitAction={onSubmitAction} />
    </article>
  );
}

function buildProjectOptions(listState: POInboxListResult): POInboxProject[] {
  const projects = new Map<string, POInboxProject>();
  for (const project of listState.projects) {
    projects.set(inboxProjectFilterKey(project), project);
  }
  for (const item of listState.items) {
    const project: POInboxProject = {
      project_id: item.project_id || item.source_project_id,
      project_name: item.project_name,
      jira_project_key: item.jira_project_key,
      repository: item.repository
    };
    projects.set(inboxProjectFilterKey(project), project);
  }
  return [...projects.values()].filter((project) => inboxProjectFilterKey(project) !== "default");
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((left, right) => left.localeCompare(right));
}

function projectLabel(project: POInboxProject): string {
  if (project.project_name && project.jira_project_key) {
    return `${project.project_name} (${project.jira_project_key})`;
  }
  return project.project_name || project.jira_project_key || project.project_id || "Default";
}

function downloadInboxExport(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function safeTimestamp(): string {
  return new Date().toISOString().replaceAll(":", "").replaceAll(".", "").replace("Z", "Z");
}

function InboxActionForm({
  item,
  onSubmitAction
}: {
  item: POInboxItem;
  onSubmitAction: (item: POInboxItem, action: POInboxAction, answer: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");
  const actions: { action: POInboxAction; label: string }[] = [
    { action: "answer", label: "Answer" },
    { action: "approve", label: "Approve" },
    { action: "reject", label: "Reject" },
    { action: "resolve", label: "Archive" }
  ];
  const availableActions = actions.map((entry) => ({
    ...entry,
    decision: canApplyInboxAction(item, entry.action)
  }));
  const hasAnyAction = availableActions.some((entry) => entry.decision.allowed);

  return (
    <section className="action-panel" aria-label="Inbox item actions">
      <h5>Actions</h5>
      {!hasAnyAction && (
        <p className="muted">
          This item has no valid UI action in its current status or message type.
        </p>
      )}
      {hasAnyAction && (
        <>
          <label htmlFor={`answer-${item.id}`}>Decision text</label>
          <textarea
            id={`answer-${item.id}`}
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Write the answer, approval note, rejection reason, or archive note."
          />
          <div className="action-buttons">
            {availableActions.map((entry) => (
              <button
                disabled={!entry.decision.allowed || answer.trim().length === 0}
                key={entry.action}
                onClick={() => void onSubmitAction(item, entry.action, answer.trim())}
                title={entry.decision.reason ?? entry.label}
                type="button"
              >
                {entry.label}
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
