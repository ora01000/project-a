import { useCallback, useEffect, useMemo, useState } from "react";

import { JobDetailModal } from "./JobDetailModal";
import type { JobDetailTab, JobRecord } from "../../types/job";
import { jobRequesterLabel } from "../../types/job";

interface JobWorkPanelProps {
  tab: JobDetailTab;
}

const ENDPOINTS: Record<JobDetailTab, string> = {
  review: "/api/jobs/review",
  pending: "/api/jobs/pending",
  completed: "/api/jobs/completed",
};

const EMPTY_MESSAGES: Record<JobDetailTab, string> = {
  review: "표시할 검토 작업이 없습니다.",
  pending: "표시할 보류 작업이 없습니다.",
  completed: "표시할 완료 작업이 없습니다.",
};

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function JobWorkPanel({ tab }: JobWorkPanelProps) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedIdxSet, setSelectedIdxSet] = useState<Set<number>>(new Set());
  const [detailJob, setDetailJob] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(ENDPOINTS[tab]);
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as JobRecord[];
      setJobs(data);
      setSelectedIdxSet((current) => {
        const valid = new Set(data.map((job) => job.idx));
        return new Set([...current].filter((idx) => valid.has(idx)));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const showReviewColumns = tab === "review";
  const isCompletedTab = tab === "completed";
  const emptyMessage = EMPTY_MESSAGES[tab];

  const selectedJobs = useMemo(
    () => jobs.filter((job) => selectedIdxSet.has(job.idx)),
    [jobs, selectedIdxSet],
  );

  const toggleRow = (idx: number) => {
    setSelectedIdxSet((current) => {
      const next = new Set(current);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIdxSet.size === jobs.length) {
      setSelectedIdxSet(new Set());
      return;
    }
    setSelectedIdxSet(new Set(jobs.map((job) => job.idx)));
  };

  const openDetail = async (job: JobRecord) => {
    try {
      const response = await fetch(`/api/jobs/${job.idx}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 상세를 불러오지 못했습니다."));
      }
      const data = (await response.json()) as JobRecord;
      setDetailJob(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 상세를 불러오지 못했습니다.");
    }
  };

  if (isLoading) {
    return <p className="text-sm text-slate-500">작업 목록을 불러오는 중...</p>;
  }

  if (error) {
    return (
      <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
        {error}
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="flex h-full min-h-[120px] items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-950/40 text-sm text-slate-500">
        {emptyMessage}
      </div>
    );
  }

  const detailButton = (job: JobRecord) => (
    <button
      type="button"
      onClick={() => void openDetail(job)}
      className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
    >
      상세보기
    </button>
  );

  return (
    <>
      <table className="min-w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-700 text-left text-slate-400">
            {isCompletedTab ? (
              <>
                <th className="px-3 py-2">작업 제목</th>
                <th className="px-3 py-2">기안 일시</th>
                <th className="px-3 py-2">기안 조직</th>
                <th className="px-3 py-2">기안자</th>
                <th className="px-3 py-2">상태</th>
                <th className="px-3 py-2">작업완료요청일</th>
                <th className="px-3 py-2">실제작업완료시간</th>
                <th className="px-3 py-2">상세보기</th>
              </>
            ) : (
              <>
                {showReviewColumns ? (
                  <th className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={jobs.length > 0 && selectedIdxSet.size === jobs.length}
                      onChange={toggleAll}
                      aria-label="전체 선택"
                    />
                  </th>
                ) : null}
                {showReviewColumns ? <th className="px-3 py-2">기안일시</th> : null}
                <th className="px-3 py-2">작업 제목</th>
                {showReviewColumns ? <th className="px-3 py-2">작업완료요청일시</th> : null}
                {showReviewColumns ? <th className="px-3 py-2">기안자 조직</th> : null}
                {showReviewColumns ? <th className="px-3 py-2">기안자 이름</th> : null}
                {!showReviewColumns ? <th className="px-3 py-2">상태</th> : null}
                <th className="px-3 py-2">상세보기</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) =>
            isCompletedTab ? (
              <tr key={job.idx} className="border-b border-slate-800 text-slate-200">
                <td className="px-3 py-2">{job.job_title}</td>
                <td className="px-3 py-2">{job.request_date}</td>
                <td className="px-3 py-2">{job.request_depart}</td>
                <td className="px-3 py-2">{jobRequesterLabel(job)}</td>
                <td className="px-3 py-2">{job.state_label}</td>
                <td className="px-3 py-2">{job.completion_request_date}</td>
                <td className="px-3 py-2">{job.actual_completion_time ?? "-"}</td>
                <td className="px-3 py-2">{detailButton(job)}</td>
              </tr>
            ) : (
              <tr key={job.idx} className="border-b border-slate-800 text-slate-200">
                {showReviewColumns ? (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selectedIdxSet.has(job.idx)}
                      onChange={() => toggleRow(job.idx)}
                      aria-label={`${job.job_title} 선택`}
                    />
                  </td>
                ) : null}
                {showReviewColumns ? <td className="px-3 py-2">{job.request_date}</td> : null}
                <td className="px-3 py-2">{job.job_title}</td>
                {showReviewColumns ? (
                  <td className="px-3 py-2">{job.completion_request_date}</td>
                ) : null}
                {showReviewColumns ? <td className="px-3 py-2">{job.request_depart}</td> : null}
                {showReviewColumns ? <td className="px-3 py-2">{jobRequesterLabel(job)}</td> : null}
                {!showReviewColumns ? <td className="px-3 py-2">{job.state_label}</td> : null}
                <td className="px-3 py-2">{detailButton(job)}</td>
              </tr>
            ),
          )}
        </tbody>
      </table>

      {selectedJobs.length > 0 ? (
        <p className="mt-3 text-xs text-slate-500">{selectedJobs.length}개 작업 선택됨</p>
      ) : null}

      {detailJob ? (
        <JobDetailModal
          job={detailJob}
          editable={tab === "review"}
          onClose={() => setDetailJob(null)}
          onJobUpdated={(updated) => {
            setDetailJob(updated);
            void loadJobs();
          }}
        />
      ) : null}
    </>
  );
}
