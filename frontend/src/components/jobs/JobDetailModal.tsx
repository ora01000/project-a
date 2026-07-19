import { useEffect, useMemo, useState } from "react";

import type { JobPlan, JobPlanStep, JobRecord } from "../../types/job";
import { jobApproverLabel, jobRequesterLabel } from "../../types/job";
import { ConfirmDialog } from "../ConfirmDialog";

interface JobDetailModalProps {
  job: JobRecord;
  editable?: boolean;
  onClose: () => void;
  onJobUpdated?: (job: JobRecord) => void;
}

interface AgentOption {
  id: string;
  name: string;
  is_system?: boolean;
}

interface ToolOption {
  name: string;
  description: string;
}

function emptyStep(agent?: AgentOption): JobPlanStep {
  return {
    agent_id: agent?.id ?? "",
    agent_name: agent?.name ?? "",
    tool_name: "",
    tool_params: {},
    description: "",
  };
}

function clonePlan(plan: JobPlan | null | undefined): JobPlan {
  const source = plan ?? { summary: "", steps: [] };
  return {
    summary: source.summary ?? "",
    steps: (source.steps ?? []).map((step) => ({
      agent_id: step.agent_id,
      agent_name: step.agent_name,
      tool_name: step.tool_name,
      tool_params: step.tool_params ? { ...step.tool_params } : {},
      description: step.description ?? "",
    })),
  };
}

