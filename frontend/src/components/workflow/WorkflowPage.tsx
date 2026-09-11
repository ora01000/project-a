import { useCallback, useEffect, useRef, useState } from "react";

import type { AgentInfo } from "../../types/agent";
import type { AuthUser } from "../../types/auth";
import type { WorkflowItem, WorkNodeItem } from "../../types/workflow";
import { OpenAiBillingConfirmDialog } from "../OpenAiBillingConfirmDialog";
import { fetchLlmBillingStatus } from "../../utils/llmBilling";
import { flushSseBuffer, parseSseChunk } from "../../utils/parseSse";
import { createSessionId } from "../../utils/sessionId";
import { parseAiWorkflowDesignResponse } from "./aiWorkflowParse";
import { WorkflowDesignPanel } from "./WorkflowDesignPanel";
import type { DiagramAgentEvent } from "./WorkflowEditor";
import { WorkflowIcon } from "./WorkflowIcon";
import { WorkflowListPanel } from "./WorkflowListPanel";
import { describeCronExpr } from "./WorkflowScheduleField";
import { isRunInProgress } from "./workflowModel";
import { normalizeCrudFlags } from "./aiWorkflowParse";

const WORKFLOW_AGENT_ID = "WORKFLOW_AGENT";

const CRUD_BADGE_META: { key: "c" | "r" | "u" | "d"; label: string }[] = [
  { key: "c", label: "생성" },
  { key: "r", label: "읽기" },
  { key: "u", label: "갱신" },
  { key: "d", label: "삭제" },
];

function collectWorkUuidsFromWorkflowDoc(workflow: string): Set<string> {
  const uuids = new Set<string>();
  const raw = (workflow || "").trim();
  if (!raw) {
    return uuids;
  }
  try {
    const parsed = JSON.parse(raw) as { nodes?: unknown };
    if (Array.isArray(parsed.nodes)) {
      for (const node of parsed.nodes) {
        const id = String(node ?? "").trim().toLowerCase();
        if (id && id !== "s" && id !== "e") {
          uuids.add(id);
        }
      }
    }
  } catch {
    const uuidRe =
      /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;
    for (const match of raw.matchAll(uuidRe)) {
      uuids.add(match[0].toLowerCase());
    }
  }
  return uuids;
}

function aggregateWorkflowCrud(
  workflow: string,
  workNodes: WorkNodeItem[],
): Array<"c" | "r" | "u" | "d"> {
  const referenced = collectWorkUuidsFromWorkflowDoc(workflow);
  if (referenced.size === 0) {
    return [];
  }
  const byUuid = new Map(
    workNodes.map((node) => [node.uuid.trim().toLowerCase(), node]),
  );
  const merged = new Set<string>();
  for (const uuid of referenced) {
    const node = byUuid.get(uuid);
    if (!node) {
      continue;
    }
    if ((node.worker || "agent").toLowerCase() === "hitl") {
      continue;
    }
    for (const ch of normalizeCrudFlags(node.crud)) {
      merged.add(ch);
    }
  }
  return CRUD_BADGE_META.map((item) => item.key).filter((key) => merged.has(key));
}

