import { useCallback, useEffect, useMemo, useState } from "react";

import type { AuthUser } from "../../types/auth";
import {
  JOB_TYPE_AX_INFRA,
  JOB_TYPE_SIGNUP,
  JOB_TYPE_WHATAP,
  JOB_TYPE_WORKFLOW,
  type JobRecord,
} from "../../types/job";
import type { JobResult } from "../../types/jobResult";
import type { UserRecord } from "../../types/user";
import { AssistantMessageContent } from "../AssistantMessageContent";
import { JobAiAuditCommentBlock } from "./JobAiAuditCommentBlock";
import { JobBlockField, JobInlineField } from "./JobFieldLabel";
import { JobContentView } from "./JobContentView";
import { ListPaginationControls } from "./ListPaginationControls";
import { useClientPagination } from "./useClientPagination";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function formatJobDate(value: string | null | undefined): string {
  const normalized = (value ?? "").trim().replace("T", " ");
  return normalized || "—";
}

function jobTypeLabel(jobType: number | undefined): string {
  if (jobType === JOB_TYPE_AX_INFRA) {
    return "작업요청서";
  }
  if (jobType === JOB_TYPE_WHATAP) {
    return "Whatap이벤트";
  }
  if (jobType === JOB_TYPE_WORKFLOW) {
    return "워크플로우승인";
  }
  if (jobType === JOB_TYPE_SIGNUP) {
    return "가입신청";
  }
  return jobType == null ? "—" : `유형 ${jobType}`;
}

const STATUS_FILTER_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: "전체" },
  { value: 0, label: "접수" },
  { value: 1, label: "승인자 지정" },
  { value: 2, label: "승인(직접)" },
  { value: 10, label: "처리 완료" },
  { value: 11, label: "처리 실패" },
  { value: 12, label: "반려" },
  { value: 13, label: "취소" },
];

function statusLabel(statusCode: number): string {
  return STATUS_FILTER_OPTIONS.find((option) => option.value === statusCode)?.label ?? `상태 ${statusCode}`;
}

function formatApproverLabel(
  approverUserid: string | null | undefined,
  usersByUserid: Map<string, UserRecord>,
): string {
  const userid = (approverUserid ?? "").trim();
  if (!userid) {
    return "—";
  }
  const user = usersByUserid.get(userid);
  if (!user) {
    return userid;
  }
  const depart = user.depart.trim();
  const name = user.username.trim();
  if (depart && name) {
    return `${name} ${depart}`;
  }
  return name || depart || userid;
}

function statusFilterButtonClass(isActive: boolean): string {
  return isActive
    ? "text-[11px] font-medium text-sky-300"
    : "text-[11px] font-medium text-slate-500 hover:text-slate-300";
}

type SortColumn = "job_type" | "status_code" | "requester_name" | "request_date";
type SortDirection = "asc" | "desc";
type RightPanelMode = "detail" | "audit";

function compareJobs(left: JobRecord, right: JobRecord, column: SortColumn): number {
  switch (column) {
    case "job_type":
      return (left.job_type ?? 0) - (right.job_type ?? 0);
    case "status_code":
      return left.status_code - right.status_code;
    case "requester_name": {
      const leftName = (left.requester_name || left.madang_id || "").trim();
      const rightName = (right.requester_name || right.madang_id || "").trim();
      return leftName.localeCompare(rightName, "ko");
    }
    case "request_date":
      return left.request_date.localeCompare(right.request_date);
    default:
      return 0;
  }
}

function sortIndicator(column: SortColumn, sortColumn: SortColumn | null, direction: SortDirection): string {
  if (sortColumn !== column) {
    return "";
  }
  return direction === "asc" ? " ↑" : " ↓";
}

function sortableHeaderClass(isActive: boolean): string {
  return `px-3 py-2 ${
    isActive ? "text-sky-300" : "text-slate-400 hover:text-slate-200"
  }`;
}

interface JobMgmtTabProps {
  active: boolean;
  currentUser: AuthUser;
}

