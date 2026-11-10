import { operatorProjectConfig } from "./operatorConfig";

export type AgentMessage = {
  id: string;
  message_type: string;
  status: string;
  priority?: string;
  source_role: string;
  target_role?: string;
  target_channel?: string;
  source_worker_id?: string;
  target_worker_id?: string;
  origin_actor?: string;
  created_at?: string;
  updated_at?: string;
  project_id: string;
  project_identity?: string;
  repository?: string;
  jira_project_key?: string;
  sprint_id?: string;
  sprint_name?: string;
  jira_issue_key?: string;
  assignment_id?: string;
  display_lane?: "automated" | "po_inbox_question" | "product_owner" | string;
  payload?: Record<string, unknown>;
  artifact_refs?: string[];
  linked_refs?: AgentMessageReference[];
  resume_gate?: {
    allowed?: boolean | null;
    reason?: string;
    blockers?: string[];
  };
};

export type AgentMessageReference = {
  kind: string;
  value: string;
};

export type AgentMessageGraphNode = {
  id: string;
  label: string;
  kind: string;
  status?: string;
};

export type AgentMessageGraphEdge = {
  source: string;
  target: string;
  label: string;
};

export type AgentMessageGraph = {
  nodes: AgentMessageGraphNode[];
  edges: AgentMessageGraphEdge[];
};

export type AgentMessageFilters = {
  projectId?: string;
  jiraIssueKey?: string;
  assignmentId?: string;
  role?: string;
  messageType?: string;
  status?: string;
};

export type AgentMessageCreateInput = {
  id?: string;
  message_type: string;
  project_id: string;
  project_name?: string;
  jira_project_key?: string;
  target_role?: string;
  target_channel?: string;
  target_worker_id?: string;
  jira_issue_key?: string;
  assignment_id?: string;
  sprint_id?: string;
  sprint_name?: string;
  subject?: string;
  body?: string;
  references?: string[];
  response_requested?: boolean;
  priority?: string;
};

export type AgentMessagesResult =
  | { state: "loaded"; items: AgentMessage[]; graph: AgentMessageGraph; filters: Record<string, string> }
  | { state: "empty"; items: []; graph: AgentMessageGraph; filters: Record<string, string> }
  | { state: "error"; message: string; items: []; graph: AgentMessageGraph; filters: Record<string, string> };

const emptyGraph: AgentMessageGraph = { nodes: [], edges: [] };

export async function listAgentMessages(filters: AgentMessageFilters = {}): Promise<AgentMessagesResult> {
  const query = new URLSearchParams();
  if (filters.projectId && filters.projectId !== "all") {
    query.set("project_id", filters.projectId);
  }
  if (filters.jiraIssueKey) {
    query.set("jira_issue_key", filters.jiraIssueKey);
  }
  if (filters.assignmentId) {
    query.set("assignment_id", filters.assignmentId);
  }
  if (filters.role && filters.role !== "all") {
    query.set("role", filters.role);
  }
  if (filters.messageType && filters.messageType !== "all") {
    query.set("message_type", filters.messageType);
  }
  if (filters.status && filters.status !== "all") {
    query.set("status", filters.status);
  }

  try {
    const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/agent-messages?${query.toString()}`);
    if (!response.ok) {
      return {
        state: "error",
        message: `Agent messages could not be loaded safely (${response.status}).`,
        items: [],
        graph: emptyGraph,
        filters: {}
      };
    }
    const data = (await response.json()) as {
      items?: AgentMessage[];
      graph?: Partial<AgentMessageGraph>;
      filters?: Record<string, string>;
    };
    const items = Array.isArray(data.items) ? data.items : [];
    const graph: AgentMessageGraph = {
      nodes: Array.isArray(data.graph?.nodes) ? data.graph.nodes : [],
      edges: Array.isArray(data.graph?.edges) ? data.graph.edges : []
    };
    const filtersOut = data.filters ?? {};
    return items.length > 0
      ? { state: "loaded", items, graph, filters: filtersOut }
      : { state: "empty", items: [], graph, filters: filtersOut };
  } catch (error) {
    return {
      state: "error",
      message: error instanceof Error ? error.message : "Agent messages could not be loaded safely.",
      items: [],
      graph: emptyGraph,
      filters: {}
    };
  }
}

export async function createAgentMessage(input: AgentMessageCreateInput): Promise<AgentMessage> {
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/agent-messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return readAgentMessageActionResponse(response, "Agent message could not be sent safely");
}

export async function acknowledgeAgentMessage(messageId: string): Promise<AgentMessage> {
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/agent-messages/${encodeURIComponent(messageId)}/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor: "po" })
  });
  return readAgentMessageActionResponse(response, "Agent message could not be acknowledged safely");
}

export async function consumeAgentMessage(messageId: string): Promise<AgentMessage> {
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/agent-messages/${encodeURIComponent(messageId)}/consume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor: "po" })
  });
  return readAgentMessageActionResponse(response, "Agent message could not be consumed safely");
}

export async function respondToAgentMessage(messageId: string, input: AgentMessageCreateInput): Promise<AgentMessage> {
  const response = await fetch(`${operatorProjectConfig.apiBaseUrl}/agent-messages/${encodeURIComponent(messageId)}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  return readAgentMessageActionResponse(response, "Agent response could not be saved safely");
}

async function readAgentMessageActionResponse(response: Response, errorPrefix: string): Promise<AgentMessage> {
  if (!response.ok) {
    throw new Error(`${errorPrefix} (${response.status}).`);
  }
  const data = (await response.json()) as { item?: AgentMessage };
  if (!data.item) {
    throw new Error(`${errorPrefix}: response was missing message data.`);
  }
  return data.item;
}
