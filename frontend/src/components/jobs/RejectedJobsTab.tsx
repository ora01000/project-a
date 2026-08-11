import { useCallback, useEffect, useMemo, useState } from "react";

import type { JobRecord } from "../../types/job";
import { JobBlockField, JobInlineField } from "./JobFieldLabel";
import { JobReportEmailModal } from "./JobReportEmailModal";
import { ListPaginationControls } from "./ListPaginationControls";
import { useClientPagination } from "./useClientPagination";

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
  if (isSelected) {
    return "border-amber-600 bg-amber-950/60 text-amber-100";
  }
  return "border-amber-800/80 bg-slate-900/80 text-amber-200 hover:border-amber-700 hover:bg-amber-950/40";
}

interface RejectedJobsTabProps {
  active: boolean;
}

export function RejectedJobsTab({ active }: RejectedJobsTabProps) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailSuccess, setEmailSuccess] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ status_code: "12" });
      const response = await fetch(`/api/jobs?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "반려된 작업 목록을 불러오지 못했습니다."));
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
      setError(err instanceof Error ? err.message : "반려된 작업 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
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

  const {
    page,
    pageSize,
    totalPages,
    totalItems,
    pageItems,
    setPage,
    setPageSize,
  } = useClientPagination(jobs);

  const rejectionReason = selectedJob?.drop_reason?.trim() || selectedJob?.reject_reason?.trim() || "";

  return (
    <>
    <div className="flex min-h-0 flex-1 gap-3 p-3">
      <aside className="flex w-[178px] shrink-0 flex-col border-r border-slate-700/80 pr-3">
        <h3 className="mb-2 text-xs font-semibold text-slate-300">작업 목록</h3>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain">
          {isLoading && jobs.length === 0 ? (
            <p className="text-xs text-slate-500">불러오는 중...</p>
          ) : null}
          {!isLoading && jobs.length === 0 ? (
            <p className="text-xs text-slate-500">반려된 작업이 없습니다.</p>
          ) : null}
          {pageItems.map((job) => {
            const isSelected = job.idx === selectedIdx;
            return (
              <button
                key={job.idx}
                type="button"
                onClick={() => setSelectedIdx(job.idx)}
                className={`block w-full rounded-full border px-2.5 py-1 text-center text-[11px] font-medium transition-colors ${srnumButtonClass(isSelected)}`}
                title={job.job_title}
              >
                {job.srnum}
              </button>
            );
          })}
        </div>
        <ListPaginationControls
          page={page}
          pageSize={pageSize}
          totalPages={totalPages}
          totalItems={totalItems}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold text-slate-300">작업 상세</h3>
          {selectedJob ? (
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
          <p className="text-sm text-slate-500">작업을 선택하면 상세 정보가 표시됩니다.</p>
        ) : null}
        {selectedJob ? (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
            <JobInlineField label="SR 번호" bullet="🔖">
              {selectedJob.srnum}
            </JobInlineField>
            <JobInlineField label="작업 제목" bullet="📋" valueClassName="text-sm font-semibold text-slate-100">
              {selectedJob.job_title}
            </JobInlineField>
            <JobInlineField label="요청자" bullet="👤">
              {selectedJob.requester_name}
            </JobInlineField>
            <JobInlineField label="요청 부서" bullet="🏢">
              {selectedJob.requester_depart}
            </JobInlineField>
            <JobInlineField label="요청 일시" bullet="🕐">
              {formatJobDate(selectedJob.request_date)}
            </JobInlineField>
            {selectedJob.approver?.trim() ? (
              <JobInlineField label="작업 승인자" bullet="✅">
                {selectedJob.approver}
              </JobInlineField>
            ) : null}
            <JobBlockField label="작업 내용" bullet="📝">
              <div
                className="job-content-html rounded-md border border-slate-700 bg-slate-950/60 p-3 text-sm text-slate-200"
                dangerouslySetInnerHTML={{ __html: selectedJob.job_content }}
              />
            </JobBlockField>
            <JobBlockField label="반려 사유" bullet="⛔">
              <div className="rounded-md border border-amber-700/80 bg-amber-950/40 p-3 text-sm text-amber-100">
                {rejectionReason || "반려 사유가 등록되지 않았습니다."}
              </div>
            </JobBlockField>
          </div>
        ) : null}
      </section>
    </div>

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
