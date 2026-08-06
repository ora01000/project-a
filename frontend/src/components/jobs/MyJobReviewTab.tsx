import { useCallback, useEffect, useMemo, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { JobRecord } from "../../types/job";
import { ConfirmDialog } from "../ConfirmDialog";
import { JobBlockField, JobInlineField } from "./JobFieldLabel";
import { JobAiReviewButton } from "./JobAiReviewButton";
import { JobRejectReasonModal } from "./JobRejectReasonModal";

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

function srnumButtonClass(isSelected: boolean): string {
  return isSelected
    ? "border-sky-600 bg-sky-950/60 text-sky-100"
    : "border-slate-600 bg-slate-900/80 text-slate-200 hover:border-slate-500 hover:bg-slate-800";
}

interface MyJobReviewTabProps {
  active: boolean;
  currentUser: AuthUser;
}

export function MyJobReviewTab({ active, currentUser }: MyJobReviewTabProps) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmApproveOpen, setConfirmApproveOpen] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [confirmRejectOpen, setConfirmRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        status_code: "1",
        approver: currentUser.userid,
      });
      const response = await fetch(`/api/jobs?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "검토 작업 목록을 불러오지 못했습니다."));
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
      setError(err instanceof Error ? err.message : "검토 작업 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [currentUser.userid]);

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
    setConfirmApproveOpen(false);
    setRejectModalOpen(false);
    setConfirmRejectOpen(false);
    setRejectReason("");
  }, [selectedIdx]);

  const handleApprove = async () => {
    if (!selectedJob) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${selectedJob.idx}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor_userid: currentUser.userid }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 승인에 실패했습니다."));
      }
      setConfirmApproveOpen(false);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 승인에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!selectedJob || !rejectReason.trim()) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${selectedJob.idx}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor_userid: currentUser.userid,
          drop_reason: rejectReason.trim(),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 반려에 실패했습니다."));
      }
      setConfirmRejectOpen(false);
      setRejectModalOpen(false);
      setRejectReason("");
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 반려에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
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
              <p className="text-xs text-slate-500">검토할 작업이 없습니다.</p>
            ) : null}
            {jobs.map((job) => {
              const isSelected = job.idx === selectedIdx;
              return (
                <button
                  key={job.idx}
                  type="button"
                  onClick={() => setSelectedIdx(job.idx)}
                  className={`block w-full rounded-full border px-2.5 py-1 text-left text-[11px] font-medium transition-colors ${srnumButtonClass(isSelected)}`}
                  title={job.job_title}
                >
                  {job.srnum}
                </button>
              );
            })}
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <h3 className="mb-2 text-xs font-semibold text-slate-300">작업 상세</h3>
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
          {!error && !selectedJob ? (
            <p className="text-sm text-slate-500">작업을 선택하면 상세 정보가 표시됩니다.</p>
          ) : null}
          {selectedJob ? (
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
                <JobInlineField label="작업 제목" bullet="📋" valueClassName="text-sm font-semibold text-slate-100">
                  {selectedJob.job_title}
                </JobInlineField>
                <JobInlineField label="요청자" bullet="👤">
                  {selectedJob.requester_name}
                </JobInlineField>
                <JobInlineField label="요청 일시" bullet="🕐">
                  {formatJobDate(selectedJob.request_date)}
                </JobInlineField>
                <JobBlockField label="작업 내용" bullet="📝">
                  <div
                    className="job-content-html rounded-md border border-slate-700 bg-slate-950/60 p-3 text-sm text-slate-200"
                    dangerouslySetInnerHTML={{ __html: selectedJob.job_content }}
                  />
                </JobBlockField>
                {selectedJob.ai_audit_comment?.trim() ? (
                  <JobBlockField label="AI 검토결과" bullet="🤖">
                    <div className="rounded-md border border-violet-800/60 bg-violet-950/30 p-3 text-sm text-violet-100">
                      {selectedJob.ai_audit_comment}
                    </div>
                  </JobBlockField>
                ) : null}
              </div>

              <div className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-700/80 pt-3">
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => setConfirmApproveOpen(true)}
                    className="rounded-md border border-emerald-700 bg-emerald-950/60 px-3 py-1.5 text-sm font-medium text-emerald-100 hover:bg-emerald-900/70 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    승인
                  </button>
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => setRejectModalOpen(true)}
                    className="rounded-md border border-rose-700 bg-rose-950/60 px-3 py-1.5 text-sm font-medium text-rose-100 hover:bg-rose-900/70 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    반려
                  </button>
                </div>
                <JobAiReviewButton
                  jobIdx={selectedJob.idx}
                  disabled={isSubmitting}
                  onError={setError}
                  onSuccess={() => void loadJobs()}
                />
              </div>
            </div>
          ) : null}
        </section>
      </div>

      {confirmApproveOpen && selectedJob ? (
        <ConfirmDialog
          title="작업 승인"
          message={`${selectedJob.srnum} 작업을 승인하시겠습니까?`}
          confirmLabel="승인"
          onConfirm={() => void handleApprove()}
          onCancel={() => setConfirmApproveOpen(false)}
        />
      ) : null}
      {rejectModalOpen ? (
        <JobRejectReasonModal
          onClose={() => setRejectModalOpen(false)}
          onSave={(reason) => {
            setRejectReason(reason);
            setRejectModalOpen(false);
            setConfirmRejectOpen(true);
          }}
        />
      ) : null}
      {confirmRejectOpen && selectedJob ? (
        <ConfirmDialog
          title="작업 반려"
          message={`${selectedJob.srnum} 작업을 반려하시겠습니까?`}
          confirmLabel="반려"
          onConfirm={() => void handleReject()}
          onCancel={() => {
            setConfirmRejectOpen(false);
            setRejectReason("");
          }}
        />
      ) : null}
    </>
  );
}
