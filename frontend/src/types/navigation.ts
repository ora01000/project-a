export type AppView =
  | "dashboard"
  | "agent-list"
  | "inventory-csv"
  | "user-list"
  | "agent-assignment";

export type AgentSubMenu = "agent-list" | "inventory-csv";

export type UserManagementSubMenu = "user-list" | "agent-assignment";
