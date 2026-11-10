import { AlertTriangle, GitBranch, MessageCircleReply, RefreshCcw, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  acknowledgeAgentMessage,
  consumeAgentMessage,
  createAgentMessage,
  listAgentMessages,
  respondToAgentMessage,
  type AgentMessage,
  type AgentMessageCreateInput,
  type AgentMessageFilters,
  type AgentMessagesResult
} from "./agentMessagesClient";
import { operatorProjectConfig } from "./operatorConfig";

const poMessageTypes = ["po_question_to_agent", "po_clarification", "po_resume_instruction", "scope_change_candidate"];
const targetRoles = [
  "scheduler",
  "platform",
  "product_planning",
  "architecture",
  "developer",
  "frontend",
  "review",
  "tester",
  "release_manager",
  "ui_ux",
  "security",
  "docs_confluence",
  "devops_platform",
  "data_persistence"
];

type ActionState = { state: "idle" } | { state: "saved"; message: string } | { state: "error"; message: string };

const initialComposer = {
  projectId: operatorProjectConfig.jiraProjectKey,
  messageType: "po_question_to_agent",
  targetRole: "scheduler",
  jiraIssueKey: "",
  assignmentId: "",
  replyToMessageId: "",
  subject: "",
  body: "",
  references: "",
  responseRequested: true
};

