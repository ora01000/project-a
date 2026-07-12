import { useCallback, useEffect, useState } from "react";

import type { AgentLogEntry } from "../types/agent-log";
import {
  formatLogTimestamp,
  logEntrySummary,
  logEntryType,
  truncateLogText,
} from "../types/agent-log";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function AgentLogsPanel() {
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadLogs = useCallback(async () => {
    try {
      const response = await fetch("/api/agent-logs?limit=500");
      if (!response.ok) {
        throw new Error(await parseError(response, "에이전트 로그를 불러오지 못했습니다."));
      }
      const data = (await response.json()) as AgentLogEntry[];
      setLogs(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "에이전트 로그를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLogs();
    const interval = window.setInterval(() => {
      void loadLogs();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [loadLogs]);

  if (isLoading) {
    return <p className="text-sm text-slate-500">에이전트 로그를 불러오는 중...</p>;
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
        표시할 로그가 없습니다.
      </div>
    );
  }

  return (
    <table className="min-w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-slate-700 text-left text-slate-400">
          <th className="px-3 py-2">시간</th>
          <th className="px-3 py-2">에이전트</th>
          <th className="px-3 py-2">유형</th>
          <th className="px-3 py-2">내용</th>
        </tr>
      </thead>
      <tbody>
        {logs.map((entry, index) => {
          const summary = logEntrySummary(entry);
          const isError = entry.event === "agent_operation_error";
          return (
            <tr
              key={`${entry.timestamp}-${entry.agent_id}-${index}`}
              className="border-b border-slate-800 text-slate-200"
            >
              <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">
                {formatLogTimestamp(entry.timestamp)}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{entry.agent_id}</td>
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
              <td className="max-w-[420px] px-3 py-2 text-xs text-slate-300" title={summary}>
                {truncateLogText(summary.replace(/\s+/g, " ").trim())}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
