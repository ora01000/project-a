interface ApproverJobSummary {
  idx: number;
  job_title: string;
  request_date: string;
  requester: string;
  request_depart: string;
  state: number;
  state_label: string;
  completion_request_date: string;
}

interface WelcomeBackModalProps {
  username: string;
  previousLastLogin: string | null;
  jobs: ApproverJobSummary[];
  onClose: () => void;
}

export function WelcomeBackModal({
  username,
  previousLastLogin,
  jobs,
  onClose,
}: WelcomeBackModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-back-title"
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="welcome-back-title" className="text-lg font-semibold text-slate-100">
          Welcome back, {username}
        </h2>
        <p className="mt-2 text-sm text-slate-300">
          다시 오신 것을 환영합니다.
          {previousLastLogin ? (
            <>
              {" "}
              이전 로그인: <span className="font-mono text-slate-200">{previousLastLogin}</span>
            </>
          ) : null}
        </p>

        <div className="mt-4 min-h-0 flex-1 overflow-hidden rounded-md border border-slate-700">
          <div className="border-b border-slate-700 bg-slate-800/80 px-3 py-2 text-xs font-medium text-slate-300">
            승인자로 지정된 작업 ({jobs.length})
          </div>
          {jobs.length === 0 ? (
            <p className="p-4 text-sm text-slate-400">승인자로 지정된 작업이 없습니다.</p>
          ) : (
            <div className="max-h-[50vh] overflow-auto">
              <table className="min-w-full border-collapse text-left text-xs text-slate-200">
                <thead className="sticky top-0 bg-slate-800">
                  <tr>
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
                      <td className="max-w-[220px] truncate border-b border-slate-800 px-3 py-2" title={job.job_title}>
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

        <div className="mt-5 flex justify-end">
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