interface WorkflowPageProps {
  agents: AgentInfo[];
  user: AuthUser;
  onChatComplete: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function resolveWorkflowAgentId(agents: AgentInfo[]): string {
  const hit = agents.find((agent) => {
    const id = agent.id.trim();
    return id === WORKFLOW_AGENT_ID || id.toUpperCase().includes(WORKFLOW_AGENT_ID);
  });
  if (!hit?.id.trim()) {
    throw new Error("WORKFLOW_AGENT를 찾을 수 없습니다.");
  }
  return hit.id.trim();
}

async function streamWorkflowAgentChat(params: {
  agentId: string;
  userid: string;
  message: string;
  sessionId: string;
  workflowUuid?: string | null;
}): Promise<string> {
  const response = await fetch(`/api/agents/${encodeURIComponent(params.agentId)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: params.message,
      userid: params.userid,
      session_id: params.sessionId,
      workflow_uuid: params.workflowUuid || undefined,
    }),
  });

  if (!response.ok) {
    throw new Error((await response.text()) || `HTTP ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("스트리밍 응답을 받지 못했습니다.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let assistantText = "";

  const applyEvents = (events: ReturnType<typeof parseSseChunk>["events"]) => {
    for (const event of events) {
      if (event.event === "error") {
        const payload = JSON.parse(event.data) as { message?: string };
        throw new Error(payload.message || "에이전트 호출에 실패했습니다.");
      }
      if (event.event !== "token") {
        continue;
      }
      const payload = JSON.parse(event.data) as { content: string };
      assistantText += payload.content;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      const parsed = parseSseChunk(buffer, decoder.decode(value, { stream: true }));
      buffer = parsed.remainder;
      applyEvents(parsed.events);
    }
    if (done) {
      applyEvents(flushSseBuffer(buffer));
      break;
    }
  }

  const finalText = assistantText.trim();
  if (!finalText) {
    throw new Error("에이전트가 빈 응답을 반환했습니다.");
  }
  return finalText;
}

export function WorkflowPage({ agents, user, onChatComplete }: WorkflowPageProps) {
  const [isListCollapsed, setIsListCollapsed] = useState(false);
  const [items, setItems] = useState<WorkflowItem[]>([]);
  const [workNodes, setWorkNodes] = useState<WorkNodeItem[]>([]);
  const [selectedUuid, setSelectedUuid] = useState<string | null>(null);
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  /** Stable across create→edit after first AI/manual save so the editor is not remounted. */
  const [editorSessionKey, setEditorSessionKey] = useState("idle");
  const [error, setError] = useState<string | null>(null);
  const [aiImportRequest, setAiImportRequest] = useState<{
    nonce: number;
    assistantText: string;
  } | null>(null);
  const [diagramAgentEvent, setDiagramAgentEvent] = useState<DiagramAgentEvent | null>(null);
  const diagramAwaitingRef = useRef(false);
  const agentSessionIdRef = useRef(createSessionId());
  const generateAbortRef = useRef<AbortController | null>(null);

  const [billingConfirmPrompt, setBillingConfirmPrompt] = useState<string | null>(null);
  const [billingConfirmModel, setBillingConfirmModel] = useState<string | null>(null);

  const [runningUuid, setRunningUuid] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const selected = items.find((item) => item.uuid === selectedUuid) ?? null;

  const pushDiagramAgentEvent = useCallback((kind: DiagramAgentEvent["kind"], content: string) => {
    setDiagramAgentEvent((current) => ({
      nonce: (current?.nonce ?? 0) + 1,
      kind,
      content,
    }));
  }, []);

  const applyAssistantWorkflowPayload = useCallback(
    (content: string) => {
      const awaitingDiagram = diagramAwaitingRef.current;
      try {
        parseAiWorkflowDesignResponse(content);
      } catch (err) {
        const looksLikeJson = content.trim().startsWith("{");
        if (awaitingDiagram) {
          diagramAwaitingRef.current = false;
          if (looksLikeJson) {
            const message =
              err instanceof Error
                ? `AI 작업 워크플로우 파싱 실패: ${err.message}`
                : "AI 작업 워크플로우 파싱에 실패했습니다.";
            setError(message);
            pushDiagramAgentEvent("error", message);
          } else {
            setError(null);
            pushDiagramAgentEvent("clarify", content);
          }
          return;
        }
        if (looksLikeJson) {
          setError(
            err instanceof Error
              ? `AI 작업 워크플로우 파싱 실패: ${err.message}`
              : "AI 작업 워크플로우 파싱에 실패했습니다.",
          );
        }
        return;
      }

      setError(null);
      if (awaitingDiagram) {
        diagramAwaitingRef.current = false;
        pushDiagramAgentEvent("success", content);
      }
      setMode((current) => {
        if (current === "idle") {
          setSelectedUuid(null);
          setEditorSessionKey(`create-${Date.now()}`);
          return "create";
        }
        return current;
      });
      setAiImportRequest((current) => ({
        nonce: (current?.nonce ?? 0) + 1,
        assistantText: content,
      }));
    },
    [pushDiagramAgentEvent],
  );

  const handleAiImportHandled = useCallback(() => {
    setAiImportRequest(null);
  }, []);

  const handleDiagramAgentEventHandled = useCallback(() => {
    setDiagramAgentEvent(null);
  }, []);

  const runWorkflowAgent = useCallback(
    async (prompt: string) => {
      diagramAwaitingRef.current = true;
      try {
        const agentId = resolveWorkflowAgentId(agents);
        const content = await streamWorkflowAgentChat({
          agentId,
          userid: user.userid,
          message: prompt,
          sessionId: agentSessionIdRef.current,
          workflowUuid: selectedUuid,
        });
        applyAssistantWorkflowPayload(content);
        onChatComplete();
      } catch (err) {
        if (!diagramAwaitingRef.current) {
          return;
        }
        diagramAwaitingRef.current = false;
        const message =
          err instanceof Error ? err.message : "작업 워크플로우 생성 요청에 실패했습니다.";
        setError(message);
        pushDiagramAgentEvent("error", message);
      }
    },
    [
      agents,
      applyAssistantWorkflowPayload,
      onChatComplete,
      pushDiagramAgentEvent,
      selectedUuid,
      user.userid,
    ],
  );

  const handleDiagramGenerate = useCallback(
    async (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed) {
        return;
      }

      try {
        const billingStatus = await fetchLlmBillingStatus();
        if (billingStatus.requires_confirmation) {
          setBillingConfirmModel(billingStatus.model);
          setBillingConfirmPrompt(trimmed);
          return;
        }
      } catch {
        // 상태 조회 실패 시 로컬 LLM으로 간주하고 진행
      }

      await runWorkflowAgent(trimmed);
    },
    [runWorkflowAgent],
  );

  const handleBillingConfirm = useCallback(() => {
    const prompt = billingConfirmPrompt?.trim() ?? "";
    setBillingConfirmPrompt(null);
    setBillingConfirmModel(null);
    if (!prompt) {
      return;
    }
    void runWorkflowAgent(prompt);
  }, [billingConfirmPrompt, runWorkflowAgent]);

  const handleBillingCancel = useCallback(() => {
    setBillingConfirmPrompt(null);
    setBillingConfirmModel(null);
    diagramAwaitingRef.current = false;
    // Editor already entered STATE_GENERATE before billing prompt — release it.
    pushDiagramAgentEvent("error", "작업 워크플로우 생성이 취소되었습니다.");
  }, [pushDiagramAgentEvent]);

  const beginCreateSession = useCallback(() => {
    setSelectedUuid(null);
    setEditorSessionKey(`create-${Date.now()}`);
    agentSessionIdRef.current = createSessionId();
    setMode("create");
  }, []);

  const beginEditSession = useCallback((uuid: string) => {
    setSelectedUuid(uuid);
    setEditorSessionKey(`edit-${uuid}`);
    agentSessionIdRef.current = createSessionId();
    setMode("edit");
  }, []);

  const loadWorkflows = useCallback(async () => {
    const response = await fetch("/api/workflows");
    if (!response.ok) {
      throw new Error(await parseError(response, "작업 워크플로우 목록을 불러오지 못했습니다."));
    }
    setItems((await response.json()) as WorkflowItem[]);
  }, []);

  const loadWorkNodes = useCallback(async () => {
    const response = await fetch("/api/work-nodes");
    if (!response.ok) {
      throw new Error(await parseError(response, "작업노드 목록을 불러오지 못했습니다."));
    }
    setWorkNodes((await response.json()) as WorkNodeItem[]);
  }, []);

  const refreshWorkflowData = useCallback(async () => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
  }, [loadWorkflows, loadWorkNodes]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        await Promise.all([loadWorkflows(), loadWorkNodes()]);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "목록을 불러오지 못했습니다.");
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [loadWorkflows, loadWorkNodes]);

