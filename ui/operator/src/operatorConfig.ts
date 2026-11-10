export type OperatorProjectConfig = {
  projectName: string;
  jiraProjectKey: string;
  apiBaseUrl: string;
  durableDataBoundary: string;
};

const publicEnv = import.meta.env;

export const operatorProjectConfig: OperatorProjectConfig = {
  projectName: publicEnv.VITE_AGENTIC_PROJECT_NAME ?? "Agentic Boilerplate",
  jiraProjectKey: publicEnv.VITE_AGENTIC_JIRA_PROJECT_KEY ?? "AGENT",
  apiBaseUrl: publicEnv.VITE_AGENTIC_API_BASE_URL ?? "http://127.0.0.1:8000",
  durableDataBoundary: "platform durable data only"
};
