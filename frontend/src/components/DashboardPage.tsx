import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AgentInfo } from "../types/agent";
import type { AuthUser } from "../types/auth";
import { AgentGrid } from "./AgentGrid";
import { AgentNodeListPanel } from "./AgentNodeListPanel";
import { DetailInfoPanel, type DetailTab } from "./DetailInfoPanel";
import { IntegratedChatPanel } from "./IntegratedChatPanel";
import { JobNotesPanel } from "./JobNotesPanel";

const DEFAULT_CHAT_PANEL_WIDTH = 650;
const MIN_CHAT_PANEL_WIDTH = 360;
const AGENT_LIST_PANEL_WIDTH = 280;
const AGENT_LIST_COLLAPSED_WIDTH = 36;
const MIN_JOB_NOTES_PANEL_WIDTH = 240;
const PANEL_RESIZE_HANDLE_WIDTH = 8;

interface DashboardPageProps {
  agents: AgentInfo[];
  error: string | null;
  user: AuthUser;
  integratedChatFullscreen: boolean;
  onToggleIntegratedChatFullscreen: () => void;
  onChatComplete: () => void;
}

export function DashboardPage({
  agents,
  error,
  user,
  integratedChatFullscreen,
  onToggleIntegratedChatFullscreen,
  onChatComplete,
}: DashboardPageProps) {
  const splitLayoutRef = useRef<HTMLDivElement>(null);
  const copyToNoteRef = useRef<(content: string, noteName?: string) => Promise<void>>(
    async () => {},
  );
  const [chatPanelWidth, setChatPanelWidth] = useState(DEFAULT_CHAT_PANEL_WIDTH);
  const [isAgentListCollapsed, setIsAgentListCollapsed] = useState(false);
  const [isChatCollapsed, setIsChatCollapsed] = useState(true);
  const isResizingRef = useRef(false);
  const resizeStartXRef = useRef(0);
  const resizeStartWidthRef = useRef(DEFAULT_CHAT_PANEL_WIDTH);

  const minCenterPanelWidth =
    (isAgentListCollapsed ? AGENT_LIST_COLLAPSED_WIDTH : AGENT_LIST_PANEL_WIDTH) +
    MIN_JOB_NOTES_PANEL_WIDTH;

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
  }, [clampChatPanelWidth, isAgentListCollapsed, isChatCollapsed]);

  const [detailTab, setDetailTab] = useState<DetailTab>("workflow");

  const assignedAgents = useMemo(() => {
    const assignedIds = new Set(
      (user.agent_ids ?? []).map((id) => id.trim()).filter(Boolean),
    );
    return agents.filter((agent) => assignedIds.has(agent.id));
  }, [agents, user.agent_ids]);

  const handleCopyToNoteReady = useCallback(
    (handler: (content: string, noteName?: string) => Promise<void>) => {
      copyToNoteRef.current = handler;
    },
    [],
  );

  const handleCopyToNote = useCallback((content: string, noteName?: string) => {
    return copyToNoteRef.current(content, noteName);
  }, []);

  return (
    <>
      {error ? (
        <div className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div ref={splitLayoutRef} className="flex min-h-0 flex-1 items-stretch gap-4">
        {!integratedChatFullscreen ? (
          <>
            <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 self-stretch">
              <div className="flex min-h-0 flex-1 gap-4">
                <AgentNodeListPanel
                  collapsed={isAgentListCollapsed}
                  onCollapsedChange={setIsAgentListCollapsed}
                >
                  {assignedAgents.length > 0 ? <AgentGrid agents={assignedAgents} /> : null}
                </AgentNodeListPanel>

                <JobNotesPanel
                  className="min-w-0 flex-1"
                  currentUser={user}
                  onCopyToNoteReady={handleCopyToNoteReady}
                />
              </div>

              <DetailInfoPanel
                currentUser={user}
                activeTab={detailTab}
                onActiveTabChange={setDetailTab}
              />
            </div>

            <button
              type="button"
              aria-label="패널 가로 비율 조절"
              onMouseDown={handlePanelResizeStart}
              disabled={isChatCollapsed}
              className={`group flex w-2 shrink-0 cursor-col-resize items-center justify-center self-stretch rounded-md border border-transparent hover:border-slate-600 hover:bg-slate-800/60 ${
                isChatCollapsed ? "pointer-events-none opacity-0" : ""
              }`}
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
          collapsed={isChatCollapsed}
          onCollapsedChange={setIsChatCollapsed}
          onToggleFullscreen={onToggleIntegratedChatFullscreen}
          onChatComplete={onChatComplete}
          onCopyToNote={handleCopyToNote}
        />
      </div>
    </>
  );
}
