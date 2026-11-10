import { operatorProjectConfig } from "./operatorConfig";

export type CodexLimitWindowStatus = "available" | "limited" | "unknown";
export type CodexLimitPlanMode = "single_pool" | "dual_window" | "dynamic";

export type CodexLimitWindowSummary = {
  label?: string;
  window_id?: string;
  bucket_id?: string;
  window_name?: string;
  status: CodexLimitWindowStatus | string;
  remaining_percent?: number | null;
  remainingPercent?: number | null;
  usedPercent?: number | null;
  reset_at?: string;
  resetsAt?: string;
  window_duration_minutes?: number | null;
  windowDurationMins?: number | null;
  authoritative?: boolean;
  observation_source?: string;
  observed_at?: string;
};

export type CodexLimitRecord = {
  id: string;
  plan_mode: CodexLimitPlanMode | string;
  recommended_action: string;
  note?: string;
  short_window: CodexLimitWindowSummary;
  broad_quota: CodexLimitWindowSummary;
  windows?: CodexLimitWindowSummary[];
};

export type CodexLimitGate = {
  allowed: boolean;
  action: string;
  reason: string;
  resume_after?: string;
};

export type CodexLiveRefresh = {
  status: string;
  source: string;
  live_capable?: boolean;
  record_id?: string;
  observed_at?: string;
  raw_window_count?: number;
  error?: string;
};

export type CodexLiveAuthSummary = {
  subscription_auth: boolean;
  account_type?: string;
  plan_type?: string;
  reason?: string;
  source?: string;
};

export type CodexLiveProviderSummary = {
  source?: string;
  bucket_id?: string;
  bucket_name?: string;
  plan_type?: string;
  raw_bucket_count?: number;
  rate_limit_reached_type?: string | null;
  spend_control_reached?: boolean | null;
  reset_credit_count?: number | null;
  credits?: {
    has_credits?: boolean | null;
    unlimited?: boolean | null;
    balance?: string;
  };
};

export type CodexLimitsSnapshot = {
  latest_record: CodexLimitRecord | null;
  gate: CodexLimitGate;
  windows: CodexLimitWindowSummary[];
  generated_at: string;
  live_refresh?: CodexLiveRefresh;
  auth?: CodexLiveAuthSummary;
  provider?: CodexLiveProviderSummary;
  canStartWork?: boolean;
  blocking_reason?: string;
};

export type CodexLimitsResult =
  | { state: "loaded"; snapshot: CodexLimitsSnapshot }
  | { state: "error"; message: string };

export type CodexLimitWindowUpdate = {
  window_id: string;
  label: string;
  status: CodexLimitWindowStatus;
  remaining_percent?: number | null;
  reset_at: string;
  authoritative: boolean;
};

export type CodexLimitRecordUpdate = {
  plan_mode: CodexLimitPlanMode;
  note?: string;
  windows: CodexLimitWindowUpdate[];
};

export async function readCodexLimits(): Promise<CodexLimitsResult> {
  try {
    const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/codex-limits`);
    if (!response.ok) {
      return { state: "error", message: `Codex limits could not be loaded safely (${response.status}).` };
    }
    return { state: "loaded", snapshot: normalizeSnapshot((await response.json()) as CodexLimitsSnapshot) };
  } catch (error) {
    return {
      state: "error",
      message: error instanceof Error ? error.message : "Codex limits could not be loaded safely."
    };
  }
}

export async function refreshLiveCodexLimits(): Promise<CodexLimitsSnapshot> {
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/codex-limits/refresh`, {
    method: "POST"
  });
  const payload = (await response.json().catch(() => null)) as CodexLimitsSnapshot | { error?: { message?: string } } | null;
  if (!payload || !("gate" in payload)) {
    const message = payload && "error" in payload ? payload.error?.message : undefined;
    throw new Error(message ?? `Live Codex limits could not be refreshed safely (${response.status}).`);
  }
  return normalizeSnapshot(payload as CodexLimitsSnapshot);
}

export async function saveCodexLimitRecord(update: CodexLimitRecordUpdate): Promise<CodexLimitsSnapshot> {
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/codex-limits/records`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update)
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as { error?: { message?: string } };
    throw new Error(error.error?.message ?? `Codex limit record could not be saved safely (${response.status}).`);
  }
  return normalizeSnapshot((await response.json()) as CodexLimitsSnapshot);
}

function normalizeSnapshot(snapshot: CodexLimitsSnapshot): CodexLimitsSnapshot {
  const windows = Array.isArray(snapshot.windows) ? snapshot.windows.map(normalizeWindow) : [];
  return {
    latest_record: snapshot.latest_record ?? null,
    gate: snapshot.gate ?? {
      allowed: false,
      action: "ask_product_owner",
      reason: "Codex limit availability is unknown."
    },
    windows,
    generated_at: snapshot.generated_at ?? "",
    live_refresh: snapshot.live_refresh,
    auth: snapshot.auth,
    provider: snapshot.provider,
    canStartWork: snapshot.canStartWork ?? snapshot.gate?.allowed ?? false,
    blocking_reason: snapshot.blocking_reason ?? (snapshot.gate?.allowed ? "" : snapshot.gate?.reason ?? "")
  };
}

function normalizeWindow(limitWindow: CodexLimitWindowSummary): CodexLimitWindowSummary {
  const remainingPercent = limitWindow.remainingPercent ?? limitWindow.remaining_percent ?? null;
  const resetAt = limitWindow.resetsAt ?? limitWindow.reset_at ?? "";
  const windowDurationMins = limitWindow.windowDurationMins ?? limitWindow.window_duration_minutes ?? null;
  return {
    ...limitWindow,
    remaining_percent: remainingPercent,
    remainingPercent,
    resetsAt: resetAt,
    reset_at: resetAt,
    window_duration_minutes: windowDurationMins,
    windowDurationMins
  };
}
