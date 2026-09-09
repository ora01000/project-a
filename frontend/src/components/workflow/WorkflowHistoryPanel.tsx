import { useCallback, useEffect, useState } from "react";

import { JobContentView } from "../jobs/JobContentView";
import { JOB_TYPE_WORKFLOW } from "../../types/job";

export interface WorkflowHistoryItem {
  idx: number;
  uuid: string;
  start_date: string;
  end_date: string;
  finish_success: boolean;
  result_file: string;
  user_idx?: number;
  username?: string;
}

interface WorkflowHistoryPanelProps {
  workflowUuid: string;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function parseHistoryDate(value: string | undefined): Date | null {
  const raw = (value || "").trim();
  if (!raw) {
    return null;
  }
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
}

function formatDurationLabel(startDate: string, endDate: string): string {
  const start = parseHistoryDate(startDate);
  const end = parseHistoryDate(endDate);
  if (!start || !end) {
    return "-";
  }
  const ms = end.getTime() - start.getTime();
  if (ms < 0) {
    return "-";
  }
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}시간 ${minutes}분 ${seconds}초`;
  }
  if (minutes > 0) {
    return `${minutes}분 ${seconds}초`;
  }
  return `${seconds}초`;
}

export function WorkflowHistoryPanel({ workflowUuid }: WorkflowHistoryPanelProps) {
  const [items, setItems] = useState<WorkflowHistoryItem[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [resultContent, setResultContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingResult, setIsLoadingResult] = useState(false);

  const loadHistory = useCallback(async () => {
    if (!workflowUuid) {
      setItems([]);
      setSelectedIdx(null);
      setResultContent("");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/workflows/${workflowUuid}/history`);
      if (!response.ok) {
        throw new Error(await parseError(response, "이력을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as WorkflowHistoryItem[];
      setItems(data);
      setSelectedIdx((current) => {
        if (current != null && data.some((row) => row.idx === current)) {
          return current;
        }
        return data[0]?.idx ?? null;
      });
    } catch (err) {
      setItems([]);
      setSelectedIdx(null);
      setResultContent("");
      setError(err instanceof Error ? err.message : "이력을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [workflowUuid]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (selectedIdx == null || !workflowUuid) {
      setResultContent("");
      return;
    }
    let cancelled = false;
    const load = async () => {
      setIsLoadingResult(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/workflows/${workflowUuid}/history/${selectedIdx}/result`,
        );
        if (!response.ok) {
          throw new Error(await parseError(response, "결과 파일을 불러오지 못했습니다."));
        }
        const payload = (await response.json()) as { content?: string };
        if (!cancelled) {
          setResultContent(payload.content || "");
        }
      } catch (err) {
        if (!cancelled) {
          setResultContent("");
          setError(err instanceof Error ? err.message : "결과 파일을 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingResult(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedIdx, workflowUuid]);

  return (
    <div className="flex min-h-0 flex-1 gap-3 overflow-hidden p-3">
      <aside className="flex w-[240px] shrink-0 flex-col border-r border-slate-700/80 pr-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="text-[11px] font-semibold text-slate-300">실행 이력</h4>
          <button
            type="button"
            onClick={() => void loadHistory()}
            className="rounded border border-slate-600 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800"
          >
            새로고침
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto">
          {isLoading ? <p className="text-[11px] text-slate-500">불러오는 중…</p> : null}
          {!isLoading && items.length === 0 ? (
            <p className="text-[11px] text-slate-500">완료된 실행 이력이 없습니다.</p>
          ) : null}
          {items.map((item) => {
            const selected = item.idx === selectedIdx;
            const endLabel = item.end_date || "-";
            const durationLabel = formatDurationLabel(item.start_date, item.end_date);
            const executorLabel = item.username || (item.user_idx ? `user#${item.user_idx}` : "-");
            return (
              <button
                key={item.idx}
                type="button"
                onClick={() => setSelectedIdx(item.idx)}
                className={`block w-full rounded-md border px-2 py-1.5 text-left text-[11px] ${
                  selected
                    ? "border-sky-600 bg-sky-950/50 text-sky-100"
                    : "border-slate-700 bg-slate-900/70 text-slate-200 hover:border-slate-500"
                }`}
              >
                <div className="truncate" title={endLabel}>
                  <span className="text-slate-500">종료시각</span> {endLabel}
                </div>
                <div className="mt-0.5 truncate text-[10px] text-slate-400" title={durationLabel}>
                  <span className="text-slate-500">소요시간</span> {durationLabel}
                </div>
                <div className="mt-0.5 flex items-center justify-between gap-2 text-[10px] text-slate-400">
                  <span>{item.finish_success ? "성공" : "실패"}</span>
                  <span className="min-w-0 truncate text-right" title={executorLabel}>
                    {executorLabel}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </aside>
      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <h4 className="mb-2 shrink-0 text-[11px] font-semibold text-slate-300">최종 결과</h4>
        {error ? <p className="mb-2 shrink-0 text-[11px] text-rose-300">{error}</p> : null}
        {isLoadingResult ? (
          <p className="text-[11px] text-slate-500">결과 불러오는 중…</p>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            {resultContent ? (
              <JobContentView content={resultContent} jobType={JOB_TYPE_WORKFLOW} />
            ) : (
              <p className="text-[11px] text-slate-500">이력을 선택하면 결과가 표시됩니다.</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
