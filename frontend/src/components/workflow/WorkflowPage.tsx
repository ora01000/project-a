import { useCallback, useEffect, useRef, useState } from "react";

import type { AgentInfo } from "../../types/agent";
import type { AuthUser } from "../../types/auth";
import type { WorkflowItem, WorkNodeItem } from "../../types/workflow";
import { IntegratedChatPanel } from "../IntegratedChatPanel";
import { WorkflowDesignPanel } from "./WorkflowDesignPanel";
import { WorkflowListPanel } from "./WorkflowListPanel";

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
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [mode, setMode] = useState<"idle" | "create" | "edit">("idle");
  const [createKey, setCreateKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const selected = items.find((item) => item.idx === selectedIdx) ?? null;

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

  const handleSaved = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedIdx(item.idx);
    setMode("edit");
  };

  const handleCheckedIn = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedIdx(item.idx);
    setMode("edit");
  };

  const handleCheckedOut = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedIdx(item.idx);
    setMode("edit");
  };

  const handleRestored = async (item: WorkflowItem) => {
    await Promise.all([loadWorkflows(), loadWorkNodes()]);
    setSelectedIdx(item.idx);
    setMode("edit");
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
                setSelectedIdx(null);
                setCreateKey((current) => current + 1);
                setMode("create");
              }}
            >
              {error ? <p className="text-xs text-rose-300">{error}</p> : null}
              <div className="flex w-full flex-col gap-3">
                {items.length === 0 && !error ? (
                  <p className="text-xs text-slate-500">등록된 워크플로우가 없습니다.</p>
                ) : null}
                {items.map((item) => {
                  const isActive = selectedIdx === item.idx && mode === "edit";
                  const tested = Boolean(item.test_result);
                  const checkinName = (item.checkin_username || "").trim();
                  const hasCheckin = Boolean(item.checkin_user && item.checkin_user > 0 && checkinName);
                  return (
                    <button
                      key={item.idx}
                      type="button"
                      onClick={() => {
                        setSelectedIdx(item.idx);
                        setMode("edit");
                      }}
                      className={`flex min-h-[76px] w-full flex-col justify-center gap-1 overflow-hidden rounded-xl border bg-slate-900/90 px-3 py-2 text-left shadow-lg ${
                        isActive ? "border-sky-500" : "border-slate-700"
                      }`}
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
                  : `wf-${selectedIdx ?? "none"}-${selected?.checkin_time || "out"}-${selected?.is_draft ? "d" : "c"}`
              }
              onSaved={handleSaved}
              onWorkNodesChanged={loadWorkNodes}
              onCheckedIn={handleCheckedIn}
              onCheckedOut={handleCheckedOut}
              onRestored={handleRestored}
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
      />
    </div>
  );
}
