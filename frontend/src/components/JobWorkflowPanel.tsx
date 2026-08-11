import { useCallback, useEffect, useState } from "react";

import type { AuthUser } from "../types/auth";
import type { JobWorkflowItem } from "../types/jobWorkflow";
import {
  JOB_WORKFLOW_POLL_INTERVAL_MS,
  JOB_WORKFLOW_REFRESH_EVENT,
} from "../utils/jobWorkflowRefresh";
import { ListPaginationControls } from "./jobs/ListPaginationControls";
import { useClientPagination } from "./jobs/useClientPagination";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function formatStepMeta(timestamp: string | null | undefined, detail: string | undefined): string {
  const timeText = formatWorkflowTimestamp(timestamp);
  const detailText = (detail ?? "").trim();
  if (detailText) {
    return `${timeText} · ${detailText}`;
  }
  return timeText;
}

function formatWorkflowTimestamp(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().replace("T", " ");
  return normalized || "—";
}

const JOB_INFO_COLUMN_CLASS = "w-[12rem] shrink-0";
const STEP_COLUMN_CLASS = "w-[11.5rem] shrink-0";

function stepButtonClass(statusCode: number, isLast: boolean): string {
  const base =
    "block w-full rounded-md border px-3 py-1.5 text-center text-[11px] font-medium leading-tight whitespace-nowrap transition-colors";
  if (statusCode === 12) {
    return `${base} border-amber-700/80 bg-amber-950/50 text-amber-100`;
  }
  if (statusCode === 11) {
    return `${base} border-rose-700/80 bg-rose-950/50 text-rose-100`;
  }
  if (statusCode === 13) {
    return `${base} border-slate-600 bg-slate-900/80 text-slate-300`;
  }
  if (isLast) {
    return `${base} border-sky-600 bg-sky-950/50 text-sky-100`;
  }
  return `${base} border-slate-600 bg-slate-900/80 text-slate-200`;
}

interface JobWorkflowPanelProps {
  currentUser: AuthUser;
  active: boolean;
}

export function JobWorkflowPanel({ currentUser, active }: JobWorkflowPanelProps) {
  const [items, setItems] = useState<JobWorkflowItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadWorkflows = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setIsLoading(true);
      setError(null);
    }
    try {
      const response = await fetch("/api/jobs/workflow");
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 워크플로우를 불러오지 못했습니다."));
      }
      const data = (await response.json()) as JobWorkflowItem[];
      setItems(data);
      if (silent) {
        setError(null);
      }
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : "작업 워크플로우를 불러오지 못했습니다.");
        setItems([]);
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!active) {
      return;
    }
    void loadWorkflows();
    const interval = window.setInterval(() => {
      void loadWorkflows({ silent: true });
    }, JOB_WORKFLOW_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [active, loadWorkflows, currentUser.userid]);

  useEffect(() => {
    if (!active) {
      return;
    }
    const handleRefresh = () => {
      void loadWorkflows({ silent: true });
    };
    window.addEventListener(JOB_WORKFLOW_REFRESH_EVENT, handleRefresh);
    return () => window.removeEventListener(JOB_WORKFLOW_REFRESH_EVENT, handleRefresh);
  }, [active, loadWorkflows]);

  useEffect(() => {
    if (!active) {
      return;
    }
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void loadWorkflows({ silent: true });
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [active, loadWorkflows]);

  const {
    page,
    pageSize,
    totalPages,
    totalItems,
    pageItems,
    setPage,
    setPageSize,
  } = useClientPagination(items);

  if (!active) {
    return null;
  }

  if (isLoading) {
    return <p className="text-sm text-slate-500">작업 워크플로우를 불러오는 중...</p>;
  }

  if (error) {
    return <p className="text-sm text-rose-300">{error}</p>;
  }

  if (items.length === 0) {
    return <p className="text-sm text-slate-500">표시할 작업 워크플로우가 없습니다.</p>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
        {pageItems.map((item) => (
          <article
            key={item.idx}
            className="grid grid-cols-[12rem_1fr] items-center gap-x-3 rounded-lg border border-slate-700/80 bg-slate-950/40 px-3 py-2.5"
          >
            <div className={`${JOB_INFO_COLUMN_CLASS} flex flex-col gap-0.5 text-xs whitespace-nowrap text-slate-300`}>
              <span className="font-semibold text-slate-100">{item.srnum}</span>
              <span>요청자 {item.requester_name}</span>
            </div>

            <div className="flex min-w-0 items-center gap-1.5 overflow-x-auto">
              {item.steps.map((step, index) => {
                const isLast = index === item.steps.length - 1;
                return (
                  <div
                    key={`${item.idx}-${step.status_code}-${index}`}
                    className="flex shrink-0 items-center gap-1.5"
                  >
                    <div className={`${STEP_COLUMN_CLASS} flex shrink-0 flex-col items-center gap-0.5`}>
                      <span className={stepButtonClass(step.status_code, isLast)}>{step.label}</span>
                      <span className="w-full text-center text-[10px] whitespace-nowrap text-slate-500">
                        {formatStepMeta(step.timestamp, step.detail)}
                      </span>
                    </div>
                    {!isLast ? <span className="shrink-0 text-slate-600" aria-hidden>→</span> : null}
                  </div>
                );
              })}
            </div>
          </article>
        ))}
      </div>
      <ListPaginationControls
        layout="bar"
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        totalItems={totalItems}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
      />
    </div>
  );
}
