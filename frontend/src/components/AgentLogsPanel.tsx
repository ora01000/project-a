import { useCallback, useEffect, useState } from "react";

import type { AuthUser } from "../types/auth";
import type { AgentLogEntry } from "../types/agent-log";
import {
  agentLogEntryKey,
  formatLogEntryFullText,
  formatLogTimestamp,
  logEntrySummary,
  logEntryType,
  logEntryUserLabel,
  truncateLogText,
} from "../types/agent-log";
import { AssistantMessageContent } from "./AssistantMessageContent";

type LogContentViewMode = "text" | "render";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function viewModeButtonClass(isActive: boolean): string {
  if (isActive) {
    return "border-sky-600 bg-sky-950/60 text-sky-100";
  }
  return "border-slate-600 bg-slate-900/80 text-slate-300 hover:border-slate-500 hover:bg-slate-800";
}

interface AgentLogsPanelProps {
  currentUser: AuthUser;
  agentId?: string;
  excludeAgentIds?: string[];
  emptyMessage?: string;
  loadingMessage?: string;
  errorMessage?: string;
}

export function AgentLogsPanel({
  currentUser,
  agentId,
  excludeAgentIds,
  emptyMessage = "표시할 로그가 없습니다.",
  loadingMessage = "에이전트 로그를 불러오는 중...",
  errorMessage = "에이전트 로그를 불러오지 못했습니다.",
}: AgentLogsPanelProps) {
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [contentViewMode, setContentViewMode] = useState<LogContentViewMode>("render");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const showAgentColumn = !agentId?.trim();

  const loadLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "500" });
      const normalizedAgentId = agentId?.trim();
      if (normalizedAgentId) {
        params.set("agent_id", normalizedAgentId);
      }
      if (excludeAgentIds && excludeAgentIds.length > 0) {
        params.set("exclude_agent_id", excludeAgentIds.join(","));
      }

      const response = await fetch(`/api/agent-logs?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, errorMessage));
      }
      const data = (await response.json()) as AgentLogEntry[];
      setLogs(data);
      setSelectedKey((current) => {
        if (current && data.some((entry, index) => agentLogEntryKey(entry, index) === current)) {
          return current;
        }
        return data.length > 0 ? agentLogEntryKey(data[0], 0) : null;
      });
      setError(null);
    } catch (err) {
      setLogs([]);
      setSelectedKey(null);
      setError(err instanceof Error ? err.message : errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [agentId, excludeAgentIds, errorMessage]);

  useEffect(() => {
    void loadLogs();
    const interval = window.setInterval(() => {
      void loadLogs();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [loadLogs, currentUser.userid]);

  const selectedEntry = logs.find((entry, index) => agentLogEntryKey(entry, index) === selectedKey) ?? null;
  const selectedFullText = selectedEntry ? formatLogEntryFullText(selectedEntry) : "";

  if (isLoading) {
    return <p className="text-sm text-slate-500">{loadingMessage}</p>;
  }

  if (error) {
    return (
      <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
        {error}
      </div>
    );
  }

  if (logs.length === 0) {
    return (
      <div className="flex h-full min-h-[120px] items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-950/40 text-sm text-slate-500">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 gap-3">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-left text-slate-400">
              <th className="px-3 py-2">시간</th>
              <th className="px-3 py-2">사용자</th>
              {showAgentColumn ? <th className="px-3 py-2">에이전트</th> : null}
              <th className="px-3 py-2">유형</th>
              <th className="px-3 py-2">내용</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((entry, index) => {
              const rowKey = agentLogEntryKey(entry, index);
              const summary = logEntrySummary(entry);
              const isError = entry.event === "agent_operation_error";
              const isSelected = rowKey === selectedKey;
              return (
                <tr
                  key={rowKey}
                  onClick={() => setSelectedKey(rowKey)}
                  className={`cursor-pointer border-b border-slate-800 text-slate-200 transition-colors ${
                    isSelected ? "bg-slate-800/80" : "hover:bg-slate-800/40"
                  }`}
                >
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">
                    {formatLogTimestamp(entry.timestamp)}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-300">{logEntryUserLabel(entry)}</td>
                  {showAgentColumn ? (
                    <td className="px-3 py-2 font-mono text-xs">{entry.agent_id}</td>
                  ) : null}
                  <td className="px-3 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] ${
                        isError
                          ? "border border-rose-700/60 bg-rose-950/40 text-rose-200"
                          : "border border-sky-700/60 bg-sky-950/40 text-sky-200"
                      }`}
                    >
                      {logEntryType(entry)}
                    </span>
                  </td>
                  <td className="max-w-[280px] px-3 py-2 text-xs text-slate-300" title={summary}>
                    {truncateLogText(summary.replace(/\s+/g, " ").trim())}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selectedEntry ? (
        <aside className="flex min-h-0 w-[42%] shrink-0 flex-col border-l border-slate-700 pl-3">
          <div className="mb-2 flex shrink-0 items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setContentViewMode("text")}
              className={`rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors ${viewModeButtonClass(contentViewMode === "text")}`}
            >
              텍스트
            </button>
            <button
              type="button"
              onClick={() => setContentViewMode("render")}
              className={`rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors ${viewModeButtonClass(contentViewMode === "render")}`}
            >
              렌더링
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-700 bg-slate-950/60 p-3">
            {contentViewMode === "text" ? (
              <pre className="whitespace-pre-wrap break-words text-xs text-slate-200">{selectedFullText}</pre>
            ) : (
              <div className="text-sm text-slate-200">
                <AssistantMessageContent content={selectedFullText} />
              </div>
            )}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
