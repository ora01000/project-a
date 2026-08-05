import { useCallback, useEffect, useRef, useState } from "react";

import type { AuthUser } from "../types/auth";
import { WHATAP_EVENT_LOG_SOURCE } from "../types/agent-log";
import { AgentLogsPanel } from "./AgentLogsPanel";

interface DetailInfoPanelProps {
  currentUser: AuthUser;
  activeTab?: DetailTab;
  onActiveTabChange?: (tab: DetailTab) => void;
}

type DetailTab = "logs" | "whatap";

const TABS: { id: DetailTab; label: string }[] = [
  { id: "logs", label: "대화로그" },
  { id: "whatap", label: "Whatap 이벤트 수신" },
];

const GENERAL_LOG_EXCLUDE_AGENT_IDS = [WHATAP_EVENT_LOG_SOURCE];
const DEFAULT_HEIGHT = 500;
const MIN_HEIGHT = 200;
const MAX_HEIGHT_RATIO = 0.85;

export function DetailInfoPanel({
  currentUser,
  activeTab: controlledActiveTab,
  onActiveTabChange,
}: DetailInfoPanelProps) {
  const [internalActiveTab, setInternalActiveTab] = useState<DetailTab>("logs");
  const activeTab = controlledActiveTab ?? internalActiveTab;
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(DEFAULT_HEIGHT);

  const setActiveTab = (tab: DetailTab) => {
    if (onActiveTabChange) {
      onActiveTabChange(tab);
      return;
    }
    setInternalActiveTab(tab);
  };

  const clampHeight = useCallback((nextHeight: number) => {
    const maxHeight = Math.max(MIN_HEIGHT, window.innerHeight * MAX_HEIGHT_RATIO);
    return Math.min(maxHeight, Math.max(MIN_HEIGHT, nextHeight));
  }, []);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isDraggingRef.current) {
        return;
      }

      const deltaY = startYRef.current - event.clientY;
      setHeight(clampHeight(startHeightRef.current + deltaY));
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [clampHeight]);

  const handleResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    isDraggingRef.current = true;
    startYRef.current = event.clientY;
    startHeightRef.current = height;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  };

  return (
    <section
      className="flex shrink-0 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg"
      style={{ height }}
    >
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="패널 높이 조절"
        onMouseDown={handleResizeStart}
        className="group flex h-2 shrink-0 cursor-row-resize items-center justify-center border-b border-slate-700 bg-slate-900 hover:bg-slate-800"
      >
        <span className="h-1 w-12 rounded-full bg-slate-600 group-hover:bg-slate-400" />
      </div>

      <header className="shrink-0 border-b border-slate-700 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-200">상세 정보</h2>
      </header>

      <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-700 px-3 pt-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`shrink-0 rounded-t-md px-3 py-2 text-xs font-medium ${
              activeTab === tab.id
                ? "border border-b-0 border-slate-600 bg-slate-800 text-sky-200"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden overscroll-contain flex flex-col p-4">
        {activeTab === "whatap" ? (
          <AgentLogsPanel
            currentUser={currentUser}
            agentId={WHATAP_EVENT_LOG_SOURCE}
            emptyMessage="표시할 Whatap 이벤트가 없습니다."
            loadingMessage="Whatap 이벤트 로그를 불러오는 중..."
            errorMessage="Whatap 이벤트 로그를 불러오지 못했습니다."
          />
        ) : (
          <AgentLogsPanel
            currentUser={currentUser}
            excludeAgentIds={GENERAL_LOG_EXCLUDE_AGENT_IDS}
          />
        )}
      </div>
    </section>
  );
}

export type { DetailTab };
