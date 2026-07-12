export interface AgentRecord {
  idx: number;
  agent_id: string;
  name: string;
  role: string;
  system_prompt: string;
  mcp_server_keys: string[];
}

export interface AgentFormValues {
  agent_id: string;
  name: string;
  role: string;
  system_prompt: string;
  mcp_server_keys: string[];
}

export interface McpServerOption {
  key: string;
  enabled: boolean;
}

export const EMPTY_AGENT_FORM: AgentFormValues = {
  agent_id: "",
  name: "",
  role: "",
  system_prompt: "",
  mcp_server_keys: [],
};

export function formatMcpServerKeys(keys: string[]): string {
  return keys.length > 0 ? keys.join(", ") : "-";
}

export function truncateText(value: string, maxLength = 80): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...`;
}
