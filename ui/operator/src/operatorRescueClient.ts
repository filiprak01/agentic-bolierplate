import { operatorProjectConfig } from "./operatorConfig";
import type { AssignmentStatusSummary, CodexLimitGateSummary } from "./operatorStatusClient";

export type OperatorRescueActionName =
  | "pause"
  | "resume"
  | "retry"
  | "requeue"
  | "cancel"
  | "clear-stale-lock"
  | "refresh-diagnostics";

export type OperatorRescueDecision = {
  action: OperatorRescueActionName;
  allowed: boolean;
  reason: string;
  blockers: string[];
  effect: string;
};

export type OperatorRescueItem = {
  assignment: AssignmentStatusSummary;
  actions: OperatorRescueDecision[];
};

export type OperatorRescueEnvelope = {
  items: OperatorRescueItem[];
  filters?: {
    project_id?: string;
  };
  stale_lock_minutes?: number;
  codex_limit_gate?: CodexLimitGateSummary;
};

export type OperatorRescueActionResult =
  | {
      state: "applied";
      assignment: AssignmentStatusSummary;
      decision: OperatorRescueDecision;
      previous_status?: string;
      audit_written: boolean;
      audit_ref?: string;
      message_written: boolean;
      message_id?: string;
      message_created?: boolean;
      duplicate_of?: string;
    }
  | {
      state: "blocked";
      assignment?: AssignmentStatusSummary;
      decision?: OperatorRescueDecision;
      message: string;
    }
  | { state: "error"; message: string };

export async function readOperatorRescue(projectId = ""): Promise<OperatorRescueEnvelope> {
  const query = new URLSearchParams();
  if (projectId) {
    query.set("project_id", projectId);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/operator-rescue${suffix}`);
  if (!response.ok) {
    throw new Error(`Operator rescue state could not be loaded safely (${response.status}).`);
  }
  const envelope = (await response.json()) as OperatorRescueEnvelope;
  return {
    ...envelope,
    items: Array.isArray(envelope.items) ? envelope.items : []
  };
}

export async function applyOperatorRescueAction(
  assignmentId: string,
  action: OperatorRescueActionName,
  reason: string
): Promise<OperatorRescueActionResult> {
  try {
    const response = await fetch(
      `${operatorProjectConfig.apiBaseUrl}/operator-rescue/${encodeURIComponent(assignmentId)}/${action}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor: "product_owner",
          reason
        })
      }
    );
    const payload = await response.json();
    if (response.status === 409) {
      return {
        state: "blocked",
        assignment: payload.assignment,
        decision: payload.decision,
        message: payload.decision?.reason ?? "Operator rescue action is blocked."
      };
    }
    if (!response.ok) {
      return {
        state: "error",
        message: payload.error?.message ?? `Operator rescue action could not be saved safely (${response.status}).`
      };
    }
    return {
      state: "applied",
      assignment: payload.assignment,
      decision: payload.decision,
      previous_status: payload.previous_status,
      audit_written: Boolean(payload.audit_written),
      audit_ref: payload.audit_ref,
      message_written: Boolean(payload.message_written),
      message_id: payload.message_id,
      message_created: Boolean(payload.message_created),
      duplicate_of: payload.duplicate_of
    };
  } catch (error) {
    return {
      state: "error",
      message: error instanceof Error ? error.message : "Operator rescue action could not be saved safely."
    };
  }
}
