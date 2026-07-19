import { useCallback, useEffect, useMemo, useState } from "react";

import type { AuthUser } from "../../types/auth";
import { JOB_LIST_STATES, jobApproverLabel, jobRequesterLabel, type JobRecord } from "../../types/job";
import { ROLE_ADMIN } from "../../types/user";
import { JobDetailModal } from "./JobDetailModal";

interface JobListPageProps {
  user: AuthUser;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function JobListPage({ user }: JobListPageProps) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [detailJob, setDetailJob] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        viewer_role: String(user.role),
        viewer_userid: user.userid,
        viewer_username: user.username,
      });
      const response = await fetch(`/api/jobs?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as JobRecord[];
      setJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [user.role, user.userid, user.username]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const jobsByState = useMemo(() => {
    const grouped = new Map<number, JobRecord[]>();
    for (const entry of JOB_LIST_STATES) {
      grouped.set(entry.state, []);
    }
    for (const job of jobs) {
      const bucket = grouped.get(job.state);
      if (bucket) {
        bucket.push(job);
      }
    }
    return grouped;
  }, [jobs]);

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

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">작업 목록</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            상태별로 jobs 테이블을 조회합니다.{" "}
            {user.role === ROLE_ADMIN
              ? "관리자는 전체 작업을 볼 수 있습니다."
              : "기안자 또는 승인자인 작업만 표시됩니다."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadJobs()}
          className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
        >
          새로고침
        </button>
      </header>

      {error ? (
        <div className="mx-4 mt-4 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 space-y-6 overflow-auto p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">작업 목록을 불러오는 중...</p>
        ) : (
          JOB_LIST_STATES.map(({ state, label }) => {
            const stateJobs = jobsByState.get(state) ?? [];
            return (
              <section key={state} className="rounded-lg border border-slate-800 bg-slate-950/40">
                <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
                  <h3 className="text-sm font-medium text-slate-200">
                    {label}
                    <span className="ml-2 text-xs font-normal text-slate-500">
                      (state={state})
                    </span>
                  </h3>
                  <span className="text-xs text-slate-500">{stateJobs.length}건</span>
                </div>
                {stateJobs.length === 0 ? (
                  <p className="px-3 py-4 text-sm text-slate-500">해당 상태의 작업이 없습니다.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-sm">
                      <thead>
                        <tr className="border-b border-slate-800 text-left text-slate-400">
                          <th className="px-3 py-2">SR 번호</th>
                          <th className="px-3 py-2">기안일시</th>
                          <th className="px-3 py-2">작업 제목</th>
                          <th className="px-3 py-2">기안 조직</th>
                          <th className="px-3 py-2">기안자</th>
                          <th className="px-3 py-2">승인자</th>
                          <th className="px-3 py-2">완료요청일시</th>
                          <th className="px-3 py-2">상태</th>
                          <th className="px-3 py-2">상세</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stateJobs.map((job) => (
                          <tr key={job.idx} className="border-b border-slate-800/80 text-slate-200">
                            <td className="px-3 py-2 font-mono text-sky-200">
                              {job.sr_num ?? "-"}
                            </td>
                            <td className="px-3 py-2 whitespace-nowrap">{job.request_date}</td>
                            <td className="px-3 py-2">{job.job_title}</td>
                            <td className="px-3 py-2">{job.request_depart}</td>
                            <td className="px-3 py-2">{jobRequesterLabel(job)}</td>
                            <td className="px-3 py-2">{jobApproverLabel(job)}</td>
                            <td className="px-3 py-2 whitespace-nowrap">
                              {job.completion_request_date}
                            </td>
                            <td className="px-3 py-2">{job.state_label}</td>
                            <td className="px-3 py-2">
                              <button
                                type="button"
                                onClick={() => void openDetail(job)}
                                className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
                              >
                                상세보기
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            );
          })
        )}
      </div>

      {detailJob ? (
        <JobDetailModal
          job={detailJob}
          editable={false}
          onClose={() => setDetailJob(null)}
          onJobUpdated={(updated) => {
            setDetailJob(updated);
            void loadJobs();
          }}
        />
      ) : null}
    </div>
  );
}
