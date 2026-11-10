import { AlertTriangle, CheckCircle2, Clock3, RefreshCcw, Save, Wifi } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  readCodexLimits,
  refreshLiveCodexLimits,
  saveCodexLimitRecord,
  type CodexLimitGate,
  type CodexLimitPlanMode,
  type CodexLimitWindowStatus,
  type CodexLimitsResult,
  type CodexLimitsSnapshot
} from "./codexLimitsClient";

type LimitFormRow = {
  windowId: string;
  label: string;
  status: CodexLimitWindowStatus;
  remainingPercent: string;
  resetAt: string;
  authoritative: boolean;
};

type SaveState = { state: "idle" } | { state: "saved"; message: string } | { state: "error"; message: string };
type LiveState = { state: "idle" } | { state: "loading" } | { state: "done"; message: string } | { state: "error"; message: string };

const emptyGate: CodexLimitGate = {
  allowed: false,
  action: "ask_product_owner",
  reason: "No Codex limit availability record is available."
};

export function CodexLimitsPanel() {
  const [limitsState, setLimitsState] = useState<CodexLimitsResult | { state: "loading" }>({ state: "loading" });
  const [planMode, setPlanMode] = useState<CodexLimitPlanMode>("single_pool");
  const [rows, setRows] = useState<LimitFormRow[]>(defaultRows("single_pool"));
  const [note, setNote] = useState("");
  const [saveState, setSaveState] = useState<SaveState>({ state: "idle" });
  const [liveState, setLiveState] = useState<LiveState>({ state: "idle" });

  async function loadLimits() {
    setLimitsState({ state: "loading" });
    const result = await readCodexLimits();
    setLimitsState(result);
    if (result.state === "loaded") {
      applySnapshot(result.snapshot);
    }
  }

  async function refreshLiveLimits() {
    setLiveState({ state: "loading" });
    try {
      const snapshot = await refreshLiveCodexLimits();
      setLimitsState({ state: "loaded", snapshot });
      applySnapshot(snapshot);
      const status = snapshot.live_refresh?.status ? formatLabel(snapshot.live_refresh.status) : "Live refresh finished";
      setLiveState({ state: "done", message: status });
    } catch (error) {
      setLiveState({
        state: "error",
        message: error instanceof Error ? error.message : "Live Codex limits could not be refreshed safely."
      });
    }
  }

  function applySnapshot(snapshot: CodexLimitsSnapshot) {
    const nextMode = normalizePlanMode(snapshot.latest_record?.plan_mode);
    setPlanMode(nextMode);
    setRows(rowsFromSnapshot(snapshot, nextMode));
    setNote(snapshot.latest_record?.note ?? "");
  }

  useEffect(() => {
    void loadLimits();
  }, []);

  const validationErrors = useMemo(() => validateRows(rows), [rows]);
  const canSave = validationErrors.length === 0;
  const snapshot = limitsState.state === "loaded" ? limitsState.snapshot : null;
  const gate = snapshot?.gate ?? emptyGate;
  const displayWindows = useMemo(() => {
    const windows = snapshot?.windows.length ? snapshot.windows : [];
    if (windows.length) {
      return windows.map((limitWindow, index) => {
        const remaining = limitWindow.remainingPercent ?? limitWindow.remaining_percent;
        const used = limitWindow.usedPercent;
        const duration = limitWindow.windowDurationMins ?? limitWindow.window_duration_minutes;
        return {
          windowId: limitWindow.window_id || `window_${index + 1}`,
          label: limitWindow.label || `Window ${index + 1}`,
          status: limitWindow.status,
          remainingPercent: remaining === null || remaining === undefined ? "unknown" : String(remaining),
          usedPercent: used === null || used === undefined ? "unknown" : String(used),
          resetAt: limitWindow.resetsAt || limitWindow.reset_at || "unknown",
          bucketId: limitWindow.bucket_id || "default",
          windowName: limitWindow.window_name || "",
          duration: duration === null || duration === undefined ? "unknown" : `${duration} min`,
          source: limitWindow.observation_source || "unknown"
        };
      });
    }
    return rows.map((row) => ({
      windowId: row.windowId,
      label: row.label,
      status: row.status,
      remainingPercent: row.remainingPercent || "unknown",
      usedPercent: row.remainingPercent ? String(100 - Number(row.remainingPercent)) : "unknown",
      resetAt: toIsoLikeValue(row.resetAt) || "unknown",
      bucketId: "manual",
      windowName: "",
      duration: "unknown",
      source: "operator"
    }));
  }, [rows, snapshot]);

  function changePlanMode(nextMode: CodexLimitPlanMode) {
    setPlanMode(nextMode);
    setRows(normalizeRowsForMode(rows, nextMode));
    setSaveState({ state: "idle" });
  }

  function updateRow(index: number, patch: Partial<LimitFormRow>) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
    setSaveState({ state: "idle" });
  }

  async function saveLimitRecord() {
    if (!canSave) {
      return;
    }
    try {
      const saved = await saveCodexLimitRecord({
        plan_mode: planMode,
        note,
        windows: rows.map((row) => ({
          window_id: row.windowId,
          label: row.label,
          status: row.status,
          remaining_percent: row.status === "unknown" ? null : Number(row.remainingPercent),
          reset_at: toIsoLikeValue(row.resetAt),
          authoritative: row.authoritative
        }))
      });
      setLimitsState({ state: "loaded", snapshot: saved });
      applySnapshot(saved);
      setSaveState({ state: "saved", message: `Saved ${saved.latest_record?.id ?? "limit record"}.` });
    } catch (error) {
      setSaveState({
        state: "error",
        message: error instanceof Error ? error.message : "Codex limit record could not be saved safely."
      });
    }
  }

  return (
    <section id="codex-limits" className="limits-panel" aria-label="Codex limits">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Codex Limits</p>
          <h3>Capacity and quota records</h3>
        </div>
        <div className="action-buttons">
          <button className="icon-button" type="button" onClick={() => void loadLimits()} title="Refresh cached limits">
            <RefreshCcw size={17} aria-hidden="true" />
          </button>
          <button type="button" onClick={() => void refreshLiveLimits()} disabled={liveState.state === "loading"}>
            <Wifi size={16} aria-hidden="true" />
            {liveState.state === "loading" ? "Checking" : "Live check"}
          </button>
        </div>
      </div>

      {limitsState.state === "loading" && <div className="empty-state">Loading Codex limits...</div>}

      {limitsState.state === "error" && (
        <div className="safe-error" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{limitsState.message}</span>
        </div>
      )}

      {snapshot ? (
        <div className="limit-summary-grid" aria-label="Current limit summary">
          <LimitMetric label="Recommended action" value={formatLabel(gate.action)} tone={gate.allowed ? "good" : "warn"} />
          <LimitMetric label="Record" value={snapshot.latest_record?.id ?? "No record"} />
          <LimitMetric label="Plan mode" value={formatLabel(snapshot.latest_record?.plan_mode ?? planMode)} />
          <LimitMetric label="Generated" value={snapshot.generated_at || "Unknown"} />
          <LimitMetric
            label="Auth"
            value={snapshot.auth?.subscription_auth ? "ChatGPT subscription" : snapshot.auth?.reason ?? "Cached/manual"}
            tone={snapshot.auth?.subscription_auth ? "good" : snapshot.auth ? "warn" : "neutral"}
          />
          <LimitMetric label="Provider" value={snapshot.provider?.bucket_id ?? snapshot.provider?.plan_type ?? "Cached"} />
          <LimitMetric label="Reset credits" value={formatMaybeNumber(snapshot.provider?.reset_credit_count)} />
          <LimitMetric label="Live status" value={formatLabel(snapshot.live_refresh?.status ?? "cached latest")} />
        </div>
      ) : null}

      <div className={`limit-gate-banner ${gate.allowed ? "good" : "warn"}`} role="status">
        {gate.allowed ? <CheckCircle2 size={18} aria-hidden="true" /> : <AlertTriangle size={18} aria-hidden="true" />}
        <span>{gate.reason}</span>
        {gate.resume_after ? <strong>Resume after {gate.resume_after}</strong> : null}
      </div>

      {liveState.state === "done" || liveState.state === "error" ? (
        <div className={liveState.state === "error" ? "safe-error" : "export-status"} role="status">
          <span>{liveState.message}</span>
        </div>
      ) : null}

      <div className="limit-window-grid">
        {displayWindows.map((limitWindow) => (
          <div className="limit-window-card" key={limitWindow.windowId}>
            <span className="row-title">{limitWindow.label}</span>
            <span className={`status-pill ${statusTone(limitWindow.status)}`}>{formatLabel(limitWindow.status)}</span>
            <strong>{limitWindow.remainingPercent}% remaining</strong>
            <span>Used: {limitWindow.usedPercent}%</span>
            <span>Reset: {limitWindow.resetAt}</span>
            <span>Window: {limitWindow.windowName || limitWindow.duration}</span>
            <span>Bucket: {limitWindow.bucketId}</span>
            <span>Source: {formatLabel(limitWindow.source)}</span>
          </div>
        ))}
      </div>

      <form className="limit-form" onSubmit={(event) => event.preventDefault()} aria-label="Atomic Codex limit update">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Atomic Update</p>
            <h4>Save limit record</h4>
          </div>
          <Clock3 size={20} aria-hidden="true" />
        </div>

        <label>
          <span>Plan mode</span>
          <select value={planMode} onChange={(event) => changePlanMode(event.target.value as CodexLimitPlanMode)}>
            <option value="single_pool">Single-pool Pro plan</option>
            <option value="dual_window">Short and broad windows</option>
          </select>
        </label>

        <div className="limit-form-rows">
          {rows.map((row, index) => (
            <fieldset className="limit-form-row" key={`${row.windowId}-${index}`}>
              <legend>{row.label}</legend>
              <label>
                <span>Window label</span>
                <input value={row.label} onChange={(event) => updateRow(index, { label: event.target.value })} />
              </label>
              <label>
                <span>Status</span>
                <select
                  value={row.status}
                  onChange={(event) => updateRow(index, { status: event.target.value as CodexLimitWindowStatus })}
                >
                  <option value="available">Available</option>
                  <option value="limited">Limited</option>
                  <option value="unknown">Unknown</option>
                </select>
              </label>
              <label>
                <span>Remaining percent</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={row.remainingPercent}
                  disabled={row.status === "unknown"}
                  onChange={(event) => updateRow(index, { remainingPercent: event.target.value })}
                />
              </label>
              <label>
                <span>Reset datetime</span>
                <input
                  type="datetime-local"
                  value={row.resetAt}
                  onChange={(event) => updateRow(index, { resetAt: event.target.value })}
                />
              </label>
            </fieldset>
          ))}
        </div>

        <label>
          <span>Operator note</span>
          <textarea value={note} onChange={(event) => setNote(event.target.value)} />
        </label>

        {validationErrors.length > 0 ? (
          <div className="safe-error" role="alert">
            <AlertTriangle size={18} aria-hidden="true" />
            <span>{validationErrors.join(" ")}</span>
          </div>
        ) : (
          <div className="export-status" role="status">
            Preview ready - {rows.length} window{rows.length === 1 ? "" : "s"} will be saved atomically.
          </div>
        )}

        {saveState.state !== "idle" ? (
          <div className={saveState.state === "error" ? "safe-error" : "export-status"} role="status">
            <span>{saveState.message}</span>
          </div>
        ) : null}

        <div className="action-buttons">
          <button type="button" disabled={!canSave} onClick={() => void saveLimitRecord()}>
            <Save size={16} aria-hidden="true" />
            Save limit record
          </button>
        </div>
      </form>
    </section>
  );
}

function LimitMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function rowsFromSnapshot(snapshot: CodexLimitsSnapshot, mode: CodexLimitPlanMode): LimitFormRow[] {
  const windows = snapshot.windows.length > 0 ? snapshot.windows : snapshot.latest_record?.windows ?? [];
  if (windows.length === 0) {
    return defaultRows(mode);
  }
  return normalizeRowsForMode(
    windows.map((limitWindow, index) => {
      const remaining = limitWindow.remainingPercent ?? limitWindow.remaining_percent;
      return {
        windowId: limitWindow.window_id || (index === 0 ? "agentic_pool" : `window_${index + 1}`),
        label: limitWindow.label || (index === 0 ? "Current plan" : `Window ${index + 1}`),
        status: normalizeStatus(limitWindow.status),
        remainingPercent: remaining === null || remaining === undefined ? "" : String(remaining),
        resetAt: toDateTimeLocalValue(limitWindow.resetsAt ?? limitWindow.reset_at ?? ""),
        authoritative: index === 0
      };
    }),
    mode
  );
}

function defaultRows(mode: CodexLimitPlanMode): LimitFormRow[] {
  const one: LimitFormRow = {
    windowId: "agentic_pool",
    label: "Current plan",
    status: "available",
    remainingPercent: "",
    resetAt: "",
    authoritative: true
  };
  if (mode === "single_pool") {
    return [one];
  }
  return [
    { ...one, windowId: "short", label: "Short window" },
    {
      windowId: "broad",
      label: "Broad quota",
      status: "available",
      remainingPercent: "",
      resetAt: "",
      authoritative: false
    }
  ];
}

