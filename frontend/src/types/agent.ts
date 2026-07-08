export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  mcp_servers: string[];
  mcp_status: Record<string, string>;
  status: string;
}

export interface HealthInfo {
  status: string;
  llm: string;
  mcp: Record<string, string>;
  agents: string[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ToolUsage {
  name: string;
  mcp_server?: string | null;
}

export interface ChatTurn {
  num: number;
  createdAt: string;
  userContent: string;
  assistantContent: string;
  toolsUsed: ToolUsage[];
}
