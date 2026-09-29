import { formatLocaleDateTime } from "../utils/datetime";

export const WHATAP_EVENT_LOG_SOURCE = "whatap-events";

export interface AgentLogEntry {
  timestamp: string;
  agent_id: string;
  user_id?: string;
  user_name?: string;
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

export function logEntryUserLabel(entry: AgentLogEntry): string {
  const name = entry.user_name?.trim();
  if (name) {
    return name;
  }
  const userid = entry.user_id?.trim();
  if (userid) {
    return userid;
  }
  return "-";
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

export function formatLogEntryFullText(entry: AgentLogEntry): string {
  const lines: string[] = [];

  if (entry.event === "agent_operation_error") {
    if (entry.reason?.trim()) {
      lines.push(`오류: ${entry.reason.trim()}`);
    }
    if (entry.input_message?.trim()) {
      lines.push(`입력:\n${entry.input_message.trim()}`);
    }
  } else {
    if (entry.input_message?.trim()) {
      lines.push(`입력:\n${entry.input_message.trim()}`);
    }
    if (entry.output_message?.trim()) {
      lines.push(`출력:\n${entry.output_message.trim()}`);
    }
    if (entry.tools && entry.tools.length > 0) {
      const toolNames = entry.tools
        .map((tool) => tool.name.trim())
        .filter(Boolean)
        .join(", ");
      if (toolNames) {
        lines.push(`도구: ${toolNames}`);
      }
    }
  }

  if (lines.length === 0) {
    return "-";
  }
  return lines.join("\n\n");
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

export function agentLogEntryKey(entry: AgentLogEntry, index: number): string {
  return `${entry.timestamp}-${entry.agent_id}-${entry.user_id ?? ""}-${index}`;
}
