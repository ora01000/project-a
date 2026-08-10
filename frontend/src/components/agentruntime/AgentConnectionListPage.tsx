import { useCallback, useEffect, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { AgentRuntimeFormValues, AgentRuntimeRecord } from "../../types/agentruntime";
import { agentRuntimeFormFromRecord, agentRuntimeTypeLabel } from "../../types/agentruntime";
import { ConfirmDialog } from "../ConfirmDialog";
import { AgentConnectionFormModal } from "./AgentConnectionFormModal";

interface AgentConnectionListPageProps {
  user: AuthUser;
  onClose: () => void;
  onAgentRuntimeChanged?: () => void | Promise<void>;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function AgentConnectionListPage({
  user,
  onClose,
  onAgentRuntimeChanged,
}: AgentConnectionListPageProps) {
  const [records, setRecords] = useState<AgentRuntimeRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [editingRecord, setEditingRecord] = useState<AgentRuntimeRecord | null>(null);
  const [createInitialValues, setCreateInitialValues] = useState<AgentRuntimeFormValues | null>(null);
  const [defaultType, setDefaultType] = useState(0);
  const [deletingRecord, setDeletingRecord] = useState<AgentRuntimeRecord | null>(null);

  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/agentruntime");
      if (!response.ok) {
        throw new Error(await parseError(response, "에이전트 연결 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as AgentRuntimeRecord[];
      setRecords(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "에이전트 연결 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    const loadDefaultType = async () => {
      try {
        const response = await fetch("/api/health");
        if (!response.ok) {
          return;
        }
        const health = (await response.json()) as { runtime_mode?: string };
        setDefaultType(health.runtime_mode === "http" ? 1 : 0);
      } catch {
        setDefaultType(0);
      }
    };
    void loadDefaultType();
  }, []);

  const writePayload = (values: AgentRuntimeFormValues) => ({
    ...values,
    viewer_role: user.role,
  });

  const notifyDashboard = useCallback(async () => {
    if (onAgentRuntimeChanged) {
      await onAgentRuntimeChanged();
    }
  }, [onAgentRuntimeChanged]);

  const handleCreate = async (values: AgentRuntimeFormValues) => {
    const response = await fetch("/api/agentruntime", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(writePayload(values)),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "에이전트 연결 추가에 실패했습니다."));
    }
    await loadRecords();
    await notifyDashboard();
  };

  const handleUpdate = async (values: AgentRuntimeFormValues) => {
    if (!editingRecord) {
      throw new Error("수정할 연결 정보를 선택해 주세요.");
    }
    const response = await fetch(`/api/agentruntime/${editingRecord.idx}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(writePayload(values)),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "에이전트 연결 수정에 실패했습니다."));
    }
    await loadRecords();
    await notifyDashboard();
  };

  const closeForm = () => {
    setFormMode(null);
    setEditingRecord(null);
    setCreateInitialValues(null);
  };

  const openCreateForm = (prefill?: AgentRuntimeRecord) => {
    setError(null);
    setEditingRecord(null);
    setCreateInitialValues(prefill ? agentRuntimeFormFromRecord(prefill) : null);
    setFormMode("create");
  };

  const handleDelete = async () => {
    if (!deletingRecord) {
      return;
    }
    const response = await fetch(`/api/agentruntime/${deletingRecord.idx}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ viewer_role: user.role }),
    });
    if (!response.ok) {
      setError(await parseError(response, "에이전트 연결 삭제에 실패했습니다."));
      setDeletingRecord(null);
      return;
    }
    setDeletingRecord(null);
    await loadRecords();
    await notifyDashboard();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-connections-title"
        className="flex max-h-[90vh] w-full max-w-[108rem] flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-xl"
      >
        <header className="flex shrink-0 items-center justify-between border-b border-slate-700 px-4 py-3">
          <div>
            <h2 id="agent-connections-title" className="text-lg font-semibold text-slate-100">
              에이전트 연결 목록
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">agentruntime 테이블 연결 정보입니다.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => openCreateForm()}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
            >
              추가
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              닫기
            </button>
          </div>
        </header>

        {error ? (
          <div className="mx-4 mt-4 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <p className="text-sm text-slate-500">목록을 불러오는 중...</p>
          ) : records.length === 0 ? (
            <p className="text-sm text-slate-500">등록된 에이전트 연결이 없습니다.</p>
          ) : (
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-slate-400">
                  <th className="px-3 py-2">유형</th>
                  <th className="px-3 py-2">에이전트 이름</th>
                  <th className="px-3 py-2">Agent ID</th>
                  <th className="px-3 py-2">Local Agent ID</th>
                  <th className="px-3 py-2">설명</th>
                  <th className="px-3 py-2">등록일시</th>
                  <th className="px-3 py-2">Service ID</th>
                  <th className="px-3 py-2">대화 가능</th>
                  <th className="px-3 py-2">오케스트레이터</th>
                  <th className="px-3 py-2">작업</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.idx} className="border-b border-slate-800 text-slate-200">
                    <td className="px-3 py-2 whitespace-nowrap">{agentRuntimeTypeLabel(record.type)}</td>
                    <td className="px-3 py-2">{record.agent_name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{record.agent_id}</td>
                    <td className="px-3 py-2 font-mono text-xs">{record.local_agent_id || "-"}</td>
                    <td className="max-w-[10rem] truncate px-3 py-2" title={record.description}>
                      {record.description}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap font-mono text-xs">{record.registered_date}</td>
                    <td className="px-3 py-2">{record.service_id}</td>
                    <td className="px-3 py-2">{record.talkable ? "예" : "아니오"}</td>
                    <td className="px-3 py-2">{record.is_orchestrator ? "예" : "아니오"}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setEditingRecord(record);
                            setCreateInitialValues(null);
                            setFormMode("edit");
                          }}
                          className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
                        >
                          수정
                        </button>
                        <button
                          type="button"
                          onClick={() => openCreateForm(record)}
                          className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
                        >
                          복제
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setDeletingRecord(record);
                          }}
                          className="rounded-md border border-rose-800 px-2 py-1 text-xs text-rose-200 hover:bg-rose-950/40"
                        >
                          삭제
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {formMode ? (
        <AgentConnectionFormModal
          mode={formMode}
          record={formMode === "edit" ? editingRecord ?? undefined : undefined}
          initialValues={formMode === "create" ? createInitialValues ?? undefined : undefined}
          defaultType={defaultType}
          onClose={closeForm}
          onSave={formMode === "create" ? handleCreate : handleUpdate}
        />
      ) : null}

      {deletingRecord ? (
        <ConfirmDialog
          title="에이전트 연결 삭제"
          message={`'${deletingRecord.agent_name}' 연결을 삭제하시겠습니까?`}
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setDeletingRecord(null)}
          onConfirm={() => void handleDelete()}
        />
      ) : null}
    </div>
  );
}
