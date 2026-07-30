export type AppView =
  | "dashboard"
  | "token-management"
  | "user-list"
  | "agent-assignment"
  | "agent-connections"
  | "notice-board";

export type AgentSubMenu = "agent-assignment" | "agent-connections" | "token-management";

export type UserManagementSubMenu = "user-list";
