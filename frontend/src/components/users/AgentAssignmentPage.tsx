import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AgentRecord } from "../../types/agent-admin";
import type { UserRecord } from "../../types/user";
import { ROLE_ADMIN, roleLabel } from "../../types/user";

interface AgentAssignmentPageProps {
  onClose: () => void;
}

interface AssignmentDraft {
  idx: number;
  depart: string;
  username: string;
  role: number;
  agentIds: string[];
}

const DRAG_MIME = "application/x-project-a-agent-ids";
const DRAG_MIME_LEGACY = "application/x-project-a-agent-id";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function uniqueAgentIds(agentIds: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const agentId of agentIds) {
    const trimmed = agentId.trim();
    if (!trimmed || seen.has(trimmed)) {
      continue;
    }
    seen.add(trimmed);
    result.push(trimmed);
  }
  return result;
}

function parseDraggedAgentIds(dataTransfer: DataTransfer): string[] {
  const multi = dataTransfer.getData(DRAG_MIME);
  if (multi) {
    try {
      const parsed = JSON.parse(multi) as unknown;
      if (Array.isArray(parsed)) {
        return uniqueAgentIds(parsed.map(String));
      }
    } catch {
      // fall through
    }
  }
  const single =
    dataTransfer.getData(DRAG_MIME_LEGACY) || dataTransfer.getData("text/plain");
  return single ? uniqueAgentIds([single]) : [];
}

