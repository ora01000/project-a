export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  mcp_servers: string[];
  mcp_status: Record<string, string>;
  status: string;
  operation_status: "working" | "idle" | "error";
  operation_error?: string | null;
  /** Brief label of current work while operation_status is working. */
  operation_detail?: string | null;
  is_system?: boolean;
  chat_enabled?: boolean;
}

export interface HealthInfo {
  status: string;
  runtime_status: string;
  mcp: Record<string, string>;
  agents: string[];
  agent_status?: Record<string, string>;
  runtime_mode?: "mock" | "http" | "local";
  runtime_capabilities?: RuntimeCapabilities;
}

export interface RuntimeCapabilities {
  invoke: boolean;
  planned_step: boolean;
  health_summary: boolean;
  agent_tools: boolean;
  reload_definitions: boolean;
  job_submission: boolean;
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
