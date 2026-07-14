export type TopologyNodeKind = "agent" | "llm" | "mcp";

export interface TopologyNode {
  id: string;
  kind: TopologyNodeKind;
  label: string;
  status: string;
  isSystem?: boolean;
}

export interface TopologyEdge {
  id: string;
  from: string;
  to: string;
}

export interface TopologyFlow {
  id: string;
  from: string;
  to: string;
  startedAt: number;
}

export function agentNodeId(agentId: string): string {
  return `agent:${agentId}`;
}

export function mcpNodeId(serverId: string): string {
  return `mcp:${serverId}`;
}

export const LLM_NODE_ID = "llm";