export function AgentMessagesPanel() {
  const [state, setState] = useState<AgentMessagesResult>({
    state: "empty",
    items: [],
    graph: { nodes: [], edges: [] },
    filters: {}
  });
  const [projectFilter, setProjectFilter] = useState("all");
  const [roleFilter, setRoleFilter] = useState("all");
  const [messageTypeFilter, setMessageTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [jiraIssueFilter, setJiraIssueFilter] = useState("");
  const [composer, setComposer] = useState(initialComposer);
  const [actionState, setActionState] = useState<ActionState>({ state: "idle" });

  function currentFilters(): AgentMessageFilters {
    return {
      projectId: projectFilter,
      role: roleFilter,
      messageType: messageTypeFilter,
      status: statusFilter,
      jiraIssueKey: jiraIssueFilter.trim()
    };
  }

  async function loadMessages() {
    setState({ state: "empty", items: [], graph: { nodes: [], edges: [] }, filters: {} });
    setState(await listAgentMessages(currentFilters()));
  }

  async function submitComposer() {
    setActionState({ state: "idle" });
    const input = composerInput(composer);
    try {
      if (composer.replyToMessageId.trim()) {
        await respondToAgentMessage(composer.replyToMessageId.trim(), input);
        setActionState({ state: "saved", message: "Agent response saved to durable messages." });
      } else {
        await createAgentMessage(input);
        setActionState({ state: "saved", message: "Product Owner message sent to durable agent channel." });
      }
      setComposer({ ...initialComposer, projectId: composer.projectId });
      await loadMessages();
    } catch (error) {
      setActionState({
        state: "error",
        message: error instanceof Error ? error.message : "Agent message could not be saved safely."
      });
    }
  }

  async function updateMessageState(messageId: string, action: "acknowledge" | "consume") {
    setActionState({ state: "idle" });
    try {
      if (action === "acknowledge") {
        await acknowledgeAgentMessage(messageId);
        setActionState({ state: "saved", message: `${messageId} acknowledged.` });
      } else {
        await consumeAgentMessage(messageId);
        setActionState({ state: "saved", message: `${messageId} consumed.` });
      }
      await loadMessages();
    } catch (error) {
      setActionState({
        state: "error",
        message: error instanceof Error ? error.message : "Agent message action could not be saved safely."
      });
    }
  }

  useEffect(() => {
    void loadMessages();
  }, [projectFilter, roleFilter, messageTypeFilter, statusFilter, jiraIssueFilter]);

  const items = state.items;
  const projects = useMemo(() => uniqueSorted(items.map((item) => item.project_id)), [items]);
  const roles = useMemo(
    () => uniqueSorted(items.flatMap((item) => [item.source_role, item.target_role ?? ""])),
    [items]
  );
  const messageTypes = useMemo(() => uniqueSorted(items.map((item) => item.message_type)), [items]);
  const statuses = useMemo(() => uniqueSorted(items.map((item) => item.status)), [items]);
  const poVisibleCount = items.filter((item) => item.display_lane !== "automated").length;
  const resumeRequests = items.filter((item) => item.message_type === "resume_request").length;

  return (
    <section id="agent-messages" className="messages-panel" aria-label="Agent messages">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Agent Messages</p>
          <h3>Timeline and communication graph</h3>
        </div>
        <button className="icon-button" type="button" onClick={() => void loadMessages()} title="Refresh messages">
          <RefreshCcw size={17} aria-hidden="true" />
        </button>
      </div>

      <div className="inbox-toolbar" aria-label="Agent message filters">
        <label>
          <span>Project</span>
          <select value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
            <option value="all">All Projects</option>
            {projects.map((project) => (
              <option value={project} key={project}>
                {project}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Role</span>
          <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
            <option value="all">All Roles</option>
            {roles.map((role) => (
              <option value={role} key={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Type</span>
          <select value={messageTypeFilter} onChange={(event) => setMessageTypeFilter(event.target.value)}>
            <option value="all">All Types</option>
            {messageTypes.map((messageType) => (
              <option value={messageType} key={messageType}>
                {messageType}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">All Statuses</option>
            {statuses.map((status) => (
              <option value={status} key={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <label className="jira-filter">
          <span>Jira</span>
          <input value={jiraIssueFilter} onChange={(event) => setJiraIssueFilter(event.target.value)} placeholder="AP-29" />
        </label>
      </div>

      <section className="message-composer" aria-label="Product Owner agent message composer">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PO Outbox</p>
            <h4>Send message to agent</h4>
          </div>
          <button className="primary-action" type="button" onClick={() => void submitComposer()}>
            <Send size={16} aria-hidden="true" />
            <span>{composer.replyToMessageId.trim() ? "Send response" : "Send message"}</span>
          </button>
        </div>
        <div className="composer-grid">
          <label>
            <span>Project</span>
            <input
              value={composer.projectId}
              onChange={(event) => setComposer({ ...composer, projectId: event.target.value })}
              placeholder="AP"
            />
          </label>
          <label>
            <span>Type</span>
            <select value={composer.messageType} onChange={(event) => setComposer({ ...composer, messageType: event.target.value })}>
              {poMessageTypes.map((messageType) => (
                <option value={messageType} key={messageType}>
                  {messageType}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Target</span>
            <select value={composer.targetRole} onChange={(event) => setComposer({ ...composer, targetRole: event.target.value })}>
              {targetRoles.map((role) => (
                <option value={role} key={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Jira</span>
            <input
              value={composer.jiraIssueKey}
              onChange={(event) => setComposer({ ...composer, jiraIssueKey: event.target.value })}
              placeholder="AP-29"
            />
          </label>
          <label>
            <span>Assignment</span>
            <input
              value={composer.assignmentId}
              onChange={(event) => setComposer({ ...composer, assignmentId: event.target.value })}
              placeholder="assignment-AP-29-dev"
            />
          </label>
          <label>
            <span>Reply To</span>
            <input
              value={composer.replyToMessageId}
              onChange={(event) => setComposer({ ...composer, replyToMessageId: event.target.value })}
              placeholder="message id"
            />
          </label>
          <label className="composer-wide">
            <span>Subject</span>
            <input value={composer.subject} onChange={(event) => setComposer({ ...composer, subject: event.target.value })} />
          </label>
          <label className="composer-wide">
            <span>Message</span>
            <textarea value={composer.body} onChange={(event) => setComposer({ ...composer, body: event.target.value })} />
          </label>
          <label className="composer-wide">
            <span>References</span>
            <input
              value={composer.references}
              onChange={(event) => setComposer({ ...composer, references: event.target.value })}
              placeholder="comma separated artifact, Jira, PR, or evidence references"
            />
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={composer.responseRequested}
              onChange={(event) => setComposer({ ...composer, responseRequested: event.target.checked })}
            />
            <span>Response requested</span>
          </label>
        </div>
      </section>

      {actionState.state !== "idle" ? (
        <div className={actionState.state === "error" ? "safe-error" : "export-status"} role="status">
          <span>{actionState.message}</span>
        </div>
      ) : null}

      {state.state === "error" && (
        <div className="safe-error" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{state.message}</span>
        </div>
      )}

      <div className="metric-strip">
        <Metric label="Messages" value={items.length} />
        <Metric label="PO-visible" value={poVisibleCount} />
        <Metric label="Resume Requests" value={resumeRequests} />
        <Metric label="Graph Nodes" value={state.graph.nodes.length} />
      </div>

      {state.state === "empty" ? (
        <div className="empty-state">No durable agent messages match the current filters.</div>
      ) : null}

      <div className="message-layout">
        <section className="message-timeline" aria-label="Agent communication timeline">
          <h4>Timeline</h4>
          {items.map((message) => (
            <MessageTimelineItem
              message={message}
              key={message.id}
              onReply={(messageId) => {
                setComposer({ ...composer, replyToMessageId: messageId, jiraIssueKey: message.jira_issue_key ?? "" });
              }}
              onAcknowledge={(messageId) => void updateMessageState(messageId, "acknowledge")}
              onConsume={(messageId) => void updateMessageState(messageId, "consume")}
            />
          ))}
        </section>

        <section className="message-graph" aria-label="Agent communication graph">
          <h4>Graph</h4>
          <div className="graph-node-list" aria-label="Graph nodes">
            {state.graph.nodes.map((node) => (
              <span className={`graph-node ${node.kind}`} key={node.id}>
                {node.label}
                {node.status ? <small>{node.status}</small> : null}
              </span>
            ))}
          </div>
          <div className="graph-edge-list" aria-label="Graph edges">
            {state.graph.edges.map((edge, index) => (
              <div className="graph-edge" key={`${edge.source}-${edge.target}-${edge.label}-${index}`}>
                <GitBranch size={15} aria-hidden="true" />
                <span>{edge.source.replace(/^[^:]+:/, "")}</span>
                <strong>{edge.label}</strong>
                <span>{edge.target.replace(/^[^:]+:/, "")}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function MessageTimelineItem({
  message,
  onReply,
  onAcknowledge,
  onConsume
}: {
  message: AgentMessage;
  onReply: (messageId: string) => void;
  onAcknowledge: (messageId: string) => void;
  onConsume: (messageId: string) => void;
}) {
  const target = message.target_role || message.target_channel || message.target_worker_id || "target not recorded";
  return (
    <article className={`message-card ${laneClass(message.display_lane)}`}>
      <div className="message-card-header">
        <div>
          <span className="project-badge">{message.project_identity || message.project_id}</span>
          <h5>{message.message_type}</h5>
        </div>
        <span className={`status-pill ${statusTone(message.status)}`}>{message.status}</span>
      </div>
      <p className="muted">
        {message.source_role} to {target} · {message.created_at || "time not recorded"}
      </p>
      {message.jira_issue_key || message.assignment_id ? (
        <p className="muted">
          {message.jira_issue_key || "No Jira issue"} · {message.assignment_id || "No assignment"}
        </p>
      ) : null}
      {message.display_lane === "po_inbox_question" ? (
        <p className="message-note">Requires PO inbox decision before work resumes.</p>
      ) : null}
      {message.resume_gate && message.message_type === "resume_request" ? (
        <p className="message-note">
          Resume gate: {message.resume_gate.allowed === false ? "blocked" : "allowed/unknown"} ·{" "}
          {message.resume_gate.reason || "reason not recorded"}
        </p>
      ) : null}
      {message.linked_refs && message.linked_refs.length > 0 ? (
        <div className="artifact-list">
          {message.linked_refs.map((ref) => (
            <span className="artifact-chip" key={`${message.id}-${ref.kind}-${ref.value}`}>
              {ref.kind}: {ref.value}
            </span>
          ))}
        </div>
      ) : null}
      <div className="message-actions" aria-label={`${message.id} message actions`}>
        <button type="button" onClick={() => onReply(message.id)}>
          <MessageCircleReply size={15} aria-hidden="true" />
          <span>Reply</span>
        </button>
        <button type="button" disabled={message.status !== "queued"} onClick={() => onAcknowledge(message.id)}>
          Acknowledge
        </button>
        <button type="button" disabled={!["queued", "acknowledged"].includes(message.status)} onClick={() => onConsume(message.id)}>
          Consume
        </button>
      </div>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function laneClass(value = "automated"): string {
  if (value === "po_inbox_question") {
    return "po-required";
  }
  if (value === "product_owner") {
    return "po-originated";
  }
  return "automated";
}

function statusTone(value: string): string {
  if (["consumed", "completed", "acknowledged"].includes(value)) {
    return "good";
  }
  if (["queued"].includes(value)) {
    return "active";
  }
  if (["rejected", "blocked", "failed"].includes(value)) {
    return "bad";
  }
  return "neutral";
}

function composerInput(input: typeof initialComposer): AgentMessageCreateInput {
  return {
    message_type: input.messageType,
    project_id: input.projectId.trim(),
    project_name: operatorProjectConfig.projectName,
    jira_project_key: operatorProjectConfig.jiraProjectKey,
    target_role: input.targetRole,
    target_channel: "role",
    jira_issue_key: input.jiraIssueKey.trim(),
    assignment_id: input.assignmentId.trim(),
    subject: input.subject.trim(),
    body: input.body.trim(),
    references: input.references
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
    response_requested: input.responseRequested,
    priority: input.messageType === "po_resume_instruction" ? "high" : "normal"
  };
}
