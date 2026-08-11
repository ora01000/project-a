import { useCallback, useEffect, useMemo, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { JobRecord } from "../../types/job";
import type { JobResult } from "../../types/jobResult";
import { requestJobWorkflowRefresh } from "../../utils/jobWorkflowRefresh";
import { AssistantMessageContent } from "../AssistantMessageContent";
import { ConfirmDialog } from "../ConfirmDialog";
import { JobCancelReasonModal } from "./JobCancelReasonModal";
import { JobReportEmailModal } from "./JobReportEmailModal";
import { JobBlockField, JobInlineField } from "./JobFieldLabel";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function formatJobDate(value: string): string {
  const normalized = value.trim().replace("T", " ");
  if (!normalized) {
    return value;
  }
  return normalized;
}

function srnumButtonClass(isSelected: boolean, statusCode: number): string {
  if (isSelected) {
    return statusCode === 11
      ? "border-rose-600 bg-rose-950/60 text-rose-100"
      : "border-sky-600 bg-sky-950/60 text-sky-100";
  }
  if (statusCode === 11) {
    return "border-rose-800/80 bg-slate-900/80 text-rose-200 hover:border-rose-700 hover:bg-rose-950/40";
  }
  return "border-slate-600 bg-slate-900/80 text-slate-200 hover:border-slate-500 hover:bg-slate-800";
}

function statusLabel(statusCode: number): string {
  if (statusCode === 10) {
    return "처리 완료";
  }
  if (statusCode === 11) {
    return "처리 실패";
  }
  if (statusCode === 12) {
    return "작업 반려";
  }
  if (statusCode === 13) {
    return "작업 취소";
  }
  return `상태 ${statusCode}`;
}

function statusValueButtonClass(statusCode: number): string {
  if (statusCode === 11) {
    return "border-rose-700/80 bg-rose-950/70 text-rose-200";
  }
  if (statusCode === 12) {
    return "border-amber-700/80 bg-amber-950/70 text-amber-200";
  }
  if (statusCode === 13) {
    return "border-slate-600 bg-slate-900/80 text-slate-300";
  }
  return "border-emerald-700/80 bg-emerald-950/70 text-emerald-200";
}

interface MyJobResultsTabProps {
  active: boolean;
  currentUser: AuthUser;
  onCopyToNote: (content: string, noteName?: string) => Promise<void>;
}

export function MyJobResultsTab({ active, currentUser, onCopyToNote }: MyJobResultsTabProps) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [jobResult, setJobResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingResult, setIsLoadingResult] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCopyingToNote, setIsCopyingToNote] = useState(false);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailSuccess, setEmailSuccess] = useState<string | null>(null);
  const [confirmReworkOpen, setConfirmReworkOpen] = useState(false);
  const [cancelModalOpen, setCancelModalOpen] = useState(false);

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        min_status_code: "10",
        approver: currentUser.userid,
        exclude_status_code: "13",
      });
      const response = await fetch(`/api/jobs?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 결과 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as JobRecord[];
      setJobs(data);
      setSelectedIdx((current) => {
        if (current !== null && data.some((job) => job.idx === current)) {
          return current;
        }
        return data[0]?.idx ?? null;
      });
    } catch (err) {
      setJobs([]);
      setSelectedIdx(null);
      setError(err instanceof Error ? err.message : "작업 결과 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [currentUser.userid]);

  const loadJobResult = useCallback(async (jobIdx: number) => {
    setIsLoadingResult(true);
    setResultError(null);
    setJobResult(null);
    try {
      const response = await fetch(`/api/jobs/${jobIdx}/result`);
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 결과를 불러오지 못했습니다."));
      }
      const data = (await response.json()) as JobResult;
      setJobResult(data);
    } catch (err) {
      setJobResult(null);
      setResultError(err instanceof Error ? err.message : "작업 결과를 불러오지 못했습니다.");
    } finally {
      setIsLoadingResult(false);
    }
  }, []);

  useEffect(() => {
    if (!active) {
      return;
    }
    void loadJobs();
    const interval = window.setInterval(() => {
      void loadJobs();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [active, loadJobs]);

  const selectedJob = useMemo(
    () => jobs.find((job) => job.idx === selectedIdx) ?? null,
    [jobs, selectedIdx],
  );

  useEffect(() => {
    setConfirmReworkOpen(false);
    setCancelModalOpen(false);
    if (!active || selectedIdx === null) {
      setJobResult(null);
      setResultError(null);
      return;
    }
    void loadJobResult(selectedIdx);
  }, [active, selectedIdx, loadJobResult]);

  const handleRework = async () => {
    if (!selectedJob) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${selectedJob.idx}/rework`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor_userid: currentUser.userid }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "재작업 요청에 실패했습니다."));
      }
      setConfirmReworkOpen(false);
      await loadJobs();
      requestJobWorkflowRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "재작업 요청에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async (dropReason: string) => {
    if (!selectedJob) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${selectedJob.idx}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor_userid: currentUser.userid,
          drop_reason: dropReason,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 취소에 실패했습니다."));
      }
      setCancelModalOpen(false);
      await loadJobs();
      requestJobWorkflowRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 취소에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopyToNote = async () => {
    if (!selectedJob || !jobResult) {
      return;
    }

    setIsCopyingToNote(true);
    setError(null);
    try {
      const noteName = `${selectedJob.srnum} 처리결과`.slice(0, 50);
      await onCopyToNote(jobResult.result, noteName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "노트 복사에 실패했습니다.");
    } finally {
      setIsCopyingToNote(false);
    }
  };

  return (
    <>
      <div className="flex min-h-0 flex-1 gap-3 p-3">
        <aside className="flex w-[148px] shrink-0 flex-col border-r border-slate-700/80 pr-3">
          <h3 className="mb-2 text-xs font-semibold text-slate-300">작업 목록</h3>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain">
            {isLoading && jobs.length === 0 ? (
              <p className="text-xs text-slate-500">불러오는 중...</p>
            ) : null}
            {!isLoading && jobs.length === 0 ? (
              <p className="text-xs text-slate-500">완료된 작업이 없습니다.</p>
            ) : null}
            {jobs.map((job) => {
              const isSelected = job.idx === selectedIdx;
              return (
                <button
                  key={job.idx}
                  type="button"
                  onClick={() => setSelectedIdx(job.idx)}
                  className={`block w-full rounded-full border px-2.5 py-1 text-left text-[11px] font-medium transition-colors ${srnumButtonClass(isSelected, job.status_code)}`}
                  title={`${job.job_title} (${statusLabel(job.status_code)})`}
                >
                  {job.srnum}
                </button>
              );
            })}
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-xs font-semibold text-slate-300">작업 결과</h3>
            {selectedJob && jobResult ? (
              <button
                type="button"
                onClick={() => {
                  setEmailSuccess(null);
                  setEmailModalOpen(true);
                }}
                className="shrink-0 rounded-md border border-slate-600 bg-slate-800/80 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700"
              >
                메일 전송
              </button>
            ) : null}
          </div>
          {emailSuccess ? <p className="mb-2 text-xs text-emerald-300">{emailSuccess}</p> : null}
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
          {!error && !selectedJob ? (
            <p className="text-sm text-slate-500">작업을 선택하면 결과가 표시됩니다.</p>
          ) : null}
          {selectedJob ? (
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div className="shrink-0 space-y-3">
                <JobInlineField label="작업 제목" bullet="📋" valueClassName="text-sm font-semibold text-slate-100">
                  {selectedJob.job_title}
                </JobInlineField>
                <JobInlineField label="상태" bullet="🏷️" valueClassName="">
                  <span
                    className={`inline-flex rounded-md border px-2.5 py-1 text-[11px] font-semibold shadow-sm ${statusValueButtonClass(selectedJob.status_code)}`}
                  >
                    {statusLabel(selectedJob.status_code)}
                  </span>
                </JobInlineField>
                <JobInlineField label="SR 번호" bullet="🔖">
                  {selectedJob.srnum}
                </JobInlineField>
              </div>

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
                {isLoadingResult ? (
                  <p className="text-sm text-slate-500">결과 불러오는 중...</p>
                ) : null}
                {!isLoadingResult && resultError ? (
                  <p className="text-sm text-rose-300">{resultError}</p>
                ) : null}
                {!isLoadingResult && jobResult ? (
                  <>
                    <JobInlineField label="완료 일시" bullet="🕐">
                      {formatJobDate(jobResult.complete_date)}
                    </JobInlineField>
                    <JobBlockField
                      label="처리 결과"
                      bullet="📊"
                      headerExtra={
                        <button
                          type="button"
                          disabled={isCopyingToNote}
                          onClick={() => void handleCopyToNote()}
                          className="shrink-0 rounded-md border border-slate-600 bg-slate-800/80 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {isCopyingToNote ? "복사 중..." : "노트로 복사"}
                        </button>
                      }
                    >
                      <div className="rounded-md border border-slate-700 bg-slate-950/60 p-3">
                        <AssistantMessageContent content={jobResult.result} />
                      </div>
                    </JobBlockField>
                  </>
                ) : null}
              </div>

              <div className="flex shrink-0 gap-2 border-t border-slate-700/80 pt-3">
                {selectedJob.status_code === 11 ? (
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => setCancelModalOpen(true)}
                    className="rounded-md border border-rose-700 bg-rose-950/60 px-3 py-1.5 text-sm font-medium text-rose-100 hover:bg-rose-900/70 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    작업취소
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => setConfirmReworkOpen(true)}
                  className="rounded-md border border-sky-700 bg-sky-950/60 px-3 py-1.5 text-sm font-medium text-sky-100 hover:bg-sky-900/70 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  재작업
                </button>
              </div>
            </div>
          ) : null}
        </section>
      </div>

      {confirmReworkOpen && selectedJob ? (
        <ConfirmDialog
          title="재작업"
          message={`${selectedJob.srnum} 작업을 재작업하시겠습니까? 승인 완료 상태로 되돌려 에이전트가 다시 처리합니다.`}
          confirmLabel="재작업"
          onConfirm={() => void handleRework()}
          onCancel={() => setConfirmReworkOpen(false)}
        />
      ) : null}
      {cancelModalOpen && selectedJob ? (
        <JobCancelReasonModal
          defaultReason={jobResult?.result ?? ""}
          onClose={() => setCancelModalOpen(false)}
          onSave={(reason) => void handleCancel(reason)}
        />
      ) : null}
      {emailModalOpen && selectedJob ? (
        <JobReportEmailModal
          subject={selectedJob.job_title}
          sendEndpoint={`/api/jobs/${selectedJob.idx}/send-report-email`}
          requester={{
            name: selectedJob.requester_name,
            email: selectedJob.requester_email,
            depart: selectedJob.requester_depart,
            madangId: selectedJob.madang_id,
          }}
          onClose={() => setEmailModalOpen(false)}
          onSent={(message) => setEmailSuccess(message)}
        />
      ) : null}
    </>
  );
}
