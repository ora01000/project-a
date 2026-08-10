import { useEffect, useState, type FormEvent } from "react";

import type { AgentRuntimeFormValues, AgentRuntimeRecord } from "../../types/agentruntime";
import {
  AGENTRUNTIME_TYPE_OPTIONS,
  agentRuntimeFormFromRecord,
  emptyAgentRuntimeForm,
} from "../../types/agentruntime";
import { ConfirmDialog } from "../ConfirmDialog";

interface AgentConnectionFormModalProps {
  mode: "create" | "edit";
  record?: AgentRuntimeRecord;
  initialValues?: AgentRuntimeFormValues;
  defaultType?: number;
  onClose: () => void;
  onSave: (values: AgentRuntimeFormValues) => Promise<void>;
}

export function AgentConnectionFormModal({
  mode,
  record,
  initialValues,
  defaultType = 0,
  onClose,
  onSave,
}: AgentConnectionFormModalProps) {
  const [values, setValues] = useState<AgentRuntimeFormValues>(() => emptyAgentRuntimeForm());
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showUpdateConfirm, setShowUpdateConfirm] = useState(false);

  useEffect(() => {
    if (mode === "edit" && record) {
      setValues(agentRuntimeFormFromRecord(record));
      return;
    }
    if (mode === "create" && initialValues) {
      setValues(initialValues);
      return;
    }
    setValues(emptyAgentRuntimeForm(defaultType));
  }, [mode, record, initialValues, defaultType]);

  const updateField = <K extends keyof AgentRuntimeFormValues>(
    key: K,
    value: AgentRuntimeFormValues[K],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const submitValues = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await onSave(values);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
      setShowUpdateConfirm(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (mode === "edit") {
      setShowUpdateConfirm(true);
      return;
    }
    await submitValues();
  };

  return (
    <>
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/70 px-4">
        <div
          role="dialog"
          aria-modal="true"
          className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
        >
          <h2 className="text-base font-semibold text-slate-100">
            {mode === "create" ? "에이전트 연결 추가" : "에이전트 연결 수정"}
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Token URL·Agent URL은 환경변수(TOKEN_URL, AGENT_URL)로 고정됩니다.
          </p>

          <form onSubmit={(event) => void handleSubmit(event)} className="mt-4 space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              {mode === "create" ? (
                <label className="block text-sm text-slate-300">
                  <span className="mb-1 block">유형</span>
                  <select
                    value={values.type}
                    onChange={(event) => updateField("type", Number(event.target.value))}
                    disabled={isSaving}
                    required
                    className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                  >
                    {AGENTRUNTIME_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label className="block text-sm text-slate-300">
                <span className="mb-1 block">에이전트 이름</span>
                <input
                  value={values.agent_name}
                  onChange={(event) => updateField("agent_name", event.target.value)}
                  disabled={isSaving}
                  maxLength={50}
                  required
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
              </label>
              <label className="block text-sm text-slate-300">
                <span className="mb-1 block">Service ID</span>
                <input
                  value={values.service_id}
                  onChange={(event) => updateField("service_id", event.target.value)}
                  disabled={isSaving}
                  maxLength={20}
                  required
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
              </label>
              <label className="block text-sm text-slate-300 md:col-span-2">
                <span className="mb-1 block">Agent ID</span>
                <input
                  value={values.agent_id}
                  onChange={(event) => updateField("agent_id", event.target.value)}
                  disabled={isSaving}
                  maxLength={50}
                  required
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-500"
                />
              </label>
              <label className="block text-sm text-slate-300 md:col-span-2">
                <span className="mb-1 block">Local Agent ID</span>
                <input
                  value={values.local_agent_id}
                  onChange={(event) => updateField("local_agent_id", event.target.value)}
                  disabled={isSaving}
                  maxLength={50}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-500"
                />
              </label>
              <label className="block text-sm text-slate-300 md:col-span-2">
                <span className="mb-1 block">설명</span>
                <textarea
                  value={values.description}
                  onChange={(event) => updateField("description", event.target.value)}
                  disabled={isSaving}
                  maxLength={255}
                  rows={3}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
              </label>
              {mode === "edit" ? (
                <label className="block text-sm text-slate-300 md:col-span-2">
                  <span className="mb-1 block">등록일시</span>
                  <input
                    value={values.registered_date}
                    onChange={(event) => updateField("registered_date", event.target.value)}
                    disabled={isSaving}
                    maxLength={40}
                    className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-500"
                  />
                </label>
              ) : null}
            </div>

            {error ? (
              <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
                {error}
              </div>
            ) : null}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={isSaving}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
              >
                닫기
              </button>
              <button
                type="submit"
                disabled={isSaving}
                className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:bg-slate-700"
              >
                {isSaving ? "저장 중..." : mode === "edit" ? "업데이트" : "추가"}
              </button>
            </div>
          </form>
        </div>
      </div>

      {showUpdateConfirm ? (
        <ConfirmDialog
          title="에이전트 연결 수정"
          message="입력한 내용으로 업데이트하시겠습니까?"
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setShowUpdateConfirm(false)}
          onConfirm={() => void submitValues()}
        />
      ) : null}
    </>
  );
}
