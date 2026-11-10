import { operatorProjectConfig } from "./operatorConfig";

export type WorkerStatusSummary = {
  id: string;
  role: string;
  status: string;
  display_name?: string;
  container_name?: string;
  workspace_path?: string;
  current_assignment_id?: string;
  updated_at?: string;
};

export type AssignmentStatusSummary = {
  id: string;
  jira_issue_key: string;
  role: string;
  status: string;
  worker_id?: string;
  branch_name?: string;
  project_id?: string;
  project_name?: string;
  repository?: string;
  jira_project_key?: string;
  updated_at?: string;
  pause_reason?: string;
  failure_reason?: string;
  artifact_refs?: AssignmentArtifactRef[];
  story_lifecycle?: StoryLifecycleSummary;
  stack_metadata?: AssignmentStackMetadataSummary;
};

export type AssignmentStackMetadataSummary = {
  stack_id: string;
  lane_id: string;
  stack_mode: string;
  resolved_path_version: string;
  current_layer: number;
  expected_next_agent: string;
  stale_state: string;
  rebase_required: boolean;
};

export type StackedPrLaneStorySummary = {
  jira_issue_key: string;
  assignment_id: string;
  role: string;
  current_agent: string;
  current_status: string;
  layer_order: number;
  stack_id: string;
  lane_id: string;
  stack_mode: string;
  resolved_path_version: string;
  branch_name?: string;
  pull_request_urls: string[];
  next_step: string;
  blocked_reason?: string;
  stale_retest_required: boolean;
  evidence_state: string;
};

export type StackedPrLaneSummary = {
  stack_id: string;
  lane_id: string;
  stack_mode: string;
  resolved_path_version: string;
  stories: StackedPrLaneStorySummary[];
};

export type CodexLimitWindowSummary = {
  status: string;
  remaining_percent?: number | null;
  reset_at?: string;
  observation_source?: string;
  observed_at?: string;
};

export type CodexLimitSummary = {
  id: string;
  recommended_action: string;
  note?: string;
  short_window: CodexLimitWindowSummary;
  broad_quota: CodexLimitWindowSummary;
};

export type CodexLimitGateSummary = {
  allowed: boolean;
  action: string;
  reason: string;
  resume_after?: string;
};

export type AssignmentArtifactRef = {
  kind: string;
  path: string;
};

export type StoryLifecycleStep = {
  id: string;
  label: string;
  role: string;
  state: string;
  artifact_refs?: AssignmentArtifactRef[];
};

export type StoryLifecycleSummary = {
  needs_process_mapping: boolean;
  next_expected_step: string;
  blocked_reason?: string;
  sprint_label?: string;
  steps: StoryLifecycleStep[];
};

export type LogSummary = {
  name: string;
  relative_path: string;
  size_bytes: number;
  modified_at: string;
};

export type OperatorStatus = {
  workers: WorkerStatusSummary[];
  assignments: AssignmentStatusSummary[];
  stack_lanes?: StackedPrLaneSummary[];
  codex_limit: CodexLimitSummary | null;
  codex_limit_gate?: CodexLimitGateSummary;
  codex_limit_windows?: CodexLimitWindowSummary[];
  recent_logs: LogSummary[];
};

export type OperatorStatusResult =
  | { state: "loaded"; status: OperatorStatus }
  | { state: "error"; message: string };

export async function readOperatorStatus(): Promise<OperatorStatusResult> {
  try {
    const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/operator-status`);
    if (!response.ok) {
      return { state: "error", message: `Operator status could not be loaded safely (${response.status}).` };
    }
    const status = (await response.json()) as OperatorStatus;
    return {
      state: "loaded",
      status: {
        workers: Array.isArray(status.workers) ? status.workers : [],
        assignments: Array.isArray(status.assignments) ? status.assignments : [],
        stack_lanes: Array.isArray(status.stack_lanes) ? status.stack_lanes : [],
        codex_limit: status.codex_limit ?? null,
        codex_limit_gate: status.codex_limit_gate,
        codex_limit_windows: Array.isArray(status.codex_limit_windows) ? status.codex_limit_windows : [],
        recent_logs: Array.isArray(status.recent_logs) ? status.recent_logs : []
      }
    };
  } catch (error) {
    return {
      state: "error",
      message: error instanceof Error ? error.message : "Operator status could not be loaded safely."
    };
  }
}
