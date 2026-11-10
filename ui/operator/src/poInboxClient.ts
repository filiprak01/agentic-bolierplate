import { operatorProjectConfig } from "./operatorConfig";

export type POInboxAuditEvent = {
  timestamp?: string;
  actor?: string;
  action?: string;
  note?: string;
};

export type POInboxOption = string | { label?: string; value?: string; description?: string };

export type POInboxItem = {
  id: string;
  composite_id?: string;
  source_item_id?: string;
  source_project_id?: string;
  message_type: string;
  status: string;
  title: string;
  message: string;
  agent_role?: string;
  agent_id?: string;
  jira_issue_key?: string;
  project_id?: string;
  project_name?: string;
  repository?: string;
  jira_project_key?: string;
  confluence_page_id?: string;
  context_pack_path?: string;
  business_impact?: string;
  recommendation?: string;
  options?: POInboxOption[];
  answer?: string;
  answered_at?: string;
  created_at?: string;
  audit?: POInboxAuditEvent[];
  project_identity?: string;
};

export type POInboxProject = {
  project_id?: string;
  project_name?: string;
  jira_project_key?: string;
  repository?: string;
};

export type POInboxProjectError = POInboxProject & {
  message: string;
};

export type POInboxFilters = {
  status?: string;
  projectId?: string;
  agentRole?: string;
  messageType?: string;
  jiraIssueKey?: string;
};

export type POInboxExportEnvelope = {
  schema_version: string;
  generated_at: string;
  scope: "project" | "all_projects";
  filters: Record<string, string>;
  project?: POInboxProject;
  items?: POInboxItem[];
  projects?: { project: POInboxProject; items: POInboxItem[] }[];
  errors?: POInboxProjectError[];
};

export type POInboxListResult =
  | { state: "loaded"; items: POInboxItem[]; projects: POInboxProject[]; projectErrors: POInboxProjectError[] }
  | { state: "empty"; items: []; projects: POInboxProject[]; projectErrors: POInboxProjectError[] }
  | { state: "error"; message: string; items: []; projects: []; projectErrors: [] };

export type POInboxAction = "answer" | "approve" | "reject" | "resolve";

export type POInboxActionDecision = {
  allowed: boolean;
  reason?: string;
};

export async function listOpenInboxItems(filters: POInboxFilters = {}): Promise<POInboxListResult> {
  try {
    const query = new URLSearchParams();
    const status = filters.status ?? "open";
    if (status && status !== "all") {
      query.set("status", status);
    }
    if (filters.projectId && filters.projectId !== "all") {
      query.set("project_id", filters.projectId);
    }
    if (filters.agentRole && filters.agentRole !== "all") {
      query.set("agent_role", filters.agentRole);
    }
    if (filters.messageType && filters.messageType !== "all") {
      query.set("message_type", filters.messageType);
    }
    if (filters.jiraIssueKey) {
      query.set("jira_issue_key", filters.jiraIssueKey);
    }
    const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/po-inbox?${query.toString()}`);
    if (!response.ok) {
      return {
        state: "error",
        message: `Inbox could not be loaded safely (${response.status}).`,
        items: [],
        projects: [],
        projectErrors: []
      };
    }
    const data = (await response.json()) as {
      items?: POInboxItem[];
      projects?: POInboxProject[];
      project_errors?: POInboxProjectError[];
    };
    const items = Array.isArray(data.items) ? data.items : [];
    const projects = Array.isArray(data.projects) ? data.projects : [];
    const projectErrors = Array.isArray(data.project_errors) ? data.project_errors : [];
    return items.length > 0
      ? { state: "loaded", items, projects, projectErrors }
      : { state: "empty", items: [], projects, projectErrors };
  } catch (error) {
    return {
      state: "error",
      message: error instanceof Error ? error.message : "Inbox could not be loaded safely.",
      items: [],
      projects: [],
      projectErrors: []
    };
  }
}

export async function readInboxItem(itemId: string): Promise<POInboxItem> {
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/po-inbox/${encodeURIComponent(itemId)}`);
  if (!response.ok) {
    throw new Error(`Inbox item could not be loaded safely (${response.status}).`);
  }
  const data = (await response.json()) as { item?: POInboxItem };
  if (!data.item) {
    throw new Error("Inbox item response was missing item data.");
  }
  return data.item;
}

