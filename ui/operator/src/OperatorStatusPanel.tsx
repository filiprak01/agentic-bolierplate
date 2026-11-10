import {
  AlertTriangle,
  FileClock,
  GitBranch,
  ListChecks,
  Pause,
  RefreshCcw,
  RotateCcw,
  ServerCog,
  Stethoscope,
  Undo2,
  XCircle
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import {
  applyOperatorRescueAction,
  readOperatorRescue,
  type OperatorRescueActionName,
  type OperatorRescueDecision,
  type OperatorRescueItem
} from "./operatorRescueClient";
import {
  readOperatorStatus,
  type AssignmentStatusSummary,
  type CodexLimitGateSummary,
  type CodexLimitSummary,
  type LogSummary,
  type OperatorStatusResult,
  type StackedPrLaneSummary,
  type WorkerStatusSummary
} from "./operatorStatusClient";

export type OperatorStatusView = "all" | "agent-status" | "codex-limits" | "logs";
type RescueState = { items: Record<string, OperatorRescueItem>; notice: string; busyKey: string };

const viewHeadings: Record<OperatorStatusView, { eyebrow: string; title: string }> = {
  all: {
    eyebrow: "Runtime Status",
    title: "Workers, assignments, limits, and logs"
  },
  "agent-status": {
    eyebrow: "Agent Status",
    title: "Workers and assignments"
  },
  "codex-limits": {
    eyebrow: "Codex Limits",
    title: "Capacity and quota records"
  },
  logs: {
    eyebrow: "Recent Logs",
    title: "Evidence and runtime records"
  }
};

export function OperatorStatusPanel({ view = "all" }: { view?: OperatorStatusView }) {
  const [statusState, setStatusState] = useState<OperatorStatusResult | { state: "loading" }>({ state: "loading" });
  const [rescueState, setRescueState] = useState<RescueState>({ items: {}, notice: "", busyKey: "" });
  const heading = viewHeadings[view];

  async function loadStatus() {
    setStatusState({ state: "loading" });
    const statusResult = await readOperatorStatus();
    if (statusResult.state === "loaded") {
      try {
        const rescue = await readOperatorRescue();
        setRescueState({
          items: Object.fromEntries(rescue.items.map((item) => [item.assignment.id, item])),
          notice: "",
          busyKey: ""
        });
      } catch (error) {
        setRescueState({
          items: {},
          notice: error instanceof Error ? error.message : "Operator rescue state could not be loaded safely.",
          busyKey: ""
        });
      }
    }
    setStatusState(statusResult);
  }

  async function onRescueAction(assignment: AssignmentStatusSummary, action: OperatorRescueActionName) {
    const busyKey = `${assignment.id}:${action}`;
    setRescueState((current) => ({ ...current, busyKey, notice: "" }));
    const result = await applyOperatorRescueAction(
      assignment.id,
      action,
      `${formatLabel(action)} requested from Operator Status for ${assignment.jira_issue_key}.`
    );
    if (result.state === "applied") {
      await loadStatus();
      setRescueState((current) => ({
        ...current,
        notice: `Operator rescue ${formatLabel(action)} saved for ${assignment.jira_issue_key}.`,
        busyKey: ""
      }));
      return;
    }
    setRescueState((current) => ({
      ...current,
      notice: result.message,
      busyKey: ""
    }));
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  return (
    <section className="status-panel" aria-label="Operator status">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{heading.eyebrow}</p>
          <h3>{heading.title}</h3>
        </div>
        <button className="icon-button" type="button" onClick={() => void loadStatus()} title="Refresh status">
          <RefreshCcw size={17} aria-hidden="true" />
        </button>
      </div>

      {statusState.state === "loading" && <div className="empty-state">Loading operator status...</div>}

      {statusState.state === "error" && (
        <div className="safe-error" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{statusState.message}</span>
        </div>
      )}

      {statusState.state === "loaded" && (
        <div className="status-grid">
          {(view === "all" || view === "agent-status") && (
            <AgentStatusSection
              workers={statusState.status.workers}
              assignments={statusState.status.assignments}
              stackLanes={statusState.status.stack_lanes ?? []}
              limitGate={statusState.status.codex_limit_gate}
              rescueItems={rescueState.items}
              rescueNotice={rescueState.notice}
              rescueBusyKey={rescueState.busyKey}
              onRescueAction={onRescueAction}
            />
          )}
          {(view === "all" || view === "codex-limits") && <CodexLimitSection limit={statusState.status.codex_limit} />}
          {(view === "all" || view === "logs") && <RecentLogsSection logs={statusState.status.recent_logs} />}
        </div>
      )}
    </section>
  );
}

function AgentStatusSection({
  workers,
  assignments,
  stackLanes,
  limitGate,
  rescueItems,
  rescueNotice,
  rescueBusyKey,
  onRescueAction
}: {
  workers: WorkerStatusSummary[];
  assignments: AssignmentStatusSummary[];
  stackLanes: StackedPrLaneSummary[];
  limitGate?: CodexLimitGateSummary;
  rescueItems: Record<string, OperatorRescueItem>;
  rescueNotice: string;
  rescueBusyKey: string;
  onRescueAction: (assignment: AssignmentStatusSummary, action: OperatorRescueActionName) => void;
}) {
  const activeAssignments = assignments.filter((assignment) =>
    ["queued", "assigned", "in_progress", "paused_limit", "paused_po", "failed"].includes(assignment.status)
  );
  const blockedAssignments = assignments.filter((assignment) =>
    ["paused_limit", "paused_po", "failed"].includes(assignment.status)
  );
  const groupedAssignments = groupAssignmentsByProject(assignments);

  return (
    <article id="agent-status" className="status-section">
      <StatusSectionHeader icon={ServerCog} label="Agent Status" />
      <div className="metric-strip">
        <Metric label="Workers" value={workers.length} />
        <Metric label="Open Assignments" value={activeAssignments.length} />
        <Metric label="Blocked/Waiting" value={blockedAssignments.length} />
        <Metric label="Limit Gate" value={formatLabel(limitGate?.action ?? "unknown")} />
      </div>
      {limitGate ? (
        <div className={`limit-gate-banner ${limitGate.allowed ? "good" : "warn"}`} role="status">
          <span>{limitGate.reason}</span>
          {limitGate.resume_after ? <strong>Resume after {limitGate.resume_after}</strong> : null}
        </div>
      ) : null}
      {rescueNotice ? (
        <div className="limit-gate-banner warn" role="status">
          <span>{rescueNotice}</span>
        </div>
      ) : null}

      <h4>Known Workers</h4>
      {workers.length === 0 ? (
        <p className="muted">No durable worker registrations are present.</p>
      ) : (
        <div className="status-table" role="table" aria-label="Known workers">
          {workers.map((worker) => (
            <div className="status-row" role="row" key={worker.id}>
              <span className="row-title">{worker.display_name || worker.id}</span>
              <span>{worker.role}</span>
              <StatusPill value={worker.status} />
              <span>{worker.current_assignment_id || "unassigned"}</span>
            </div>
          ))}
        </div>
      )}

      <h4>Assignments</h4>
      {assignments.length === 0 ? (
        <p className="muted">No durable assignment records are present.</p>
      ) : (
        <div className="status-table" role="table" aria-label="Assignments">
          {assignments.map((assignment) => (
            <div className="status-row" role="row" key={assignment.id}>
              <span className="row-title">{assignment.jira_issue_key}</span>
              <span>{projectIdentity(assignment)}</span>
              <StatusPill value={assignment.status} />
              <span>{assignment.story_lifecycle?.next_expected_step || assignment.role}</span>
            </div>
          ))}
        </div>
      )}

      <StackedPrLanesSection lanes={stackLanes} />

      <h4>Story Lifecycle</h4>
      {assignments.length === 0 ? (
        <p className="muted">No story lifecycle records are present.</p>
      ) : (
        <div className="lifecycle-board" aria-label="Story lifecycle by project">
          {groupedAssignments.map((group) => (
            <section className="lifecycle-group" key={group.identity}>
              <div className="section-heading">
                <div>
                  <p className="eyebrow">{group.identity}</p>
                  <h5>{group.assignments.length} assignment{group.assignments.length === 1 ? "" : "s"}</h5>
                </div>
              </div>
              {group.assignments.map((assignment) => (
                <StoryLifecycleCard
                  assignment={assignment}
                  rescueItem={rescueItems[assignment.id]}
                  rescueBusyKey={rescueBusyKey}
                  onRescueAction={onRescueAction}
                  key={assignment.id}
                />
              ))}
            </section>
          ))}
        </div>
      )}
    </article>
  );
}

function StackedPrLanesSection({ lanes }: { lanes: StackedPrLaneSummary[] }) {
  return (
    <section className="stack-lanes-section" aria-label="Stacked PR lanes">
      <StatusSectionHeader icon={GitBranch} label="Stacked PR Lanes" />
      {lanes.length === 0 ? (
        <p className="muted">No stacked PR lane records are present.</p>
      ) : (
        <div className="stack-lane-board">
          {lanes.map((lane) => (
            <article className="stack-lane-card" key={`${lane.stack_id}-${lane.lane_id}`}>
              <div className="stack-lane-header">
                <div>
                  <span className="project-badge">Stack {lane.stack_id}</span>
                  <h5>Lane {lane.lane_id}</h5>
                </div>
                <StatusPill value={lane.stack_mode || "stacked"} />
              </div>
              <p className="muted">Resolver: {lane.resolved_path_version || "not recorded"}</p>
              <div className="stack-story-list">
                {lane.stories.map((story) => (
                  <div className="stack-story-row" key={story.assignment_id}>
                    <span className="stack-layer">Layer {story.layer_order}</span>
                    <strong>{story.jira_issue_key}</strong>
                    <span>{formatLabel(story.current_agent)}</span>
                    <StatusPill value={story.current_status} />
                    <span>Next: {formatLabel(story.next_step || "not recorded")}</span>
                    <StatusPill value={story.evidence_state} />
                    {story.stale_retest_required ? <span className="stack-warning">Retest needed</span> : null}
                    {story.blocked_reason ? <span className="stack-warning">{story.blocked_reason}</span> : null}
                    {story.pull_request_urls.length > 0 ? (
                      <div className="artifact-list">
                        {story.pull_request_urls.map((url) => (
                          <a className="artifact-chip" href={url} target="_blank" rel="noreferrer" key={url}>
                            PR link
                          </a>
                        ))}
                      </div>
                    ) : story.branch_name ? (
                      <span className="artifact-chip">Branch: {story.branch_name}</span>
                    ) : (
                      <span className="muted">PR not recorded</span>
                    )}
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function StoryLifecycleCard({
  assignment,
  rescueItem,
  rescueBusyKey,
  onRescueAction
}: {
  assignment: AssignmentStatusSummary;
  rescueItem?: OperatorRescueItem;
  rescueBusyKey: string;
  onRescueAction: (assignment: AssignmentStatusSummary, action: OperatorRescueActionName) => void;
}) {
  const lifecycle = assignment.story_lifecycle;
  const artifacts = assignment.artifact_refs ?? [];
  if (!lifecycle) {
    return (
      <section className="lifecycle-card">
        <strong>{assignment.jira_issue_key}</strong>
        <p className="muted">Needs process mapping before lifecycle can be inferred.</p>
        <OperatorRescueControls
          assignment={assignment}
          rescueItem={rescueItem}
          rescueBusyKey={rescueBusyKey}
          onRescueAction={onRescueAction}
        />
      </section>
    );
  }

  return (
    <section className="lifecycle-card">
      <div className="lifecycle-card-header">
        <div>
          <span className="project-badge">{projectIdentity(assignment)}</span>
          <h5>{assignment.jira_issue_key}</h5>
        </div>
        <StatusPill value={assignment.status} />
      </div>
      <p className="muted">
        Sprint: {lifecycle.sprint_label || "Sprint not recorded"} · Next: {lifecycle.next_expected_step}
      </p>
      {lifecycle.blocked_reason ? <p className="blocked-reason">{lifecycle.blocked_reason}</p> : null}
      {lifecycle.needs_process_mapping ? (
        <p className="blocked-reason">Needs process mapping</p>
      ) : null}
      <div className="lifecycle-rail" aria-label={`${assignment.jira_issue_key} lifecycle steps`}>
        {lifecycle.steps.map((step) => (
          <div className={`lifecycle-step ${stateClass(step.state)}`} key={step.id}>
            <span className="lifecycle-dot" aria-hidden="true" />
            <span>{step.label}</span>
            <small>{step.state}</small>
          </div>
        ))}
      </div>
      {artifacts.length > 0 ? (
        <div className="artifact-list" aria-label={`${assignment.jira_issue_key} artifact references`}>
          {artifacts.map((artifact) => (
            <span className="artifact-chip" key={`${artifact.kind}-${artifact.path}`}>
              {formatLabel(artifact.kind)}: {artifact.path}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted">No safe artifact references recorded.</p>
      )}
      <OperatorRescueControls
        assignment={assignment}
        rescueItem={rescueItem}
        rescueBusyKey={rescueBusyKey}
        onRescueAction={onRescueAction}
      />
    </section>
  );
}

function OperatorRescueControls({
  assignment,
  rescueItem,
  rescueBusyKey,
  onRescueAction
}: {
  assignment: AssignmentStatusSummary;
  rescueItem?: OperatorRescueItem;
  rescueBusyKey: string;
  onRescueAction: (assignment: AssignmentStatusSummary, action: OperatorRescueActionName) => void;
}) {
  if (!rescueItem) {
    return <p className="muted">Operator rescue decisions are not loaded for this assignment.</p>;
  }
  return (
    <div className="rescue-controls" aria-label={`${assignment.jira_issue_key} operator rescue controls`}>
      <div>
        <span className="row-title">Operator Rescue</span>
        <p className="muted">Safe actions write audit and agent communication records.</p>
      </div>
      <div className="rescue-action-grid">
        {rescueItem.actions.map((decision) => (
          <RescueActionButton
            assignment={assignment}
            decision={decision}
            busyKey={rescueBusyKey}
            onRescueAction={onRescueAction}
            key={decision.action}
          />
        ))}
      </div>
    </div>
  );
}

function RescueActionButton({
  assignment,
  decision,
  busyKey,
  onRescueAction
}: {
  assignment: AssignmentStatusSummary;
  decision: OperatorRescueDecision;
  busyKey: string;
  onRescueAction: (assignment: AssignmentStatusSummary, action: OperatorRescueActionName) => void;
}) {
  const Icon = rescueActionIcon(decision.action);
  const buttonKey = `${assignment.id}:${decision.action}`;
  const disabled = !decision.allowed || busyKey === buttonKey;
  const blocker = decision.blockers[0] ?? decision.reason;
  return (
    <button
      className={`rescue-action ${decision.allowed ? "allowed" : "blocked"}`}
      type="button"
      disabled={disabled}
      title={decision.allowed ? decision.effect : blocker}
      onClick={() => onRescueAction(assignment, decision.action)}
    >
      <Icon size={15} aria-hidden="true" />
      <span>{formatLabel(decision.action)}</span>
    </button>
  );
}

function CodexLimitSection({ limit }: { limit: CodexLimitSummary | null }) {
  return (
    <article id="codex-limits" className="status-section">
      <StatusSectionHeader icon={ListChecks} label="Codex Limits" />
      {!limit ? (
        <p className="muted">No durable Codex limit record is present.</p>
      ) : (
        <>
          <div className="metric-strip">
            <Metric label="Action" value={formatLabel(limit.recommended_action)} />
            <Metric label="Record" value={limit.id} />
          </div>
          <div className="limit-grid">
            <LimitWindow label="Short Window" window={limit.short_window} />
            <LimitWindow label="Broad Quota" window={limit.broad_quota} />
          </div>
          {limit.note ? <p className="muted">{limit.note}</p> : null}
        </>
      )}
    </article>
  );
}

function RecentLogsSection({ logs }: { logs: LogSummary[] }) {
  return (
    <article id="logs" className="status-section">
      <StatusSectionHeader icon={FileClock} label="Recent Logs" />
      {logs.length === 0 ? (
        <p className="muted">No durable log files are present.</p>
      ) : (
        <div className="log-list" aria-label="Recent durable logs">
          {logs.map((log) => (
            <div className="log-row" key={log.relative_path}>
              <span className="row-title">{log.name}</span>
              <span>{log.relative_path}</span>
              <span>{formatBytes(log.size_bytes)} · {log.modified_at}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function LimitWindow({ label, window }: { label: string; window: CodexLimitSummary["short_window"] }) {
  return (
    <div className="limit-window">
      <span className="row-title">{label}</span>
      <StatusPill value={window.status} />
      <span>{window.remaining_percent ?? "unknown"}% remaining</span>
      <span>Reset: {window.reset_at || "unknown"}</span>
    </div>
  );
}

function StatusSectionHeader({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <header className="status-section-header">
      <div className="route-icon" aria-hidden="true">
        <Icon size={22} />
      </div>
      <h4>{label}</h4>
    </header>
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

function StatusPill({ value }: { value: string }) {
  return <span className={`status-pill ${statusTone(value)}`}>{formatLabel(value)}</span>;
}

function statusTone(value: string): string {
  if (["available", "completed", "resume", "final"].includes(value)) {
    return "good";
  }
  if (["assigned", "in_progress", "queued", "provisional"].includes(value)) {
    return "active";
  }
  if (
    ["paused", "paused_limit", "paused_po", "limited", "wait", "downgrade_model", "stale", "not-recorded"].includes(
      value
    )
  ) {
    return "warn";
  }
  if (["failed", "offline", "blocked"].includes(value)) {
    return "bad";
  }
  return "neutral";
}

function groupAssignmentsByProject(assignments: AssignmentStatusSummary[]) {
  const groups = new Map<string, AssignmentStatusSummary[]>();
  for (const assignment of assignments) {
    const key = projectIdentity(assignment);
    groups.set(key, [...(groups.get(key) ?? []), assignment]);
  }
  return Array.from(groups.entries()).map(([identity, grouped]) => ({ identity, assignments: grouped }));
}

function projectIdentity(assignment: AssignmentStatusSummary): string {
  if (assignment.project_name && assignment.jira_project_key) {
    return `${assignment.project_name} (${assignment.jira_project_key})`;
  }
  return assignment.project_name || assignment.jira_project_key || assignment.project_id || "Project not recorded";
}

function stateClass(state: string): string {
  if (state === "done") {
    return "done";
  }
  if (state === "next") {
    return "next";
  }
  if (state === "blocked/stuck") {
    return "blocked";
  }
  if (state === "skipped/not applicable") {
    return "skipped";
  }
  return "pending";
}

function rescueActionIcon(action: OperatorRescueActionName): LucideIcon {
  if (action === "pause") {
    return Pause;
  }
  if (action === "resume") {
    return Undo2;
  }
  if (action === "cancel") {
    return XCircle;
  }
  if (action === "refresh-diagnostics") {
    return Stethoscope;
  }
  return RotateCcw;
}

function formatLabel(value: string): string {
  return value.replaceAll("_", " ").replaceAll("-", " ");
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  return `${Math.round(value / 1024)} KB`;
}
