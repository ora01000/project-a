import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "../ConfirmDialog";
import { AgentFormModal } from "./AgentFormModal";
import type { AgentFormValues, AgentRecord, McpServerOption } from "../../types/agent-admin";
import { formatMcpServerKeys, truncateText } from "../../types/agent-admin";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function AgentListPage() {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServerOption[]>([]);
  const [selectedIdxSet, setSelectedIdxSet] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const selectedAgents = useMemo(
    () => agents.filter((agent) => selectedIdxSet.has(agent.idx)),
    [agents, selectedIdxSet],
  );

  const loadAgents = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [agentsResponse, mcpServersResponse] = await Promise.all([
        fetch("/api/agent-records"),
        fetch("/api/mcp-servers"),
      ]);

      if (!agentsResponse.ok) {
        throw new Error(await parseError(agentsResponse, "에이전트 목록을 불러오지 못했습니다."));
      }
      if (!mcpServersResponse.ok) {
        throw new Error(await parseError(mcpServersResponse, "MCP 도구 목록을 불러오지 못했습니다."));
      }

      const agentsData = (await agentsResponse.json()) as AgentRecord[];
      const mcpServersData = (await mcpServersResponse.json()) as McpServerOption[];
      setAgents(agentsData);
      setMcpServers(mcpServersData);
      setSelectedIdxSet((current) => {
        const valid = new Set(agentsData.map((agent) => agent.idx));
        return new Set([...current].filter((idx) => valid.has(idx)));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "에이전트 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

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
    if (selectedIdxSet.size === agents.length) {
      setSelectedIdxSet(new Set());
      return;
    }
    setSelectedIdxSet(new Set(agents.map((agent) => agent.idx)));
  };

  const handleCreate = async (values: AgentFormValues) => {
    const response = await fetch("/api/agent-records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "에이전트 추가에 실패했습니다."));
    }
    await loadAgents();
  };

  const handleUpdate = async (values: AgentFormValues) => {
    const target = selectedAgents[0];
    if (!target) {
      throw new Error("수정할 에이전트를 선택해 주세요.");
    }

    const response = await fetch(`/api/agent-records/${target.idx}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "에이전트 수정에 실패했습니다."));
    }
    await loadAgents();
  };

  const handleDelete = async () => {
    if (selectedIdxSet.size === 0) {
      return;
    }

    const response = await fetch("/api/agent-records", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idx_list: [...selectedIdxSet] }),
    });
    if (!response.ok) {
      setError(await parseError(response, "에이전트 삭제에 실패했습니다."));
      setShowDeleteConfirm(false);
      return;
    }

    setShowDeleteConfirm(false);
    setSelectedIdxSet(new Set());
    await loadAgents();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">에이전트 관리</h2>
          <p className="mt-0.5 text-xs text-slate-500">agents 테이블 데이터를 조회하고 관리합니다.</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={selectedIdxSet.size === 0}
            className="rounded-md border border-rose-800 px-3 py-1.5 text-sm text-rose-200 hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            삭제
          </button>
          <button
            type="button"
            onClick={() => {
              if (selectedAgents.length !== 1) {
                setError("수정할 에이전트 1개를 선택해 주세요.");
                return;
              }
              setError(null);
              setFormMode("edit");
            }}
            disabled={selectedAgents.length !== 1}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            수정
          </button>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setFormMode("create");
            }}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            추가
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
          <p className="text-sm text-slate-500">에이전트 목록을 불러오는 중...</p>
        ) : (
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                <th className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={agents.length > 0 && selectedIdxSet.size === agents.length}
                    onChange={toggleAll}
                    aria-label="전체 선택"
                  />
                </th>
                <th className="px-3 py-2">idx</th>
                <th className="px-3 py-2">에이전트 ID</th>
                <th className="px-3 py-2">Display 이름</th>
                <th className="px-3 py-2">역할(간략)</th>
                <th className="px-3 py-2">사용 도구</th>
                <th className="px-3 py-2">역할(상세)</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.idx} className="border-b border-slate-800 text-slate-200">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selectedIdxSet.has(agent.idx)}
                      onChange={() => toggleRow(agent.idx)}
                      aria-label={`${agent.agent_id} 선택`}
                    />
                  </td>
                  <td className="px-3 py-2">{agent.idx}</td>
                  <td className="px-3 py-2">{agent.agent_id}</td>
                  <td className="px-3 py-2">{agent.name}</td>
                  <td className="px-3 py-2">{agent.role}</td>
                  <td className="px-3 py-2">{formatMcpServerKeys(agent.mcp_server_keys)}</td>
                  <td className="px-3 py-2" title={agent.system_prompt}>
                    {truncateText(agent.system_prompt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {formMode ? (
        <AgentFormModal
          mode={formMode}
          agent={formMode === "edit" ? selectedAgents[0] : undefined}
          mcpServers={mcpServers}
          onClose={() => setFormMode(null)}
          onSave={formMode === "create" ? handleCreate : handleUpdate}
        />
      ) : null}

      {showDeleteConfirm ? (
        <ConfirmDialog
          title="에이전트 삭제"
          message={`선택한 ${selectedIdxSet.size}개의 에이전트를 삭제하시겠습니까?`}
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setShowDeleteConfirm(false)}
          onConfirm={() => void handleDelete()}
        />
      ) : null}
    </div>
  );
}