export async function exportInboxItems(filters: POInboxFilters = {}): Promise<POInboxExportEnvelope> {
  const query = new URLSearchParams();
  const status = filters.status ?? "open";
  if (status && status !== "all") {
    query.set("status", status);
  }
  if (filters.projectId) {
    query.set("project_id", filters.projectId);
  }
  if (filters.agentRole && filters.agentRole !== "all") {
    query.set("agent_role", filters.agentRole);
  }
  if (filters.messageType && filters.messageType !== "all") {
    query.set("message_type", filters.messageType);
  }
  if (filters.jiraIssueKey) {
    query.set("jira_issue_key", filters.jiraIssueKey);
  }
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/po-inbox/export?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Inbox export could not be loaded safely (${response.status}).`);
  }
  return (await response.json()) as POInboxExportEnvelope;
}

export async function submitInboxAction(
  item: POInboxItem,
  action: POInboxAction,
  answer: string,
  actor = "po"
): Promise<POInboxItem> {
  const decision = canApplyInboxAction(item, action);
  if (!decision.allowed) {
    throw new Error(decision.reason ?? "This inbox action is not allowed.");
  }

  const itemKey = inboxItemKey(item);
  const response = await fetch(
    `${operatorProjectConfig.apiBaseUrl}/po-inbox/${encodeURIComponent(itemKey)}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action === "resolve" ? { actor, note: answer } : { actor, answer })
    }
  );
  if (!response.ok) {
    throw new Error(`Inbox action could not be saved safely (${response.status}).`);
  }
  const data = (await response.json()) as { item?: POInboxItem };
  if (!data.item) {
    throw new Error("Inbox action response was missing item data.");
  }
  return data.item;
}

export function canApplyInboxAction(
  item: Pick<POInboxItem, "message_type" | "status">,
  action: POInboxAction
): POInboxActionDecision {
  if (item.status !== "open") {
    return { allowed: false, reason: "Only open inbox items can be changed." };
  }

  if (action === "answer") {
    return item.message_type === "blocking_question" || item.message_type === "assumption"
      ? { allowed: true }
      : { allowed: false, reason: "Only blocking questions and assumptions can be answered." };
  }

  if (action === "approve" || action === "reject") {
    return item.message_type === "approval_request"
      ? { allowed: true }
      : { allowed: false, reason: "Only approval requests can be approved or rejected." };
  }

  if (action === "resolve") {
    return item.message_type === "fyi" || item.message_type === "assumption"
      ? { allowed: true }
      : { allowed: false, reason: "Only FYI and assumption items can be archived." };
  }

  return { allowed: false, reason: "Unsupported inbox action." };
}

export function formatInboxOption(option: POInboxOption): string {
  if (typeof option === "string") {
    return option;
  }
  return [option.label, option.value, option.description].filter(Boolean).join(" - ");
}

export function inboxProjectIdentity(item: POInboxItem): string {
  if (item.project_identity) {
    return item.project_identity;
  }
  if (item.project_name && item.jira_project_key) {
    return `${item.project_name} (${item.jira_project_key})`;
  }
  return item.project_name || item.jira_project_key || item.project_id || item.jira_issue_key || operatorProjectConfig.jiraProjectKey;
}

export function inboxItemKey(item: POInboxItem): string {
  return item.composite_id || item.id;
}

export function inboxProjectFilterKey(project: POInboxProject): string {
  return project.project_id || project.jira_project_key || "default";
}
