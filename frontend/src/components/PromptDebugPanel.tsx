import { useCallback, useEffect, useState } from "react";

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
  return date.toLocaleString("ko-KR", {
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

export function PromptDebugPanel() {
  const [entries, setEntries] = useState<PromptDebugEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isClearing, setIsClearing] = useState(false);

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

  useEffect(() => {
    void loadEntries();
    const interval = window.setInterval(() => {
      void loadEntries();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [loadEntries]);

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

      {error ? (
        <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {entries.length === 0 ? (
        <div className="flex min-h-[120px] flex-1 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-950/40 text-sm text-slate-500">
          표시할 항목이 없습니다. 에이전트 질의 또는 작업 요청/수행 시 여기에 기록됩니다.
        </div>
      ) : (
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          {entries.map((entry) => {
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
