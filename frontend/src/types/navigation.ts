export type AppView =
  | "dashboard"
  | "agent-list"
  | "inventory-csv"
  | "token-management"
  | "job-list"
  | "job-create"
  | "user-list"
  | "agent-assignment"
  | "notice-board";

export type AgentSubMenu = "agent-list" | "inventory-csv" | "agent-assignment" | "token-management";

export type JobManagementSubMenu = "job-list" | "job-create";

export type UserManagementSubMenu = "user-list";
