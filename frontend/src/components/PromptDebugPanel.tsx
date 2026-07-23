import { useCallback, useEffect, useMemo, useState } from "react";

import type { AgentInfo } from "../types/agent";
import { ROLE_ADMIN } from "../types/user";
import { formatLocaleDateTime, toDatetimeLocalValue } from "../utils/datetime";

export interface PromptDebugEntry {
  idx: number;
  timestamp: string;
  kind?: "llm" | "orchestration";
  agent_id: string;
  agent_name: string;
  prompt: string;
  response?: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  job_idx?: number | null;
  caller_agent_id?: string | null;
  caller_agent_name?: string | null;
  step_index?: number | null;
}

interface PromptDebugPanelProps {
  agents: AgentInfo[];
  viewerRole: number;
}

interface TokenUsageRow {
  agent_id: string;
  agent_name: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  call_count?: number | null;
}

type AgentFilterId = "all" | string;

interface FilterOption {
  id: AgentFilterId;
  label: string;
}

interface PromptMessage {
  role: string;
  content: string;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return formatLocaleDateTime(date, {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatTokenCount(value: number): string {
  return value.toLocaleString("ko-KR");
}

function parsePromptMessages(prompt: string): PromptMessage[] {
  const trimmed = prompt.trim();
  if (!trimmed) {
    return [];
  }

  const parts = trimmed.split(/\n\n(?=\[)/);
  const messages: PromptMessage[] = [];
  for (const part of parts) {
    const match = part.match(/^\[([^\]]+)\]\n?([\s\S]*)$/);
    if (match) {
      messages.push({ role: match[1].toLowerCase(), content: match[2].trim() });
    } else {
      messages.push({ role: "message", content: part.trim() });
    }
  }
  return messages;
}

function roleLabel(role: string): string {
  switch (role) {
    case "system":
      return "system";
    case "human":
    case "user":
      return "user";
    case "ai":
    case "assistant":
      return "assistant";
    case "tool":
      return "tool";
    case "orchestration":
      return "orchestration";
    default:
      return role;
  }
}

function bubbleClass(role: string): string {
  const normalized = roleLabel(role);
  if (normalized === "user") {
    return "ml-8 border-sky-800/50 bg-sky-950/40 text-sky-50";
  }
  if (normalized === "assistant") {
    return "mr-8 border-emerald-800/50 bg-emerald-950/30 text-emerald-50";
  }
  if (normalized === "system") {
    return "border-amber-800/40 bg-amber-950/25 text-amber-50";
  }
  if (normalized === "orchestration") {
    return "border-violet-800/50 bg-violet-950/30 text-violet-50";
  }
  return "border-slate-700 bg-slate-900/80 text-slate-200";
}

function filterButtonClass(isSelected: boolean): string {
  const base = "rounded-md border px-2.5 py-1 text-xs font-medium transition";
  if (isSelected) {
    return `${base} border-sky-600 bg-sky-950/70 text-sky-100`;
  }
  return `${base} border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500 hover:bg-slate-700 hover:text-slate-100`;
}

function defaultPeriodSince(): string {
  return toDatetimeLocalValue(new Date(Date.now() - 24 * 60 * 60 * 1000));
}

function defaultPeriodUntil(): string {
  return toDatetimeLocalValue(new Date());
}

function EntryMeta({ entry }: { entry: PromptDebugEntry }) {
  const isOrchestration = entry.kind === "orchestration";
  return (
    <header className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-slate-800 pb-2 text-[11px] text-slate-400">
      <span
        className={`rounded-full border px-2 py-0.5 ${
          isOrchestration
            ? "border-violet-800/60 bg-violet-950/40 text-violet-200"
            : "border-sky-800/60 bg-sky-950/40 text-sky-200"
        }`}
      >
        {entry.agent_name}
      </span>
      {isOrchestration ? (
        <span className="rounded border border-violet-900/50 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-violet-300">
          orchestration
        </span>
      ) : (
        <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
          llm
        </span>
      )}
      <span className="font-mono text-slate-500">{entry.agent_id}</span>
      {entry.job_idx != null ? (
        <span className="font-mono text-amber-300/90">job#{entry.job_idx}</span>
      ) : null}
      {entry.step_index != null ? (
        <span className="font-mono text-slate-400">step {entry.step_index}</span>
      ) : null}
      {entry.caller_agent_name || entry.caller_agent_id ? (
        <span className="text-slate-400">
          caller {entry.caller_agent_name || entry.caller_agent_id}
          {entry.caller_agent_id && entry.caller_agent_name ? (
            <span className="font-mono text-slate-500"> ({entry.caller_agent_id})</span>
          ) : null}
        </span>
      ) : null}
      <span>{formatTimestamp(entry.timestamp)}</span>
      {(entry.input_tokens > 0 || entry.output_tokens > 0) && (
        <span>
          토큰 입력 {formatTokenCount(entry.input_tokens)} / 출력{" "}
          {formatTokenCount(entry.output_tokens)} (합계 {formatTokenCount(entry.total_tokens)})
        </span>
      )}
    </header>
  );
}

export function PromptDebugPanel({ agents, viewerRole }: PromptDebugPanelProps) {
  const isAdmin = viewerRole === ROLE_ADMIN;
  const [entries, setEntries] = useState<PromptDebugEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isClearing, setIsClearing] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<AgentFilterId>("all");
  const [cumulativeUsage, setCumulativeUsage] = useState<TokenUsageRow[]>([]);
  const [periodUsage, setPeriodUsage] = useState<TokenUsageRow[]>([]);
  const [periodSince, setPeriodSince] = useState(defaultPeriodSince);
  const [periodUntil, setPeriodUntil] = useState(defaultPeriodUntil);
  const [isLoadingPeriod, setIsLoadingPeriod] = useState(false);
  const [isResettingTokens, setIsResettingTokens] = useState(false);
  const [tokenMessage, setTokenMessage] = useState<string | null>(null);

  const filterOptions = useMemo((): FilterOption[] => {
    const regular = agents
      .filter((agent) => !agent.is_system)
      .map((agent) => ({ id: agent.id, label: agent.name }));
    const system = agents
      .filter((agent) => Boolean(agent.is_system))
      .map((agent) => ({ id: agent.id, label: agent.name }));

    const knownIds = new Set(agents.map((agent) => agent.id));
    const extras: FilterOption[] = [];
    const seenExtra = new Set<string>();
    for (const entry of entries) {
      if (!entry.agent_id || knownIds.has(entry.agent_id) || seenExtra.has(entry.agent_id)) {
        continue;
      }
      seenExtra.add(entry.agent_id);
      extras.push({ id: entry.agent_id, label: entry.agent_name || entry.agent_id });
    }

    return [{ id: "all", label: "전체" }, ...regular, ...system, ...extras];
  }, [agents, entries]);

  const filteredEntries = useMemo(() => {
    if (selectedAgentId === "all") {
      return entries;
    }
    return entries.filter((entry) => entry.agent_id === selectedAgentId);
  }, [entries, selectedAgentId]);

  const loadEntries = useCallback(async () => {
    try {
      const response = await fetch("/api/prompt-debug?limit=200");
      if (!response.ok) {
        throw new Error(await parseError(response, "프롬프트 디버그 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as PromptDebugEntry[];
      setEntries(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "프롬프트 디버그 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadCumulativeUsage = useCallback(async () => {
    try {
      const response = await fetch("/api/agents/token-usage");
      if (!response.ok) {
        throw new Error(await parseError(response, "누적 토큰 사용량을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as { agents: TokenUsageRow[] };
      setCumulativeUsage(data.agents ?? []);
    } catch (err) {
      setTokenMessage(err instanceof Error ? err.message : "누적 토큰 사용량을 불러오지 못했습니다.");
    }
  }, []);

  const loadPeriodUsage = useCallback(async () => {
    setIsLoadingPeriod(true);
    setTokenMessage(null);
    try {
      const params = new URLSearchParams();
      if (periodSince) {
        params.set("since", new Date(periodSince).toISOString());
      }
      if (periodUntil) {
        params.set("until", new Date(periodUntil).toISOString());
      }
      if (selectedAgentId !== "all") {
        params.set("agent_id", selectedAgentId);
      }
      const response = await fetch(`/api/agents/token-usage/period?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "기간별 토큰 사용량을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as { agents: TokenUsageRow[] };
      setPeriodUsage(data.agents ?? []);
    } catch (err) {
      setTokenMessage(
        err instanceof Error ? err.message : "기간별 토큰 사용량을 불러오지 못했습니다.",
      );
      setPeriodUsage([]);
    } finally {
      setIsLoadingPeriod(false);
    }
  }, [periodSince, periodUntil, selectedAgentId]);

  useEffect(() => {
    void loadEntries();
    void loadCumulativeUsage();
    const interval = window.setInterval(() => {
      void loadEntries();
      void loadCumulativeUsage();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [loadEntries, loadCumulativeUsage]);

  useEffect(() => {
    if (selectedAgentId === "all") {
      return;
    }
    const stillExists = filterOptions.some((option) => option.id === selectedAgentId);
    if (!stillExists) {
      setSelectedAgentId("all");
    }
  }, [filterOptions, selectedAgentId]);

  const handleClear = async () => {
    setIsClearing(true);
    try {
      const response = await fetch("/api/prompt-debug", { method: "DELETE" });
      if (!response.ok) {
        throw new Error(await parseError(response, "프롬프트 디버그 삭제에 실패했습니다."));
      }
      await loadEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "프롬프트 디버그 삭제에 실패했습니다.");
    } finally {
      setIsClearing(false);
    }
  };

  const handleResetCumulativeTokens = async () => {
    if (!isAdmin) {
      return;
    }
    setIsResettingTokens(true);
    setTokenMessage(null);
    try {
      const response = await fetch("/api/agents/token-usage/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ viewer_role: viewerRole }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "토큰 누적 초기화에 실패했습니다."));
      }
      const data = (await response.json()) as { cleared_agents: number };
      setTokenMessage(`누적 토큰을 초기화했습니다. (${data.cleared_agents}개 에이전트)`);
      await loadCumulativeUsage();
    } catch (err) {
      setTokenMessage(err instanceof Error ? err.message : "토큰 누적 초기화에 실패했습니다.");
    } finally {
      setIsResettingTokens(false);
    }
  };

  const renderUsageTable = (rows: TokenUsageRow[], emptyLabel: string) => {
    if (rows.length === 0) {
      return <p className="text-xs text-slate-500">{emptyLabel}</p>;
    }
    return (
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-left text-slate-400">
              <th className="px-2 py-1">에이전트</th>
              <th className="px-2 py-1">입력</th>
              <th className="px-2 py-1">출력</th>
              <th className="px-2 py-1">합계</th>
              <th className="px-2 py-1">호출</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.agent_id} className="border-b border-slate-800/80 text-slate-200">
                <td className="px-2 py-1">
                  <span className="font-medium">{row.agent_name}</span>
                  <span className="ml-1 font-mono text-[10px] text-slate-500">{row.agent_id}</span>
                </td>
                <td className="px-2 py-1 font-mono">{formatTokenCount(row.input_tokens)}</td>
                <td className="px-2 py-1 font-mono">{formatTokenCount(row.output_tokens)}</td>
                <td className="px-2 py-1 font-mono">{formatTokenCount(row.total_tokens)}</td>
                <td className="px-2 py-1 font-mono text-slate-400">
                  {row.call_count != null ? formatTokenCount(row.call_count) : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  if (isLoading) {
    return <p className="text-sm text-slate-500">프롬프트 디버그 데이터를 불러오는 중...</p>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-slate-500">
          LLM 교환과 시스템 에이전트 오케스트레이션을 최신순으로 표시합니다. (최대 200건)
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadEntries()}
            className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-800"
          >
            새로고침
          </button>
          <button
            type="button"
            onClick={() => void handleClear()}
            disabled={isClearing || entries.length === 0}
            className="rounded-md border border-rose-800 px-2.5 py-1 text-xs text-rose-200 hover:bg-rose-950/40 disabled:opacity-40"
          >
            비우기
          </button>
        </div>
      </div>

      <section className="shrink-0 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-semibold text-slate-200">토큰 사용량</h3>
          <div className="flex flex-wrap items-center gap-2">
            {isAdmin ? (
              <button
                type="button"
                onClick={() => void handleResetCumulativeTokens()}
                disabled={isResettingTokens}
                className="rounded-md border border-amber-800 px-2.5 py-1 text-xs text-amber-100 hover:bg-amber-950/40 disabled:opacity-40"
              >
                {isResettingTokens ? "초기화 중…" : "누적 초기화"}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void loadCumulativeUsage()}
              className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-800"
            >
              누적 새로고침
            </button>
          </div>
        </div>
        <p className="mb-2 text-[11px] text-slate-500">
          누적: 서버 기동 후 TokenTracker (에이전트 타일과 동일) · 기간: Prompt Debug LLM 기록 합산
        </p>
        {tokenMessage ? (
          <p className="mb-2 text-xs text-amber-200">{tokenMessage}</p>
        ) : null}
        <div className="mb-3">
          <p className="mb-1 text-[11px] font-medium text-slate-400">누적 (서버 기동 후)</p>
          {renderUsageTable(cumulativeUsage, "누적 토큰 사용 기록이 없습니다.")}
        </div>
        <div className="border-t border-slate-800 pt-3">
          <p className="mb-2 text-[11px] font-medium text-slate-400">기간별 조회 (LLM 교환)</p>
          <div className="mb-2 flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-0.5 text-[11px] text-slate-400">
              시작
              <input
                type="datetime-local"
                value={periodSince}
                onChange={(event) => setPeriodSince(event.target.value)}
                className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200"
              />
            </label>
            <label className="flex flex-col gap-0.5 text-[11px] text-slate-400">
              종료
              <input
                type="datetime-local"
                value={periodUntil}
                onChange={(event) => setPeriodUntil(event.target.value)}
                className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200"
              />
            </label>
            <button
              type="button"
              onClick={() => void loadPeriodUsage()}
              disabled={isLoadingPeriod}
              className="rounded-md border border-sky-700 bg-sky-950/40 px-2.5 py-1.5 text-xs text-sky-100 hover:bg-sky-900/50 disabled:opacity-40"
            >
              {isLoadingPeriod ? "조회 중…" : "기간 조회"}
            </button>
          </div>
          {renderUsageTable(
            periodUsage,
            "조건에 맞는 기간 LLM 토큰 기록이 없습니다. 기간 조회를 실행하세요.",
          )}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-1.5" role="list" aria-label="에이전트 필터">
        {filterOptions.map((option) => (
          <button
            key={option.id}
            type="button"
            role="listitem"
            onClick={() => setSelectedAgentId(option.id)}
            className={filterButtonClass(selectedAgentId === option.id)}
            title={option.id === "all" ? "전체 로그" : option.id}
          >
            {option.label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {filteredEntries.length === 0 ? (
        <div className="flex min-h-[120px] flex-1 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-950/40 text-sm text-slate-500">
          {entries.length === 0
            ? "표시할 항목이 없습니다. 에이전트 질의 또는 작업 요청/수행 시 여기에 기록됩니다."
            : "선택한 에이전트의 디버깅 로그가 없습니다."}
        </div>
      ) : (
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          {filteredEntries.map((entry) => {
            const isOrchestration = entry.kind === "orchestration";
            const messages = parsePromptMessages(entry.prompt);
            const response = entry.response?.trim() ?? "";
            return (
              <article
                key={entry.idx}
                className={`rounded-lg border px-3 py-2.5 shadow-sm ${
                  isOrchestration
                    ? "border-violet-900/60 bg-violet-950/20"
                    : "border-slate-700 bg-slate-950/50"
                }`}
              >
                <EntryMeta entry={entry} />

                <div className="space-y-2">
                  {messages.map((message, index) => (
                    <div
                      key={`${entry.idx}-${index}-${message.role}`}
                      className={`rounded-lg border px-3 py-2 ${bubbleClass(message.role)}`}
                    >
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide opacity-70">
                        {roleLabel(message.role)}
                      </div>
                      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
                        {message.content || "(empty)"}
                      </pre>
                    </div>
                  ))}
                  {response ? (
                    <div
                      className={`rounded-lg border px-3 py-2 ${
                        isOrchestration ? bubbleClass("orchestration") : bubbleClass("assistant")
                      }`}
                    >
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide opacity-70">
                        {isOrchestration ? "result" : "assistant"}
                      </div>
                      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
                        {response}
                      </pre>
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
