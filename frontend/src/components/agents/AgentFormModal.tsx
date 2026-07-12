import { useEffect, useState } from "react";

import type { AgentFormValues, AgentRecord, McpServerOption } from "../../types/agent-admin";
import { EMPTY_AGENT_FORM } from "../../types/agent-admin";

interface AgentFormModalProps {
  mode: "create" | "edit";
  agent?: AgentRecord;
  mcpServers: McpServerOption[];
  onClose: () => void;
  onSave: (values: AgentFormValues) => Promise<void>;
}

export function AgentFormModal({ mode, agent, mcpServers, onClose, onSave }: AgentFormModalProps) {
  const [values, setValues] = useState<AgentFormValues>(EMPTY_AGENT_FORM);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (mode === "edit" && agent) {
      setValues({
        agent_id: agent.agent_id,
        name: agent.name,
        role: agent.role,
        system_prompt: agent.system_prompt,
        mcp_server_keys: [...agent.mcp_server_keys],
      });
      return;
    }

    setValues(EMPTY_AGENT_FORM);
  }, [mode, agent]);

  const updateField = <K extends keyof AgentFormValues>(key: K, value: AgentFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const toggleMcpServer = (serverKey: string) => {
    setValues((current) => {
      const nextKeys = new Set(current.mcp_server_keys);
      if (nextKeys.has(serverKey)) {
        nextKeys.delete(serverKey);
      } else {
        nextKeys.add(serverKey);
      }
      return {
        ...current,
        mcp_server_keys: [...nextKeys].sort(),
      };
    });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!values.agent_id.trim()) {
      setError("에이전트 ID를 입력해 주세요.");
      return;
    }
    if (!values.name.trim() || !values.role.trim() || !values.system_prompt.trim()) {
      setError("필수 항목을 입력해 주세요.");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await onSave(values);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-slate-100">
          {mode === "create" ? "에이전트 추가" : "에이전트 수정"}
        </h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>에이전트 ID</span>
            <input
              value={values.agent_id}
              onChange={(event) => updateField("agent_id", event.target.value)}
              disabled={mode === "edit" || isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500 disabled:text-slate-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>Display 이름</span>
            <input
              value={values.name}
              onChange={(event) => updateField("name", event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>에이전트 역할(간략)</span>
            <input
              value={values.role}
              onChange={(event) => updateField("role", event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>에이전트 역할(상세)</span>
            <textarea
              value={values.system_prompt}
              onChange={(event) => updateField("system_prompt", event.target.value)}
              disabled={isSaving}
              rows={6}
              className="w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <fieldset className="space-y-2 rounded-md border border-slate-700 px-3 py-3">
            <legend className="px-1 text-sm text-slate-300">사용 도구</legend>
            {mcpServers.length === 0 ? (
              <p className="text-sm text-slate-500">등록된 MCP 도구가 없습니다.</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {mcpServers.map((server) => (
                  <label
                    key={server.key}
                    className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-200"
                  >
                    <input
                      type="checkbox"
                      checked={values.mcp_server_keys.includes(server.key)}
                      onChange={() => toggleMcpServer(server.key)}
                      disabled={isSaving}
                    />
                    <span>
                      {server.key}
                      {!server.enabled ? (
                        <span className="ml-2 text-xs text-slate-500">(disabled)</span>
                      ) : null}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </fieldset>

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
              {isSaving ? "저장 중..." : "저장"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