function PlanFlowDiagram({
  job,
  steps,
  editable,
  toolsByAgent,
  onToolChange,
}: {
  job: JobRecord;
  steps: JobPlanStep[];
  editable: boolean;
  toolsByAgent: Record<string, ToolOption[]>;
  onToolChange: (index: number, toolName: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-slate-700 bg-slate-950/50 p-4">
      <div className="flex min-w-max items-center gap-2">
        <div className="rounded-md border border-sky-800/60 bg-sky-950/40 px-3 py-2 text-center">
          <div className="text-xs font-medium text-sky-200">작업일시</div>
          <div className="mt-1 max-w-[160px] truncate text-[10px] text-slate-400">{job.request_date}</div>
        </div>

        {steps.map((step, index) => {
          const tools = toolsByAgent[step.agent_id] ?? [];
          const toolOptions =
            step.tool_name && !tools.some((tool) => tool.name === step.tool_name)
              ? [{ name: step.tool_name, description: "" }, ...tools]
              : tools;

          return (
            <div key={`flow-${step.agent_id}-${index}`} className="flex items-center gap-2">
              <span className="text-slate-500">→</span>
              <div className="rounded-md border border-sky-800/60 bg-sky-950/40 px-3 py-2 text-center">
                <div className="text-xs font-medium text-sky-200">{step.agent_name ?? step.agent_id}</div>
                <div className="mt-1 max-w-[160px] truncate text-[10px] text-slate-400">{step.agent_id}</div>
              </div>
              <span className="text-slate-500">→</span>
              <div className="rounded-md border border-sky-800/60 bg-sky-950/40 px-3 py-2 text-center">
                <div className="text-xs font-medium text-sky-200">호출도구</div>
                {editable ? (
                  <select
                    value={step.tool_name ?? ""}
                    onChange={(event) => onToolChange(index, event.target.value)}
                    className="mt-1 max-w-[180px] rounded border border-slate-700 bg-slate-950 px-1 py-0.5 text-[10px] text-slate-200 outline-none"
                  >
                    <option value="">도구 선택</option>
                    {toolOptions.map((tool) => (
                      <option key={tool.name} value={tool.name}>
                        {tool.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="mt-1 max-w-[160px] truncate text-[10px] text-slate-400">
                    {step.tool_name ?? "-"}
                  </div>
                )}
              </div>
              <span className="text-slate-500">→</span>
              <div className="rounded-md border border-sky-800/60 bg-sky-950/40 px-3 py-2 text-center">
                <div className="text-xs font-medium text-sky-200">도구 함수</div>
                <div className="mt-1 max-w-[160px] truncate text-[10px] text-slate-400">
                  {step.tool_params ? JSON.stringify(step.tool_params) : "-"}
                </div>
              </div>
            </div>
          );
        })}

        <span className="text-slate-500">→</span>
        <div className="rounded-md border border-sky-800/60 bg-sky-950/40 px-3 py-2 text-center">
          <div className="text-xs font-medium text-sky-200">작업결과알림</div>
        </div>
      </div>
    </div>
  );
}

export function JobDetailModal({
  job,
  editable = false,
  onClose,
  onJobUpdated,
}: JobDetailModalProps) {
  const originalBaseline = useMemo(
    () => clonePlan(job.original_job_plan ?? job.job_plan),
    [job.original_job_plan, job.job_plan],
  );
  const [draftPlan, setDraftPlan] = useState<JobPlan>(() => clonePlan(job.job_plan));
  const [appliedPlan, setAppliedPlan] = useState<JobPlan>(() => clonePlan(job.job_plan));
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [toolsByAgent, setToolsByAgent] = useState<Record<string, ToolOption[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showModifyConfirm, setShowModifyConfirm] = useState(false);

  const chatAgents = useMemo(
    () => agents.filter((agent) => !agent.is_system),
    [agents],
  );

  useEffect(() => {
    setDraftPlan(clonePlan(job.job_plan));
    setAppliedPlan(clonePlan(job.job_plan));
  }, [job.idx, job.job_plan]);

  useEffect(() => {
    let cancelled = false;
    const loadAgents = async () => {
      try {
        const response = await fetch("/api/agents");
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as AgentOption[];
        if (!cancelled) {
          setAgents(data);
        }
      } catch {
        // ignore catalog load failure; editing still works with existing step agents
      }
    };
    void loadAgents();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const agentIds = [
      ...new Set(
        [...(draftPlan.steps ?? []), ...(appliedPlan.steps ?? [])]
          .map((step) => step.agent_id)
          .filter((agentId) => Boolean(agentId)),
      ),
    ];

    const loadTools = async () => {
      const entries = await Promise.all(
        agentIds.map(async (agentId) => {
          try {
            const response = await fetch(`/api/agents/${encodeURIComponent(agentId)}/tools`);
            if (!response.ok) {
              return [agentId, [] as ToolOption[]] as const;
            }
            const tools = (await response.json()) as ToolOption[];
            return [agentId, tools] as const;
          } catch {
            return [agentId, [] as ToolOption[]] as const;
          }
        }),
      );
      if (!cancelled) {
        setToolsByAgent((current) => {
          const next = { ...current };
          for (const [agentId, tools] of entries) {
            next[agentId] = tools;
          }
          return next;
        });
      }
    };

    if (agentIds.length > 0) {
      void loadTools();
    }
    return () => {
      cancelled = true;
    };
  }, [draftPlan.steps, appliedPlan.steps]);

  const updateStep = (index: number, patch: Partial<JobPlanStep>) => {
    setDraftPlan((current) => ({
      ...current,
      steps: (current.steps ?? []).map((step, stepIndex) =>
        stepIndex === index ? { ...step, ...patch } : step,
      ),
    }));
  };

  const removeStep = (index: number) => {
    setDraftPlan((current) => ({
      ...current,
      steps: (current.steps ?? []).filter((_, stepIndex) => stepIndex !== index),
    }));
  };

  const insertStepBelow = (index: number) => {
    const defaultAgent = chatAgents[0];
    setDraftPlan((current) => {
      const nextSteps = [...(current.steps ?? [])];
      nextSteps.splice(index + 1, 0, emptyStep(defaultAgent));
      return { ...current, steps: nextSteps };
    });
  };

  const appendStep = () => {
    const defaultAgent = chatAgents[0];
    setDraftPlan((current) => ({
      ...current,
      steps: [...(current.steps ?? []), emptyStep(defaultAgent)],
    }));
  };

  const handleSaveLocal = () => {
    setAppliedPlan(clonePlan(draftPlan));
    setError(null);
  };

  const handleRestore = () => {
    const restored = clonePlan(originalBaseline);
    setDraftPlan(restored);
    setAppliedPlan(restored);
    setError(null);
  };

  const handlePersist = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${job.idx}/plan`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          summary: draftPlan.summary ?? "",
          steps: draftPlan.steps,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "작업 계획 저장에 실패했습니다.");
      }
      const updated = (await response.json()) as JobRecord;
      setDraftPlan(clonePlan(updated.job_plan));
      setAppliedPlan(clonePlan(updated.job_plan));
      onJobUpdated?.(updated);
      setShowModifyConfirm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 계획 저장에 실패했습니다.");
      setShowModifyConfirm(false);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
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
                <div>
                  SR 번호: <span className="font-mono text-sky-200">{job.sr_num ?? "-"}</span>
                </div>
                <div>기안일시: {job.request_date}</div>
                <div>작업완료요청일시: {job.completion_request_date}</div>
                <div>실제작업완료시간: {job.actual_completion_time ?? "-"}</div>
                <div>기안자: {jobRequesterLabel(job)}</div>
                <div>기안자 조직: {job.request_depart}</div>
                <div>승인자: {jobApproverLabel(job)}</div>
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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-medium text-slate-300">작업 계획</h3>
                {editable ? (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={handleSaveLocal}
                      className="rounded-md border border-sky-700 px-2 py-1 text-xs text-sky-200 hover:bg-sky-950/40"
                    >
                      저장
                    </button>
                    <button
                      type="button"
                      onClick={handleRestore}
                      className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
                    >
                      원복
                    </button>
                    <button
                      type="button"
                      disabled={isSaving}
                      onClick={() => setShowModifyConfirm(true)}
                      className="rounded-md border border-emerald-700 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-950/40 disabled:text-slate-500"
                    >
                      수정
                    </button>
                  </div>
                ) : null}
              </div>

              {editable ? (
                <textarea
                  value={draftPlan.summary ?? ""}
                  onChange={(event) =>
                    setDraftPlan((current) => ({ ...current, summary: event.target.value }))
                  }
                  rows={3}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500"
                  placeholder="계획 요약"
                />
              ) : (
                <p className="rounded-md border border-slate-800 bg-slate-950/40 p-3 text-slate-300">
                  {appliedPlan.summary || "등록된 계획 요약이 없습니다."}
                </p>
              )}

              <ul className="space-y-2">
                {((editable ? draftPlan.steps : appliedPlan.steps) ?? []).map((step, index) => (
                  <li
                    key={`plan-step-${index}`}
                    className="rounded-md border border-slate-800 bg-slate-950/40 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        {editable ? (
                          <div className="flex flex-wrap gap-2">
                            <select
                              value={step.agent_id}
                              onChange={(event) => {
                                const selected = chatAgents.find(
                                  (agent) => agent.id === event.target.value,
                                );
                                updateStep(index, {
                                  agent_id: selected?.id ?? event.target.value,
                                  agent_name: selected?.name ?? event.target.value,
                                  tool_name: "",
                                });
                              }}
                              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100 outline-none"
                            >
                              {!chatAgents.some((agent) => agent.id === step.agent_id) ? (
                                <option value={step.agent_id}>{step.agent_name ?? step.agent_id}</option>
                              ) : null}
                              {chatAgents.map((agent) => (
                                <option key={agent.id} value={agent.id}>
                                  {agent.name}
                                </option>
                              ))}
                            </select>
                          </div>
                        ) : (
                          <div className="font-medium text-sky-200">
                            {index + 1}. {step.agent_name ?? step.agent_id}
                          </div>
                        )}
                        {!editable ? (
                          <div className="mt-1 text-xs text-slate-400">도구: {step.tool_name ?? "-"}</div>
                        ) : null}
                      </div>
                      {editable ? (
                        <button
                          type="button"
                          onClick={() => removeStep(index)}
                          title="단계 삭제"
                          className="rounded-md border border-rose-800 px-2 py-0.5 text-xs text-rose-300 hover:bg-rose-950/40"
                        >
                          X
                        </button>
                      ) : null}
                    </div>

                    {editable ? (
                      <textarea
                        value={step.description ?? ""}
                        onChange={(event) => updateStep(index, { description: event.target.value })}
                        rows={3}
                        className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500"
                        placeholder="단계 설명"
                      />
                    ) : (
                      <p className="mt-2 text-slate-300">{step.description ?? "-"}</p>
                    )}

                    {editable ? (
                      <div className="mt-2 flex justify-end">
                        <button
                          type="button"
                          onClick={() => insertStepBelow(index)}
                          title="아래에 단계 추가"
                          className="rounded-md border border-sky-700 px-2 py-0.5 text-xs text-sky-200 hover:bg-sky-950/40"
                        >
                          +
                        </button>
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>

              {editable ? (
                <button
                  type="button"
                  onClick={appendStep}
                  className="rounded-md border border-sky-700 px-2 py-1 text-xs text-sky-200 hover:bg-sky-950/40"
                >
                  + 단계 추가
                </button>
              ) : null}
            </section>

            <section className="space-y-2">
              <h3 className="font-medium text-slate-300">에이전트 호출 계획</h3>
              <PlanFlowDiagram
                job={job}
                steps={appliedPlan.steps ?? []}
                editable={editable}
                toolsByAgent={toolsByAgent}
                onToolChange={(index, toolName) => {
                  setAppliedPlan((current) => ({
                    ...current,
                    steps: (current.steps ?? []).map((step, stepIndex) =>
                      stepIndex === index ? { ...step, tool_name: toolName } : step,
                    ),
                  }));
                  setDraftPlan((current) => ({
                    ...current,
                    steps: (current.steps ?? []).map((step, stepIndex) =>
                      stepIndex === index ? { ...step, tool_name: toolName } : step,
                    ),
                  }));
                }}
              />
            </section>

            {job.execution_result ? (
              <section className="space-y-2">
                <h3 className="font-medium text-slate-300">작업 수행 결과</h3>
                <p className="whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-950/40 p-3 text-slate-300">
                  {job.execution_result.summary || "-"}
                </p>
                {(job.execution_result.results ?? []).length > 0 ? (
                  <ul className="space-y-2">
                    {(job.execution_result.results ?? []).map((result, index) => {
                      const isFailed = result.status !== "completed";
                      return (
                        <li
                          key={`${result.agent_id}-${index}`}
                          className={`rounded-md border p-3 ${
                            isFailed
                              ? "border-rose-800/60 bg-rose-950/20"
                              : "border-slate-800 bg-slate-950/40"
                          }`}
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-sky-200">
                              {index + 1}. {result.agent_name ?? result.agent_id}
                            </span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] ${
                                isFailed
                                  ? "border border-rose-700/50 bg-rose-950/40 text-rose-200"
                                  : "border border-emerald-700/50 bg-emerald-950/40 text-emerald-200"
                              }`}
                            >
                              {result.status === "completed"
                                ? "완료"
                                : result.status === "skipped"
                                  ? "건너뜀"
                                  : "실패"}
                            </span>
                          </div>
                          {result.tool_name ? (
                            <div className="mt-1 text-xs text-slate-400">도구: {result.tool_name}</div>
                          ) : null}
                          <p className="mt-2 whitespace-pre-wrap text-slate-300">
                            {isFailed ? `실패 사유: ${result.content || "-"}` : result.content || "-"}
                          </p>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </section>
            ) : null}

            {error ? (
              <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
                {error}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {showModifyConfirm ? (
        <ConfirmDialog
          title="작업 계획 수정"
          message="수정한 작업 계획을 저장하시겠습니까?"
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setShowModifyConfirm(false)}
          onConfirm={() => void handlePersist()}
        />
      ) : null}
    </>
  );
}
