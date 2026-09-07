import { useCallback, useEffect, useRef, useState } from "react";

import type { AgentInfo } from "../../types/agent";
import type { AuthUser } from "../../types/auth";
import type { WorkflowItem, WorkNodeItem } from "../../types/workflow";
import { IntegratedChatPanel } from "../IntegratedChatPanel";
import { parseAiWorkflowDesignResponse } from "./aiWorkflowParse";
import { WorkflowDesignPanel } from "./WorkflowDesignPanel";
import { WorkflowListPanel } from "./WorkflowListPanel";
import { isRunInProgress } from "./workflowModel";

const DEFAULT_CHAT_PANEL_WIDTH = 650;
const MIN_CHAT_PANEL_WIDTH = 360;
const LIST_PANEL_WIDTH = 280;
const LIST_COLLAPSED_WIDTH = 36;
const MIN_DESIGN_PANEL_WIDTH = 240;
const PANEL_RESIZE_HANDLE_WIDTH = 8;

interface WorkflowPageProps {
  agents: AgentInfo[];
  user: AuthUser;
  integratedChatFullscreen: boolean;
  onToggleIntegratedChatFullscreen: () => void;
  onChatComplete: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

export function WorkflowPage({
  agents,
  user,
  integratedChatFullscreen,
  onToggleIntegratedChatFullscreen,
  onChatComplete,
}: WorkflowPageProps) {
  const splitLayoutRef = useRef<HTMLDivElement>(null);
  const [chatPanelWidth, setChatPanelWidth] = useState(DEFAULT_CHAT_PANEL_WIDTH);
  const [isListCollapsed, setIsListCollapsed] = useState(false);
  const isResizingRef = useRef(false);
  const resizeStartXRef = useRef(0);
  const resizeStartWidthRef = useRef(DEFAULT_CHAT_PANEL_WIDTH);

  const [items, setItems] = useState<WorkflowItem[]>([]);
  const [workNodes, setWorkNodes] = useState<WorkNodeItem[]>([]);
  const [selectedUuid, setSelectedUuid] = useState<string | null>(null);
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  const [createKey, setCreateKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [aiImportRequest, setAiImportRequest] = useState<{
    nonce: number;
    assistantText: string;
  } | null>(null);

  const [runningUuid, setRunningUuid] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const selected = items.find((item) => item.uuid === selectedUuid) ?? null;

  const handleAssistantResponse = useCallback((payload: { agentId: string; content: string }) => {
    const agentId = payload.agentId.trim();
    const isWorkflowAgent =
      agentId === "WORKFLOW_AGENT" || agentId.toUpperCase().includes("WORKFLOW_AGENT");
    if (!isWorkflowAgent) {
      return;
    }
    try {
      parseAiWorkflowDesignResponse(payload.content);
    } catch (err) {
      const looksLikeJson = payload.content.trim().startsWith("{");
      if (looksLikeJson) {
        setError(
          err instanceof Error
            ? `AI 워크플로우 파싱 실패: ${err.message}`
            : "AI 워크플로우 파싱에 실패했습니다.",
        );
      }
      // 보충 질문(비 JSON)이면 무시
      return;
    }
    setError(null);
    setMode((current) => {
      if (current === "idle") {
        setSelectedUuid(null);
        setCreateKey((key) => key + 1);
        return "create";
      }
      return current;
    });
    setAiImportRequest((current) => ({
      nonce: (current?.nonce ?? 0) + 1,
      assistantText: payload.content,
    }));
  }, []);

  const handleAiImportHandled = useCallback(() => {
    setAiImportRequest(null);
  }, []);

  const minCenterPanelWidth =
    (isListCollapsed ? LIST_COLLAPSED_WIDTH : LIST_PANEL_WIDTH) + MIN_DESIGN_PANEL_WIDTH;

  const clampChatPanelWidth = useCallback(
    (nextWidth: number) => {
      const containerWidth = splitLayoutRef.current?.clientWidth ?? window.innerWidth;
      const maxWidth = Math.max(
        MIN_CHAT_PANEL_WIDTH,
        containerWidth - minCenterPanelWidth - PANEL_RESIZE_HANDLE_WIDTH - 16,
      );
      return Math.min(maxWidth, Math.max(MIN_CHAT_PANEL_WIDTH, nextWidth));
    },
    [minCenterPanelWidth],
  );

  const handlePanelResizeStart = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault();
      isResizingRef.current = true;
      resizeStartXRef.current = event.clientX;
      resizeStartWidthRef.current = chatPanelWidth;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [chatPanelWidth],
  );

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isResizingRef.current) {
        return;
      }
      const deltaX = resizeStartXRef.current - event.clientX;
      setChatPanelWidth(clampChatPanelWidth(resizeStartWidthRef.current + deltaX));
    };
    const handleMouseUp = () => {
      if (!isResizingRef.current) {
        return;
      }
      isResizingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [clampChatPanelWidth]);

  useEffect(() => {
    const handleWindowResize = () => {
      setChatPanelWidth((current) => clampChatPanelWidth(current));
    };
    window.addEventListener("resize", handleWindowResize);
    return () => window.removeEventListener("resize", handleWindowResize);
  }, [clampChatPanelWidth]);

  useEffect(() => {
    setChatPanelWidth((current) => clampChatPanelWidth(current));
  }, [clampChatPanelWidth, isListCollapsed]);

  const loadWorkflows = useCallback(async () => {
    const response = await fetch("/api/workflows");
    if (!response.ok) {
      throw new Error(await parseError(response, "워크플로우 목록을 불러오지 못했습니다."));
    }
    const data = (await response.json()) as WorkflowItem[];
    setItems(data);
  }, []);

  const loadWorkNodes = useCallback(async () => {
    const response = await fetch("/api/work-nodes");
    if (!response.ok) {
      throw new Error(await parseError(response, "워크 노드를 불러오지 못했습니다."));
    }
    setWorkNodes((await response.json()) as WorkNodeItem[]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        await Promise.all([loadWorkflows(), loadWorkNodes()]);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "워크플로우를 불러오지 못했습니다.");
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

  const handleSaved = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedUuid(item.uuid);
    setMode("edit");
  };

  const handleCheckedIn = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedUuid(item.uuid);
    setMode("edit");
  };

  const handleCheckedOut = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedUuid(item.uuid);
    setMode("edit");
  };

  const handleRestored = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedUuid(item.uuid);
    setMode("edit");
  };

  const handleRunWorkflow = async (item: WorkflowItem) => {
    const checkedIn = Boolean(item.checkin_user && item.checkin_user > 0);
    if (checkedIn) {
      setError("체크인 중인 워크플로우는 실행할 수 없습니다. 체크아웃 후 실행하세요.");
      return;
    }
    const confirmed = window.confirm(
      `"${item.workflow_name}" 워크플로우를 실행하시겠습니까?`,
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
        throw new Error(await parseError(response, "워크플로우 실행에 실패했습니다."));
      }
      const payload = (await response.json()) as {
        status?: string;
        message?: string;
        workflow?: WorkflowItem;
      };
      await Promise.all([loadWorkflows(), loadWorkNodes()]);
      setRunMessage(payload.message || "실행이 완료되었습니다.");
      if (payload.workflow) {
        setSelectedUuid(payload.workflow.uuid);
        setMode("edit");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "워크플로우 실행에 실패했습니다.");
    } finally {
      setRunningUuid(null);
    }
  };

  return (
    <div ref={splitLayoutRef} className="flex min-h-0 flex-1 items-stretch gap-4">
      {!integratedChatFullscreen ? (
        <>
          <div className="flex min-h-0 min-w-0 flex-1 gap-4 self-stretch">
            <WorkflowListPanel
              collapsed={isListCollapsed}
              onCollapsedChange={setIsListCollapsed}
              onCreate={() => {
                setSelectedUuid(null);
                setCreateKey((current) => current + 1);
                setMode("create");
              }}
            >
              {error ? <p className="text-xs text-rose-300">{error}</p> : null}
              {runMessage ? <p className="text-xs text-emerald-300">{runMessage}</p> : null}
              <div className="flex w-full flex-col gap-3">
                {items.length === 0 && !error ? (
                  <p className="text-xs text-slate-500">등록된 워크플로우가 없습니다.</p>
                ) : null}
                {items.map((item) => {
                  const isActive = selectedUuid === item.uuid && mode === "edit";
                  const tested = Boolean(item.test_result);
                  const checkinName = (item.checkin_username || "").trim();
                  const hasCheckin = Boolean(item.checkin_user && item.checkin_user > 0 && checkinName);
                  const dbRunning = isRunInProgress(item.last_start_date, item.last_end_date);
                  const isAwaitingApproval = Boolean(item.awaiting_approval);
                  const isRunning = runningUuid === item.uuid || dbRunning || isAwaitingApproval;
                  const canRun =
                    !Boolean(item.checkin_user && item.checkin_user > 0) &&
                    !dbRunning &&
                    !isAwaitingApproval;
                  return (
                    <div
                      key={item.uuid}
                      className={`flex min-h-[76px] w-full flex-col justify-center gap-1 overflow-hidden rounded-xl border bg-slate-900/90 px-3 py-2 text-left shadow-lg ${
                        isActive ? "border-sky-500" : "border-slate-700"
                      } ${isRunning ? "wf-run-pulse" : ""}`}
                      aria-busy={isRunning || undefined}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedUuid(item.uuid);
                          setMode("edit");
                        }}
                        className="flex w-full flex-col gap-1 text-left"
                      >
                        <h2 className="truncate text-sm font-semibold text-slate-100" title={item.workflow_name}>
                          {item.workflow_name}
                        </h2>
                        <p className="truncate text-[11px] text-slate-400" title={item.create_date || undefined}>
                          {item.create_date || "생성일 없음"}
                        </p>
                        <div className="flex min-w-0 items-center gap-1.5 text-[11px] text-slate-300">
                          <span aria-hidden="true">{tested ? "✅" : "⬜"}</span>
                          <span className="min-w-0 flex-1 truncate">
                            {tested ? item.validate_date || "검증됨" : "테스트 미실행"}
                          </span>
                          {isRunning ? (
                            <span className="shrink-0 rounded-full border border-rose-500/80 bg-rose-950/70 px-2 py-0.5 text-[10px] font-semibold text-rose-100">
                              {isAwaitingApproval ? "승인 대기" : "실행 중"}
                            </span>
                          ) : null}
                          {hasCheckin ? (
                            <span
                              title={`Check-In: ${checkinName}`}
                              className="inline-block max-w-[40%] shrink-0 truncate rounded-full border border-slate-600 bg-slate-900/80 px-2.5 py-1 text-center text-[11px] font-medium text-slate-200"
                            >
                              {checkinName}
                            </span>
                          ) : null}
                        </div>
                      </button>
                      <div className="flex justify-end pt-1">
                        <button
                          type="button"
                          disabled={!canRun || isRunning || runningUuid != null}
                          title={
                            canRun
                              ? "워크플로우 실행"
                              : "체크아웃 상태에서만 실행할 수 있습니다"
                          }
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleRunWorkflow(item);
                          }}
                          className="rounded-md border border-emerald-700 bg-emerald-950/50 px-2.5 py-1 text-[11px] font-medium text-emerald-100 hover:bg-emerald-900/60 disabled:cursor-not-allowed disabled:opacity-40"
                        >
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
              editorKey={
                mode === "create"
                  ? `create-${createKey}`
                  : `wf-${selectedUuid ?? "none"}-${selected?.checkin_time || "out"}-${selected?.is_draft ? "d" : "c"}`
              }
              onSaved={handleSaved}
              onWorkNodesChanged={loadWorkNodes}
              onCheckedIn={handleCheckedIn}
              onCheckedOut={handleCheckedOut}
              onRestored={handleRestored}
              aiImportRequest={aiImportRequest}
              onAiImportHandled={handleAiImportHandled}
            />
          </div>

          <button
            type="button"
            aria-label="패널 가로 비율 조절"
            onMouseDown={handlePanelResizeStart}
            className="group flex w-2 shrink-0 cursor-col-resize items-center justify-center self-stretch rounded-md border border-transparent hover:border-slate-600 hover:bg-slate-800/60"
          >
            <span className="h-12 w-1 rounded-full bg-slate-600 group-hover:bg-slate-400" />
          </button>
        </>
      ) : null}

      <IntegratedChatPanel
        agents={agents}
        user={user}
        isFullscreen={integratedChatFullscreen}
        panelWidth={chatPanelWidth}
        onToggleFullscreen={onToggleIntegratedChatFullscreen}
        onChatComplete={onChatComplete}
        allowedAgentIds={["WORKFLOW_AGENT"]}
        expandUserInput
        userInputHeightPx={300}
        onAssistantResponse={handleAssistantResponse}
      />
    </div>
  );
}
