import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ReactNode } from "react";

import { bandLabel } from "../types/user";

interface ApproverJobSummary {
  idx: number;
  sr_num?: string | null;
  job_title: string;
  request_date: string;
  requester: string;
  request_depart: string;
  state: number;
  state_label: string;
  completion_request_date: string;
}

export interface WelcomeNoticeItem {
  idx: number;
  writer: string;
  writer_name: string;
  title: string;
  from_date: string;
  until_date: string;
  notice: string;
}

interface WelcomeBackModalProps {
  username: string;
  band?: number | null;
  previousLastLogin: string | null;
  notices: WelcomeNoticeItem[];
  jobs: ApproverJobSummary[];
  onClose: () => void;
}

const markdownComponents = {
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="mb-2 text-base font-bold text-slate-50">{children}</h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mb-1.5 mt-3 text-sm font-semibold text-slate-50">{children}</h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mb-1 mt-2 text-sm font-semibold text-slate-100">{children}</h3>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-1.5 text-slate-200">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="mb-2 list-disc space-y-0.5 pl-5">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="mb-2 list-decimal space-y-0.5 pl-5">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="text-slate-200">{children}</li>
  ),
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-slate-50">{children}</strong>
  ),
  code: ({ className, children }: { className?: string; children?: ReactNode }) =>
    className ? (
      <code className="block overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-200">
        {children}
      </code>
    ) : (
      <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs text-sky-200">
        {children}
      </code>
    ),
};

export function WelcomeBackModal({
  username,
  band,
  previousLastLogin,
  notices,
  jobs,
  onClose,
}: WelcomeBackModalProps) {
  const titleBand = bandLabel(band);
  const titleName = titleBand ? `${username} ${titleBand}` : username;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-back-title"
        className="flex h-[90vh] w-full max-w-[min(96rem,calc(100vw-2rem))] flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 id="welcome-back-title" className="text-lg font-semibold text-slate-100">
            Welcome back, {titleName} 님
          </h2>
          {previousLastLogin ? (
            <p className="text-right text-sm text-slate-300">
              최근 로그인: <span className="font-mono text-slate-200">{previousLastLogin}</span>
            </p>
          ) : null}
        </div>
        <p className="mt-2 text-sm text-slate-300">다시 오신 것을 환영합니다.</p>

        <div className="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
          <div className="flex max-h-[40%] min-h-0 shrink-0 flex-col overflow-hidden rounded-md border border-slate-700">
            <div className="shrink-0 border-b border-slate-700 bg-slate-800/80 px-3 py-2 text-xs font-medium text-slate-300">
              공지사항 ({notices.length})
            </div>
            {notices.length === 0 ? (
              <p className="p-4 text-sm text-slate-400">표시할 공지사항이 없습니다.</p>
            ) : (
              <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
                {notices.map((notice) => (
                  <article
                    key={notice.idx}
                    className="rounded-md border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-200"
                  >
                    <div className="flex flex-col gap-2">
                      <h3 className="block w-full rounded-md bg-slate-800 px-2.5 py-1.5 text-[17px] font-semibold text-slate-50">
                        {notice.title}
                      </h3>
                      <span className="text-xs text-slate-400">
                        작성자: {notice.writer_name || notice.writer}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-xs text-slate-400">
                      {notice.from_date} ~ {notice.until_date}
                    </p>
                    <div className="markdown-body mt-2 text-sm leading-relaxed">
                      {notice.notice.trim() ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                          {notice.notice}
                        </ReactMarkdown>
                      ) : (
                        <p className="text-slate-500">내용 없음</p>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-700">
            <div className="shrink-0 border-b border-slate-700 bg-slate-800/80 px-3 py-2 text-xs font-medium text-slate-300">
              승인자로 지정된 작업 ({jobs.length})
            </div>
            {jobs.length === 0 ? (
              <p className="p-4 text-sm text-slate-400">승인자로 지정된 작업이 없습니다.</p>
            ) : (
              <div className="min-h-0 flex-1 overflow-auto">
                <table className="min-w-full border-collapse text-left text-xs text-slate-200">
                  <thead className="sticky top-0 bg-slate-800">
                    <tr>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        SR 번호
                      </th>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        작업 제목
                      </th>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        기안 일시
                      </th>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        기안자
                      </th>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        진행 상태
                      </th>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        작업완료요청일
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((job) => (
                      <tr key={job.idx} className="odd:bg-slate-900/40 even:bg-slate-900/80">
                        <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2 font-mono text-sky-200">
                          {job.sr_num ?? "-"}
                        </td>
                        <td
                          className="max-w-[220px] truncate border-b border-slate-800 px-3 py-2"
                          title={job.job_title}
                        >
                          {job.job_title}
                        </td>
                        <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2 font-mono">
                          {job.request_date}
                        </td>
                        <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2">
                          {job.request_depart}/{job.requester}
                        </td>
                        <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2">
                          <span className="rounded border border-slate-600 bg-slate-950/50 px-1.5 py-0.5 text-[11px] text-sky-200">
                            {job.state}: {job.state_label}
                          </span>
                        </td>
                        <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2 font-mono">
                          {job.completion_request_date}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 flex shrink-0 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
