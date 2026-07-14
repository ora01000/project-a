export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  mcp_servers: string[];
  mcp_status: Record<string, string>;
  status: string;
  operation_status: "working" | "idle" | "error";
  operation_error?: string | null;
  input_tokens: number;
  output_tokens: number;
  is_system?: boolean;
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

export interface IntegratedChatResponse {
  id: string;
  agentId: string;
  agentName: string;
  userContent: string;
  assistantContent: string;
  toolsUsed: ToolUsage[];
  createdAt: string;
}