  const hasDbRunning =
    items.some(
      (item) =>
        Boolean(item.awaiting_approval) ||
        isRunInProgress(item.last_start_date, item.last_end_date),
    ) || workNodes.some((node) => isRunInProgress(node.last_start_date, node.last_end_date));

  useEffect(() => {
    if (!hasDbRunning && runningUuid == null) {
      return;
    }
    const timer = window.setInterval(() => {
      void Promise.all([loadWorkflows(), loadWorkNodes()]).catch(() => {
        /* 폴링 중 일시 오류는 무시 */
      });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [hasDbRunning, runningUuid, loadWorkflows, loadWorkNodes]);

  useEffect(() => {
    return () => {
      generateAbortRef.current?.abort();
    };
  }, []);

  const handleSaved = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    // Keep editorSessionKey so create→edit after AI generate does not remount the editor.
    setSelectedUuid(item.uuid);
    setMode("edit");
  };

  const handleDistributed = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedUuid(item.uuid);
    setMode("edit");
  };

  const handleCloned = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    beginEditSession(item.uuid);
    setRunMessage(`"${item.workflow_name}" 으로 복제되었습니다.`);
  };

  const handleDeleteWorkflow = async (item: WorkflowItem) => {
    const confirmed = window.confirm(
      `"${item.workflow_name}" 작업 워크플로우를 삭제하시겠습니까?\n참조하는 작업노드도 함께 삭제됩니다.`,
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    setRunMessage(null);
    try {
      const response = await fetch(`/api/workflows/${item.uuid}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 워크플로우 삭제에 실패했습니다."));
      }
      await Promise.all([loadWorkflows(), loadWorkNodes()]);
      if (selectedUuid === item.uuid) {
        setSelectedUuid(null);
        setMode("idle");
        setEditorSessionKey("idle");
      }
      setRunMessage(`"${item.workflow_name}" 을(를) 삭제했습니다.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 워크플로우 삭제에 실패했습니다.");
    }
  };

  const handleRunWorkflow = async (item: WorkflowItem) => {
    const confirmed = window.confirm(
      `"${item.workflow_name}" 작업 워크플로우를 실행하시겠습니까?`,
    );
    if (!confirmed) {
      return;
    }
    setRunningUuid(item.uuid);
    setError(null);
    setRunMessage(null);
    try {
      const response = await fetch(`/api/workflows/${item.uuid}/run`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 워크플로우 실행에 실패했습니다."));
      }
      const payload = (await response.json()) as {
        status?: string;
        message?: string;
        workflow?: WorkflowItem;
      };
      await Promise.all([loadWorkflows(), loadWorkNodes()]);
      setRunMessage(payload.message || "실행이 완료되었습니다.");
      if (payload.workflow) {
        beginEditSession(payload.workflow.uuid);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 워크플로우 실행에 실패했습니다.");
    } finally {
      setRunningUuid(null);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 items-stretch gap-4">
      <div className="flex min-h-0 min-w-0 flex-1 gap-4 self-stretch">
        <WorkflowListPanel
          collapsed={isListCollapsed}
          onCollapsedChange={setIsListCollapsed}
          onCreate={() => {
            beginCreateSession();
          }}
        >
          {error ? <p className="text-xs text-rose-300">{error}</p> : null}
          {runMessage ? <p className="text-xs text-emerald-300">{runMessage}</p> : null}
          <div className="flex w-full flex-col gap-3">
            {items.length === 0 && !error ? (
              <p className="text-xs text-slate-500">등록된 작업 워크플로우가 없습니다.</p>
            ) : null}
            {items.map((item) => {
              const isActive = selectedUuid === item.uuid && mode === "edit";
              const tested = Boolean(item.test_result);
              const ownerName = (item.owner_username || "").trim();
              const isMine = (item.owner ?? 0) === user.idx;
              const isDistributed = Boolean(item.distribute);
              const dbRunning = isRunInProgress(item.last_start_date, item.last_end_date);
              const isAwaitingApproval = Boolean(item.awaiting_approval);
              const isRunning = runningUuid === item.uuid || dbRunning || isAwaitingApproval;
              const canRun = !dbRunning && !isAwaitingApproval;
              const crudFlags = aggregateWorkflowCrud(item.workflow, workNodes);
              return (
                <div
                  key={item.uuid}
                  className={`flex min-h-[76px] w-full flex-col justify-center gap-1 overflow-hidden rounded-xl border bg-slate-900/90 px-3 py-2 text-left shadow-lg ${
                    isActive ? "border-sky-500" : "border-slate-700"
                  } ${isRunning ? "wf-run-pulse" : ""}`}
                  aria-busy={isRunning || undefined}
                >
                  <div className="flex min-w-0 items-start gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        beginEditSession(item.uuid);
                      }}
                      className="min-w-0 flex-1 text-left"
                    >
                      <h2
                        className="min-w-0 truncate text-sm font-semibold text-slate-100"
                        title={item.workflow_name}
                      >
                        {item.workflow_name}
                      </h2>
                    </button>
                    {isMine ? (
                      <button
                        type="button"
                        title="작업 워크플로우 삭제"
                        aria-label="작업 워크플로우 삭제"
                        disabled={isRunning || runningUuid != null}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleDeleteWorkflow(item);
                        }}
                        className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-transparent text-slate-300 hover:bg-rose-950/60 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <WorkflowIcon name="delete" size="xs" label="삭제" />
                      </button>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      beginEditSession(item.uuid);
                    }}
                    className="flex min-w-0 w-full flex-col gap-1 text-left"
                  >
                    <div className="flex min-w-0 items-center justify-between gap-2">
                      <p
                        className="min-w-0 truncate text-[11px] text-slate-400"
                        title={item.create_date || undefined}
                      >
                        {item.create_date || "생성일 없음"}
                      </p>
                      {crudFlags.length > 0 ? (
                        <div className="flex shrink-0 items-center gap-1">
                          {CRUD_BADGE_META.filter((meta) => crudFlags.includes(meta.key)).map(
                            (meta) => (
                              <span
                                key={meta.key}
                                title={meta.label}
                                className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-slate-500 bg-slate-900/80 px-1 text-[10px] font-semibold uppercase tracking-wide text-slate-100"
                              >
                                {meta.key.toUpperCase()}
                              </span>
                            ),
                          )}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex min-w-0 items-center gap-1.5 text-[11px] text-slate-300">
                      <span aria-hidden="true" className="inline-flex">
                        {tested ? (
                          <WorkflowIcon name="approve" size="sm" />
                        ) : (
                          <WorkflowIcon name="list" size="sm" className="opacity-40" />
                        )}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        {tested ? item.validate_date || "검증됨" : "테스트 미실행"}
                      </span>
                      {isRunning ? (
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-rose-500/80 bg-rose-950/70 px-2 py-0.5 text-[10px] font-semibold text-rose-100">
                          <WorkflowIcon
                            name={isAwaitingApproval ? "approve" : "run"}
                            size="xs"
                          />
                          {isAwaitingApproval ? "승인 대기" : "실행 중"}
                        </span>
                      ) : null}
                      {isDistributed ? (
                        <span
                          title="배포됨"
                          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-sky-600/70 bg-sky-950/60 px-2 py-0.5 text-[10px] font-medium text-sky-100"
                        >
                          <WorkflowIcon name="distribute" size="xs" label="배포" />
                          배포
                        </span>
                      ) : null}
                      {item.cron ? (
                        <span
                          title={`스케줄: ${describeCronExpr(item.cron_expr)} (${item.cron_expr || ""})`}
                          className="inline-flex shrink-0 items-center gap-1 truncate rounded-full border border-violet-600/70 bg-violet-950/50 px-2 py-0.5 text-[10px] font-medium text-violet-100"
                        >
                          <WorkflowIcon name="history" size="xs" label="스케줄" />
                          {describeCronExpr(item.cron_expr)}
                        </span>
                      ) : null}
                      {ownerName ? (
                        <span
                          title={isMine ? "내 작업 워크플로우" : `소유자: ${ownerName}`}
                          className="inline-flex max-w-[40%] shrink-0 items-center gap-1 truncate rounded-full border border-slate-600 bg-slate-900/80 px-2.5 py-1 text-center text-[11px] font-medium text-slate-200"
                        >
                          <WorkflowIcon name="owner" size="xs" />
                          {isMine ? "나" : ownerName}
                        </span>
                      ) : null}
                    </div>
                  </button>
                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      disabled={!canRun || isRunning || runningUuid != null}
                      title={canRun ? "작업 워크플로우 실행" : "실행할 수 없는 상태입니다"}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleRunWorkflow(item);
                      }}
                      className="inline-flex items-center gap-1 rounded-md border border-emerald-700 bg-emerald-950/50 px-2.5 py-1 text-[11px] font-medium text-emerald-100 hover:bg-emerald-900/60 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <WorkflowIcon name="run" size="xs" label="실행" />
                      {isRunning ? "실행 중…" : "실행"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </WorkflowListPanel>

        <WorkflowDesignPanel
          mode={mode}
          selected={selected}
          workNodes={workNodes}
          user={user}
          editorSessionKey={editorSessionKey}
          onSaved={handleSaved}
          onWorkNodesChanged={refreshWorkflowData}
          onDistributed={handleDistributed}
          onCloned={handleCloned}
          aiImportRequest={aiImportRequest}
          onAiImportHandled={handleAiImportHandled}
          diagramAgentEvent={diagramAgentEvent}
          onDiagramAgentEventHandled={handleDiagramAgentEventHandled}
          onDiagramGenerate={(prompt) => {
            void handleDiagramGenerate(prompt);
          }}
        />
      </div>

      {billingConfirmPrompt ? (
        <OpenAiBillingConfirmDialog
          prompt={billingConfirmPrompt}
          model={billingConfirmModel}
          onConfirm={handleBillingConfirm}
          onCancel={handleBillingCancel}
        />
      ) : null}
    </div>
  );
}