export function JobMgmtTab({ active, currentUser }: JobMgmtTabProps) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [rightPanelMode, setRightPanelMode] = useState<RightPanelMode | null>(null);
  const [rightPanelIdx, setRightPanelIdx] = useState<number | null>(null);
  const [jobResult, setJobResult] = useState<JobResult | null>(null);
  const [isLoadingResult, setIsLoadingResult] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<number | null>(null);
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const filteredJobs = useMemo(() => {
    const filtered =
      statusFilter === null ? jobs : jobs.filter((job) => job.status_code === statusFilter);
    if (sortColumn === null) {
      return filtered;
    }
    const directionFactor = sortDirection === "asc" ? 1 : -1;
    return [...filtered].sort((left, right) => {
      const result = compareJobs(left, right, sortColumn);
      if (result !== 0) {
        return result * directionFactor;
      }
      return right.idx - left.idx;
    });
  }, [jobs, statusFilter, sortColumn, sortDirection]);

  const { page, pageSize, totalPages, totalItems, pageItems, setPage, setPageSize } =
    useClientPagination(filteredJobs);

  const usersByUserid = useMemo(
    () => new Map(users.map((user) => [user.userid, user])),
    [users],
  );

  const closeRightPanel = useCallback(() => {
    setRightPanelMode(null);
    setRightPanelIdx(null);
    setJobResult(null);
    setResultError(null);
    setIsLoadingResult(false);
  }, []);

  const openRightPanel = useCallback((mode: RightPanelMode, idx: number) => {
    setRightPanelMode(mode);
    setRightPanelIdx(idx);
  }, []);

  const toggleRightPanel = useCallback(
    (mode: RightPanelMode, idx: number) => {
      if (rightPanelMode === mode && rightPanelIdx === idx) {
        closeRightPanel();
        return;
      }
      openRightPanel(mode, idx);
    },
    [closeRightPanel, openRightPanel, rightPanelIdx, rightPanelMode],
  );

  const loadJobs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/jobs");
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as JobRecord[];
      setJobs(data);
      setRightPanelIdx((current) => {
        if (current === null) {
          return null;
        }
        const matched = data.find((job) => job.idx === current);
        if (!matched) {
          setRightPanelMode(null);
          setJobResult(null);
          setResultError(null);
          return null;
        }
        return current;
      });
    } catch (err) {
      setJobs([]);
      closeRightPanel();
      setError(err instanceof Error ? err.message : "작업 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [closeRightPanel]);

  const loadUsers = useCallback(async () => {
    try {
      const response = await fetch("/api/users");
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as UserRecord[];
      setUsers(data);
    } catch {
      setUsers([]);
    }
  }, []);

  const loadJobResult = useCallback(async (jobIdx: number) => {
    setIsLoadingResult(true);
    setResultError(null);
    setJobResult(null);
    try {
      const response = await fetch(`/api/jobs/${jobIdx}/result`);
      if (response.status === 404) {
        setJobResult(null);
        return;
      }
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
      closeRightPanel();
      return;
    }
    void loadJobs();
    void loadUsers();
  }, [active, closeRightPanel, loadJobs, loadUsers, currentUser.userid, currentUser.role]);

  useEffect(() => {
    if (!active || rightPanelMode !== "detail" || rightPanelIdx === null) {
      if (rightPanelMode !== "detail") {
        setJobResult(null);
        setResultError(null);
        setIsLoadingResult(false);
      }
      return;
    }
    void loadJobResult(rightPanelIdx);
  }, [active, rightPanelMode, rightPanelIdx, loadJobResult]);

  const panelJob = useMemo(() => {
    if (rightPanelIdx === null) {
      return null;
    }
    return jobs.find((job) => job.idx === rightPanelIdx) ?? null;
  }, [rightPanelIdx, jobs]);

  const handleStatusFilterChange = (value: number | null) => {
    setStatusFilter(value);
    setPage(1);
  };

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
    setPage(1);
  };

  if (isLoading && jobs.length === 0) {
    return <p className="text-sm text-slate-500">작업 목록을 불러오는 중...</p>;
  }

  if (error) {
    return (
      <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
        {error}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="mb-2 flex shrink-0 items-center justify-end gap-2 overflow-x-auto">
        {STATUS_FILTER_OPTIONS.map((option) => {
          const isActive = statusFilter === option.value;
          return (
            <button
              key={option.label}
              type="button"
              onClick={() => handleStatusFilterChange(option.value)}
              className={statusFilterButtonClass(isActive)}
              aria-pressed={isActive}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      {filteredJobs.length === 0 ? (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-950/40 text-sm text-slate-500">
          {jobs.length === 0 ? "표시할 작업이 없습니다." : "선택한 상태에 해당하는 작업이 없습니다."}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-3 overflow-hidden">
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-slate-400">
                  <th className="px-3 py-2">SR</th>
                  <th className={sortableHeaderClass(sortColumn === "job_type")}>
                    <button
                      type="button"
                      onClick={() => handleSort("job_type")}
                      className="inline-flex items-center gap-0.5 font-medium"
                      aria-sort={
                        sortColumn === "job_type"
                          ? sortDirection === "asc"
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                    >
                      유형{sortIndicator("job_type", sortColumn, sortDirection)}
                    </button>
                  </th>
                  <th className={sortableHeaderClass(sortColumn === "status_code")}>
                    <button
                      type="button"
                      onClick={() => handleSort("status_code")}
                      className="inline-flex items-center gap-0.5 font-medium"
                      aria-sort={
                        sortColumn === "status_code"
                          ? sortDirection === "asc"
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                    >
                      상태{sortIndicator("status_code", sortColumn, sortDirection)}
                    </button>
                  </th>
                  <th className="px-3 py-2">제목</th>
                  <th className={sortableHeaderClass(sortColumn === "requester_name")}>
                    <button
                      type="button"
                      onClick={() => handleSort("requester_name")}
                      className="inline-flex items-center gap-0.5 font-medium"
                      aria-sort={
                        sortColumn === "requester_name"
                          ? sortDirection === "asc"
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                    >
                      요청자{sortIndicator("requester_name", sortColumn, sortDirection)}
                    </button>
                  </th>
                  <th className="px-3 py-2">승인자</th>
                  <th className={sortableHeaderClass(sortColumn === "request_date")}>
                    <button
                      type="button"
                      onClick={() => handleSort("request_date")}
                      className="inline-flex items-center gap-0.5 font-medium"
                      aria-sort={
                        sortColumn === "request_date"
                          ? sortDirection === "asc"
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                    >
                      요청일{sortIndicator("request_date", sortColumn, sortDirection)}
                    </button>
                  </th>
                  <th className="px-3 py-2">AI검토</th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((job) => {
                  const hasAiAudit = (job.ai_audit_cnt ?? 0) > 0;
                  const isAuditOpen = rightPanelMode === "audit" && rightPanelIdx === job.idx;
                  const isDetailOpen = rightPanelMode === "detail" && rightPanelIdx === job.idx;
                  return (
                    <tr
                      key={job.idx}
                      onClick={() => toggleRightPanel("detail", job.idx)}
                      className={`cursor-pointer border-b border-slate-800 text-slate-200 hover:bg-slate-800/40 ${
                        isDetailOpen || isAuditOpen ? "bg-slate-800/60" : ""
                      }`}
                    >
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-300">
                        {job.srnum}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-300">
                        {jobTypeLabel(job.job_type)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-300">
                        {statusLabel(job.status_code)}
                      </td>
                      <td
                        className="max-w-[220px] truncate px-3 py-2 text-xs text-slate-200"
                        title={job.job_title}
                      >
                        {job.job_title}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-300">
                        {job.requester_name || job.madang_id || "—"}
                      </td>
                      <td
                        className="whitespace-nowrap px-3 py-2 text-xs text-slate-400"
                        title={job.approver?.trim() || undefined}
                      >
                        {formatApproverLabel(job.approver, usersByUserid)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">
                        {formatJobDate(job.request_date)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        {hasAiAudit ? (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              toggleRightPanel("audit", job.idx);
                            }}
                            className={`inline-flex h-5 items-center rounded border px-1.5 text-[10px] font-medium leading-none transition-colors ${
                              isAuditOpen
                                ? "border-violet-500 bg-violet-950/70 text-violet-50"
                                : "border-violet-700/80 bg-violet-950/40 text-violet-100 hover:border-violet-500 hover:bg-violet-950/60"
                            }`}
                          >
                            AI검토내용
                          </button>
                        ) : (
                          <span className="text-xs text-slate-600">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {panelJob && rightPanelMode ? (
            <aside className="flex min-h-0 w-[42%] shrink-0 flex-col border-l border-slate-700 pl-3">
              <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-slate-200">
                    {rightPanelMode === "audit" ? "AI 검토" : "작업 상세"} · {panelJob.srnum}
                  </p>
                  <p className="truncate text-[10px] text-slate-500" title={panelJob.job_title}>
                    {panelJob.job_title}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeRightPanel}
                  className="shrink-0 rounded-md border border-slate-600 bg-slate-900/80 px-2 py-1 text-[10px] text-slate-300 hover:border-slate-500 hover:bg-slate-800"
                  aria-label="패널 닫기"
                >
                  닫기
                </button>
              </div>

              {rightPanelMode === "audit" ? (
                <div className="min-h-0 flex-1 overflow-auto pr-1">
                  <JobAiAuditCommentBlock
                    comment={panelJob.ai_audit_comment}
                    auditCount={panelJob.ai_audit_cnt}
                    auditDate={panelJob.ai_audit_date}
                  />
                  {!panelJob.ai_audit_comment?.trim() ? (
                    <div className="rounded-md border border-dashed border-slate-700 bg-slate-950/40 px-3 py-4 text-xs text-slate-500">
                      AI 검토 내용이 없습니다.
                      {panelJob.ai_audit_date?.trim()
                        ? ` (검토일: ${formatJobDate(panelJob.ai_audit_date)})`
                        : null}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
                  <JobInlineField label="SR 번호" bullet="🔖">
                    {panelJob.srnum}
                  </JobInlineField>
                  <JobInlineField label="유형" bullet="🗂️">
                    {jobTypeLabel(panelJob.job_type)}
                  </JobInlineField>
                  <JobInlineField label="상태" bullet="🏷️">
                    {statusLabel(panelJob.status_code)}
                  </JobInlineField>
                  <JobInlineField
                    label="작업 제목"
                    bullet="📋"
                    valueClassName="text-sm font-semibold text-slate-100"
                  >
                    {panelJob.job_title}
                  </JobInlineField>
                  <JobInlineField label="요청자" bullet="👤">
                    {panelJob.requester_name || panelJob.madang_id || "—"}
                  </JobInlineField>
                  <JobInlineField label="요청자 이메일" bullet="✉️">
                    {panelJob.requester_email || "—"}
                  </JobInlineField>
                  <JobInlineField label="요청자 조직" bullet="🏢">
                    {panelJob.requester_depart || "—"}
                  </JobInlineField>
                  <JobInlineField label="승인자" bullet="✅">
                    {formatApproverLabel(panelJob.approver, usersByUserid)}
                  </JobInlineField>
                  <JobInlineField label="요청 일시" bullet="🕐">
                    {formatJobDate(panelJob.request_date)}
                  </JobInlineField>
                  <JobInlineField label="접수 일시" bullet="📥">
                    {formatJobDate(panelJob.received_at)}
                  </JobInlineField>
                  {panelJob.reject_reason?.trim() ? (
                    <JobBlockField label="반려 사유" bullet="⚠️">
                      <div className="rounded-md border border-amber-800/60 bg-amber-950/30 p-3 text-sm text-amber-100 whitespace-pre-wrap">
                        {panelJob.reject_reason.trim()}
                      </div>
                    </JobBlockField>
                  ) : null}
                  {panelJob.drop_reason?.trim() ? (
                    <JobBlockField label="취소 사유" bullet="⛔">
                      <div className="rounded-md border border-rose-800/60 bg-rose-950/30 p-3 text-sm text-rose-100 whitespace-pre-wrap">
                        {panelJob.drop_reason.trim()}
                      </div>
                    </JobBlockField>
                  ) : null}
                  <JobBlockField label="작업 내용" bullet="📝">
                    <JobContentView content={panelJob.job_content || ""} jobType={panelJob.job_type} />
                  </JobBlockField>

                  {isLoadingResult ? (
                    <p className="text-sm text-slate-500">결과 불러오는 중...</p>
                  ) : null}
                  {!isLoadingResult && resultError ? (
                    <p className="text-sm text-rose-300">{resultError}</p>
                  ) : null}
                  {!isLoadingResult && jobResult ? (
                    <>
                      <JobInlineField label="완료 일시" bullet="🏁">
                        {formatJobDate(jobResult.complete_date)}
                      </JobInlineField>
                      <JobBlockField label="처리 결과" bullet="📊">
                        <div className="rounded-md border border-slate-700 bg-slate-950/60 p-3">
                          <AssistantMessageContent content={jobResult.result} />
                        </div>
                      </JobBlockField>
                    </>
                  ) : null}
                </div>
              )}
            </aside>
          ) : null}
        </div>
      )}

      <ListPaginationControls
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        totalItems={totalItems}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        layout="bar"
      />
    </div>
  );
}
