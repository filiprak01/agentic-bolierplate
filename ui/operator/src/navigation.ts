import { Activity, FileClock, Inbox, ListChecks, MessageSquareText, Settings, Waypoints } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type OperatorRouteId =
  | "po-inbox"
  | "codex-limits"
  | "agent-status"
  | "logs"
  | "projects"
  | "agent-messages"
  | "settings";

export type OperatorRoute = {
  id: OperatorRouteId;
  label: string;
  description: string;
  icon: LucideIcon;
  stateLabel?: string;
};

export const operatorRoutes: OperatorRoute[] = [
  {
    id: "po-inbox",
    label: "PO Inbox",
    description: "Questions, approvals, rejections, and durable PO decisions.",
    icon: Inbox,
    stateLabel: "Open"
  },
  {
    id: "codex-limits",
    label: "Limits",
    description: "Latest short-window and broad Codex quota records.",
    icon: ListChecks,
    stateLabel: "Live"
  },
  {
    id: "agent-status",
    label: "Agent Status",
    description: "Worker roles, assignment state, and active project identity.",
    icon: Activity,
    stateLabel: "Runtime"
  },
  {
    id: "logs",
    label: "Logs",
    description: "Evidence, sprint records, and worker execution logs.",
    icon: FileClock,
    stateLabel: "Recent"
  },
  {
    id: "projects",
    label: "Projects",
    description: "Active project identity and future multi-project inbox routing.",
    icon: Waypoints,
    stateLabel: "Next"
  },
  {
    id: "agent-messages",
    label: "Agent Messages",
    description: "Structured handoffs, resume requests, and agent communication flow.",
    icon: MessageSquareText,
    stateLabel: "Live"
  },
  {
    id: "settings",
    label: "Settings",
    description: "Operator shell configuration and local runtime preferences.",
    icon: Settings,
    stateLabel: "Next"
  }
];