export function AgentAssignmentPage({ onClose }: AgentAssignmentPageProps) {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [drafts, setDrafts] = useState<AssignmentDraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [dropTargetIdx, setDropTargetIdx] = useState<number | null>(null);
  const [draggingAgentIds, setDraggingAgentIds] = useState<string[]>([]);
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(new Set());
  const suppressClickRef = useRef(false);

  const agentNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agents) {
      map.set(agent.agent_id, agent.name);
    }
    return map;
  }, [agents]);

  const allAgentIds = useMemo(() => agents.map((agent) => agent.agent_id), [agents]);
  const hasSelection = selectedAgentIds.size > 0;

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [agentsResponse, usersResponse] = await Promise.all([
        fetch("/api/agent-records"),
        fetch(`/api/users?viewer_role=${ROLE_ADMIN}`),
      ]);
      if (!agentsResponse.ok) {
        throw new Error(await parseError(agentsResponse, "에이전트 목록을 불러오지 못했습니다."));
      }
      if (!usersResponse.ok) {
        throw new Error(await parseError(usersResponse, "사용자 목록을 불러오지 못했습니다."));
      }

      const agentsData = (await agentsResponse.json()) as AgentRecord[];
      const usersData = (await usersResponse.json()) as UserRecord[];
      setAgents(agentsData);
      setSelectedAgentIds(new Set());
      setDrafts(
        usersData.map((user) => ({
          idx: user.idx,
          depart: user.depart,
          username: user.username,
          role: user.role,
          agentIds: uniqueAgentIds(user.agent_ids ?? (user.agents ? user.agents.split(",") : [])),
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "데이터를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) {
          return;
        }
      }

      const isSelectAll =
        (event.key === "a" || event.key === "A") && (event.metaKey || event.ctrlKey);
      if (isSelectAll) {
        event.preventDefault();
        setSelectedAgentIds(new Set(allAgentIds));
        return;
      }

      if (event.key === "Escape" && hasSelection) {
        event.preventDefault();
        event.stopPropagation();
        setSelectedAgentIds(new Set());
      }
    };

    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [allAgentIds, hasSelection]);

  const toggleAgentSelection = (agentId: string) => {
    setSelectedAgentIds((current) => {
      const next = new Set(current);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  };

  const assignAgents = (userIdx: number, agentIds: string[]) => {
    if (agentIds.length === 0) {
      return;
    }
    setDrafts((current) =>
      current.map((draft) => {
        if (draft.idx !== userIdx) {
          return draft;
        }
        return {
          ...draft,
          agentIds: uniqueAgentIds([...draft.agentIds, ...agentIds]),
        };
      }),
    );
  };

  const removeAgent = (userIdx: number, agentId: string) => {
    setDrafts((current) =>
      current.map((draft) => {
        if (draft.idx !== userIdx) {
          return draft;
        }
        return {
          ...draft,
          agentIds: draft.agentIds.filter((id) => id !== agentId),
        };
      }),
    );
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/users/agent-assignments", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assignments: drafts.map((draft) => ({
            idx: draft.idx,
            agent_ids: draft.agentIds,
          })),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "에이전트 할당 저장에 실패했습니다."));
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "에이전트 할당 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-assignment-title"
        className="flex max-h-[90vh] w-full max-w-6xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="agent-assignment-title" className="text-lg font-semibold text-slate-100">
              에이전트 할당
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              왼쪽 에이전트를 클릭해 다중 선택(Ctrl/Cmd+A 전체 선택, Esc 선택 해제)한 뒤 사용자 행으로
              드래그하세요. 할당된 에이전트 레이블을 클릭하면 해제됩니다.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={isLoading || isSaving || drafts.length === 0}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSaving ? "저장 중…" : "저장"}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={isSaving}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            >
              닫기
            </button>
          </div>
        </div>

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

        {isLoading ? (
          <p className="mt-4 text-sm text-slate-400">불러오는 중…</p>
        ) : (
          <div className="mt-4 flex min-h-0 flex-1 flex-col gap-3 md:flex-row">
            <aside className="flex max-h-48 min-h-0 w-full shrink-0 flex-col rounded-md border border-slate-700 md:max-h-none md:w-64">
              <div className="flex items-center justify-between gap-2 border-b border-slate-700 px-3 py-2">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                  일반 에이전트
                </span>
                <span className="text-[10px] text-slate-500">
                  {selectedAgentIds.size}/{agents.length} 선택
                </span>
              </div>
              <div className="flex min-h-0 flex-1 flex-wrap content-start gap-2 overflow-y-auto p-3">
                {agents.length === 0 ? (
                  <p className="text-sm text-slate-500">등록된 에이전트가 없습니다.</p>
                ) : (
                  agents.map((agent) => {
                    const isSelected = selectedAgentIds.has(agent.agent_id);
                    const isDragging = draggingAgentIds.includes(agent.agent_id);
                    return (
                      <button
                        key={agent.agent_id}
                        type="button"
                        draggable
                        aria-pressed={isSelected}
                        onClick={() => {
                          if (suppressClickRef.current) {
                            suppressClickRef.current = false;
                            return;
                          }
                          toggleAgentSelection(agent.agent_id);
                        }}
                        onDragStart={(event) => {
                          suppressClickRef.current = true;
                          const payloadIds = selectedAgentIds.has(agent.agent_id)
                            ? allAgentIds.filter((id) => selectedAgentIds.has(id))
                            : [agent.agent_id];
                          event.dataTransfer.setData(DRAG_MIME, JSON.stringify(payloadIds));
                          event.dataTransfer.setData(DRAG_MIME_LEGACY, payloadIds[0] ?? "");
                          event.dataTransfer.setData("text/plain", payloadIds.join(","));
                          event.dataTransfer.effectAllowed = "copy";
                          setDraggingAgentIds(payloadIds);
                          if (!selectedAgentIds.has(agent.agent_id)) {
                            setSelectedAgentIds(new Set([agent.agent_id]));
                          }
                        }}
                        onDragEnd={() => {
                          setDraggingAgentIds([]);
                          setDropTargetIdx(null);
                          window.setTimeout(() => {
                            suppressClickRef.current = false;
                          }, 0);
                        }}
                        title={`${agent.agent_id} — ${agent.role}`}
                        className={`rounded-md border px-2.5 py-1.5 text-left text-xs font-medium transition ${
                          isDragging || isSelected
                            ? "border-sky-500 bg-sky-950/60 text-sky-100 ring-1 ring-sky-500/60"
                            : "border-slate-600 bg-slate-800 text-slate-100 hover:border-sky-700 hover:bg-slate-700"
                        }`}
                      >
                        <span className="block truncate">{agent.name}</span>
                        <span className="mt-0.5 block truncate font-mono text-[10px] text-slate-400">
                          {agent.agent_id}
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            </aside>

            <div className="min-h-0 min-w-0 flex-1 overflow-auto rounded-md border border-slate-700">
              {drafts.length === 0 ? (
                <p className="p-4 text-sm text-slate-400">사용자가 없습니다.</p>
              ) : (
                <table className="min-w-full border-collapse text-left text-sm text-slate-200">
                  <thead className="sticky top-0 bg-slate-800">
                    <tr>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        조직
                      </th>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        이름
                      </th>
                      <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        역할
                      </th>
                      <th className="border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                        할당된 에이전트
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {drafts.map((draft) => {
                      const isDropTarget = dropTargetIdx === draft.idx;
                      return (
                        <tr
                          key={draft.idx}
                          onDragOver={(event) => {
                            event.preventDefault();
                            event.dataTransfer.dropEffect = "copy";
                            setDropTargetIdx(draft.idx);
                          }}
                          onDragLeave={() => {
                            setDropTargetIdx((current) => (current === draft.idx ? null : current));
                          }}
                          onDrop={(event) => {
                            event.preventDefault();
                            const agentIds = parseDraggedAgentIds(event.dataTransfer);
                            setDropTargetIdx(null);
                            setDraggingAgentIds([]);
                            assignAgents(draft.idx, agentIds);
                          }}
                          className={`align-top transition ${
                            isDropTarget
                              ? "bg-sky-950/40 outline outline-1 outline-sky-600"
                              : "odd:bg-slate-900/40 even:bg-slate-900/80"
                          }`}
                        >
                          <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2">
                            {draft.depart}
                          </td>
                          <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2">
                            {draft.username}
                          </td>
                          <td className="whitespace-nowrap border-b border-slate-800 px-3 py-2">
                            {draft.role}: {roleLabel(draft.role)}
                          </td>
                          <td className="border-b border-slate-800 px-3 py-2">
                            <div className="flex min-h-[2rem] flex-wrap gap-1.5">
                              {draft.agentIds.length === 0 ? (
                                <span className="text-xs text-slate-500">드래그하여 할당</span>
                              ) : (
                                draft.agentIds.map((agentId) => (
                                  <button
                                    key={agentId}
                                    type="button"
                                    onClick={() => removeAgent(draft.idx, agentId)}
                                    title="클릭하여 할당 해제"
                                    className="rounded border border-emerald-800 bg-emerald-950/40 px-2 py-0.5 text-[11px] text-emerald-100 hover:border-rose-700 hover:bg-rose-950/40 hover:text-rose-100"
                                  >
                                    {agentNameById.get(agentId) ?? agentId}
                                  </button>
                                ))
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
