import type { JobPlanStep, JobRecord } from "../../types/job";

interface JobDetailModalProps {
  job: JobRecord;
  onClose: () => void;
}

function PlanFlowDiagram({ job, steps }: { job: JobRecord; steps: JobPlanStep[] }) {
  const nodes: { label: string; detail?: string }[] = [
    { label: "작업일시", detail: job.request_date },
  ];

  for (const step of steps) {
    nodes.push({
      label: step.agent_name ?? step.agent_id,
      detail: step.agent_id,
    });
    nodes.push({
      label: "호출도구",
      detail: step.tool_name ?? "-",
    });
    nodes.push({
      label: "도구 함수",
      detail: step.tool_params ? JSON.stringify(step.tool_params) : "-",
    });
  }

  nodes.push({ label: "작업결과알림" });

  return (
    <div className="overflow-x-auto rounded-md border border-slate-700 bg-slate-950/50 p-4">
      <div className="flex min-w-max items-center gap-2">
        {nodes.map((node, index) => (
          <div key={`${node.label}-${index}`} className="flex items-center gap-2">
            <div className="rounded-md border border-sky-800/60 bg-sky-950/40 px-3 py-2 text-center">
              <div className="text-xs font-medium text-sky-200">{node.label}</div>
              {node.detail ? <div className="mt-1 max-w-[160px] truncate text-[10px] text-slate-400">{node.detail}</div> : null}
            </div>
            {index < nodes.length - 1 ? <span className="text-slate-500">→</span> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

export function JobDetailModal({ job, onClose }: JobDetailModalProps) {
  const plan = job.job_plan ?? { summary: "", steps: [] };
  const steps = plan.steps ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">작업 상세보기</h2>
            <p className="mt-1 text-sm text-slate-400">{job.job_title}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <div className="mt-4 space-y-4 text-sm text-slate-200">
          <section className="space-y-2">
            <h3 className="font-medium text-slate-300">작업 정보</h3>
            <div className="grid gap-2 rounded-md border border-slate-800 bg-slate-950/40 p-3 sm:grid-cols-2">
              <div>기안일시: {job.request_date}</div>
              <div>작업완료요청일시: {job.completion_request_date}</div>
              <div>기안자: {job.requester}</div>
              <div>기안자 조직: {job.request_depart}</div>
              <div>승인자: {job.approver}</div>
              <div>상태: {job.state_label}</div>
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="font-medium text-slate-300">작업 내용</h3>
            <p className="whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-950/40 p-3 text-slate-300">
              {job.job_description}
            </p>
          </section>

          <section className="space-y-2">
            <h3 className="font-medium text-slate-300">작업 계획</h3>
            <p className="rounded-md border border-slate-800 bg-slate-950/40 p-3 text-slate-300">
              {plan.summary || "등록된 계획 요약이 없습니다."}
            </p>
            {steps.length > 0 ? (
              <ul className="space-y-2">
                {steps.map((step, index) => (
                  <li
                    key={`${step.agent_id}-${index}`}
                    className="rounded-md border border-slate-800 bg-slate-950/40 p-3"
                  >
                    <div className="font-medium text-sky-200">
                      {index + 1}. {step.agent_name ?? step.agent_id}
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      도구: {step.tool_name ?? "-"}
                    </div>
                    <p className="mt-2 text-slate-300">{step.description ?? "-"}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <section className="space-y-2">
            <h3 className="font-medium text-slate-300">에이전트 호출 계획</h3>
            <PlanFlowDiagram job={job} steps={steps} />
          </section>

          {job.execution_result ? (
            <section className="space-y-2">
              <h3 className="font-medium text-slate-300">작업 수행 결과</h3>
              <p className="rounded-md border border-slate-800 bg-slate-950/40 p-3 text-slate-300">
                {job.execution_result.summary || "-"}
              </p>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