function normalizeRowsForMode(rows: LimitFormRow[], mode: CodexLimitPlanMode): LimitFormRow[] {
  if (mode === "single_pool") {
    const first = rows[0] ?? defaultRows("single_pool")[0];
    return [{ ...first, windowId: first.windowId || "agentic_pool", label: first.label || "Current plan", authoritative: true }];
  }
  const defaults = defaultRows("dual_window");
  return [0, 1].map((index) => ({
    ...defaults[index],
    ...(rows[index] ?? {}),
    authoritative: index === 0
  }));
}

function validateRows(rows: LimitFormRow[]): string[] {
  return rows.flatMap((row) => {
    const errors: string[] = [];
    if (!row.label.trim()) {
      errors.push("Window label is required.");
    }
    if (row.status !== "unknown") {
      const value = Number(row.remainingPercent);
      if (!row.remainingPercent || !Number.isInteger(value) || value < 0 || value > 100) {
        errors.push(`${row.label || "Window"} needs a remaining percent from 0 to 100.`);
      }
      if (!row.resetAt) {
        errors.push(`${row.label || "Window"} needs a reset datetime.`);
      }
    }
    return errors;
  });
}

function normalizePlanMode(value?: string): CodexLimitPlanMode {
  return value === "dual_window" || value === "dynamic" ? value : "single_pool";
}

function normalizeStatus(value?: string): CodexLimitWindowStatus {
  if (value === "limited" || value === "unknown") {
    return value;
  }
  return "available";
}

function toDateTimeLocalValue(value: string): string {
  if (!value) {
    return "";
  }
  return value.replace("Z", "").slice(0, 16);
}

function toIsoLikeValue(value: string): string {
  if (!value) {
    return "";
  }
  return value.length === 16 ? `${value}:00Z` : value;
}

function formatLabel(value: string): string {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMaybeNumber(value?: number | null): string {
  return value === null || value === undefined ? "Unknown" : String(value);
}

function statusTone(value: string): string {
  if (value === "available" || value === "resume") {
    return "good";
  }
  if (value === "limited" || value === "wait" || value === "downgrade_model") {
    return "warn";
  }
  return "neutral";
}
