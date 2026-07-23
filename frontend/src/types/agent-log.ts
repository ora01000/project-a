import { formatLocaleDateTime } from "../utils/datetime";

export interface AgentLogEntry {
  timestamp: string;
  agent_id: string;
  event?: string;
  reason?: string;
  input_message?: string;
  output_message?: string;
  tools?: { name: string; mcp_server?: string | null }[];
}

export function logEntryType(entry: AgentLogEntry): string {
  if (entry.event === "agent_operation_error") {
    return "오류";
  }
  return "대화";
}

export function logEntrySummary(entry: AgentLogEntry): string {
  if (entry.event === "agent_operation_error") {
    return entry.reason ?? "알 수 없는 오류";
  }
  if (entry.output_message) {
    return entry.output_message;
  }
  if (entry.input_message) {
    return entry.input_message;
  }
  return "-";
}

export function formatLogTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return formatLocaleDateTime(date);
}

export function truncateLogText(value: string, maxLength = 120): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...`;
}
