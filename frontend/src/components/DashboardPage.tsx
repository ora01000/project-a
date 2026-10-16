import { useCallback, useEffect, useRef, useState } from "react";

import type { AgentInfo } from "../types/agent";
import type { AuthUser } from "../types/auth";
import { DetailInfoPanel, type DetailTab } from "./DetailInfoPanel";
import { IntegratedChatPanel } from "./IntegratedChatPanel";
import { JobNotesPanel } from "./JobNotesPanel";

const DEFAULT_CHAT_PANEL_WIDTH = 650;
/** QHD(2560)의 80% 이상일 때 대화형 터미널을 50% 확장 */
const WIDE_CHAT_PANEL_WIDTH = Math.round(DEFAULT_CHAT_PANEL_WIDTH * 1.5);
const FHD_VIEWPORT_WIDTH = 1920;
const QHD_WIDE_THRESHOLD = Math.round(2560 * 0.8); // 2048
const MIN_CHAT_PANEL_WIDTH = 360;
const MIN_JOB_NOTES_PANEL_WIDTH = 240;
const PANEL_RESIZE_HANDLE_WIDTH = 1;

function resolveInitialChatPanelWidth(viewportWidth: number): number {
  // FHD 이하: 현행 유지 / QHD 80% 이상: 50% 확장 / 그 사이: 현행 유지
  if (viewportWidth <= FHD_VIEWPORT_WIDTH) {
    return DEFAULT_CHAT_PANEL_WIDTH;
  }
  if (viewportWidth >= QHD_WIDE_THRESHOLD) {
    return WIDE_CHAT_PANEL_WIDTH;
  }
  return DEFAULT_CHAT_PANEL_WIDTH;
}

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
  const [chatPanelWidth, setChatPanelWidth] = useState(() =>
    resolveInitialChatPanelWidth(window.innerWidth),
  );
  const isResizingRef = useRef(false);
  const resizeStartXRef = useRef(0);
  const resizeStartWidthRef = useRef(chatPanelWidth);

  const minCenterPanelWidth = MIN_JOB_NOTES_PANEL_WIDTH;

  const clampChatPanelWidth = useCallback(
    (nextWidth: number) => {
      const containerWidth = splitLayoutRef.current?.clientWidth ?? window.innerWidth;
      const maxWidth = Math.max(
        MIN_CHAT_PANEL_WIDTH,
        containerWidth - minCenterPanelWidth - PANEL_RESIZE_HANDLE_WIDTH - 8,
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
  }, [clampChatPanelWidth]);

  const [detailTab, setDetailTab] = useState<DetailTab>("workflow");

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

      <div ref={splitLayoutRef} className="flex min-h-0 flex-1 items-stretch gap-1">
        {!integratedChatFullscreen ? (
          <>
            <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 self-stretch">
              <div className="flex min-h-0 flex-1 gap-4">
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
              className="group relative z-10 w-px shrink-0 cursor-col-resize self-stretch bg-slate-700 transition-colors hover:bg-sky-500"
            >
              {/* 레이아웃은 1px만 차지하고, 드래그 히트 영역만 좌우로 확장 */}
              <span
                aria-hidden
                className="absolute inset-y-0 -left-1.5 -right-1.5"
              />
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
          onCopyToNote={handleCopyToNote}
        />
      </div>
    </>
  );
}
