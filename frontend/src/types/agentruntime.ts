export interface AgentRuntimeRecord {
  idx: number;
  type: number;
  agent_name: string;
  agent_id: string;
  local_agent_id: string;
  description: string;
  registered_date: string;
  service_id: string;
}

export interface AgentRuntimeFormValues {
  type: number;
  agent_name: string;
  agent_id: string;
  local_agent_id: string;
  description: string;
  registered_date: string;
  service_id: string;
}

export const AGENTRUNTIME_TYPE_OPTIONS = [
  { value: 0, label: "목업 (0)" },
  { value: 1, label: "외부연동 (1)" },
] as const;

export function agentRuntimeTypeLabel(type: number): string {
  const option = AGENTRUNTIME_TYPE_OPTIONS.find((item) => item.value === type);
  return option ? option.label : String(type);
}

export function emptyAgentRuntimeForm(defaultType = 0): AgentRuntimeFormValues {
  return {
    type: defaultType,
    agent_name: "",
    agent_id: "",
    local_agent_id: "",
    description: "",
    registered_date: "",
    service_id: "prvops",
  };
}

export function agentRuntimeFormFromRecord(record: AgentRuntimeRecord): AgentRuntimeFormValues {
  return {
    type: record.type,
    agent_name: record.agent_name,
    agent_id: record.agent_id,
    local_agent_id: record.local_agent_id,
    description: record.description,
    registered_date: record.registered_date,
    service_id: record.service_id,
  };
}

export function assignableAgentId(record: AgentRuntimeRecord): string {
  return record.local_agent_id.trim() || record.agent_id;
}
