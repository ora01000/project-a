import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AuthUser } from "../types/auth";
import { WHATAP_EVENT_LOG_SOURCE } from "../types/agent-log";
import { hasAdminAccess } from "../types/user";
import { AgentLogsPanel } from "./AgentLogsPanel";
import { JobMgmtTab } from "./jobs/JobMgmtTab";
import { JobWorkflowPanel } from "./JobWorkflowPanel";

interface DetailInfoPanelProps {
  currentUser: AuthUser;
  activeTab?: DetailTab;
  onActiveTabChange?: (tab: DetailTab) => void;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
}

type DetailTab = "logs" | "whatap" | "workflow" | "job-mgmt";

const ALL_TABS: { id: DetailTab; label: string; adminOnly?: boolean }[] = [
  { id: "workflow", label: "작업 진행" },
  { id: "whatap", label: "Whatap 이벤트 감지" },
  { id: "logs", label: "대화로그" },
  { id: "job-mgmt", label: "작업 관리" },
];

const GENERAL_LOG_EXCLUDE_AGENT_IDS = [WHATAP_EVENT_LOG_SOURCE, "WORKFLOW_AGENT"];
const DEFAULT_HEIGHT = 400;
const MIN_HEIGHT = 200;
const MAX_HEIGHT_RATIO = 0.85;
const COLLAPSED_HEIGHT = 36;

function PanelCollapseDownIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 15h18" />
      <path d="M9 9l3 3 3-3" />
    </svg>
  );
}

export function DetailInfoPanel({
  currentUser,
  activeTab: controlledActiveTab,
  onActiveTabChange,
  collapsed: controlledCollapsed,
  onCollapsedChange,
}: DetailInfoPanelProps) {
  const [internalActiveTab, setInternalActiveTab] = useState<DetailTab>("workflow");
  const activeTab = controlledActiveTab ?? internalActiveTab;
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const [uncontrolledCollapsed, setUncontrolledCollapsed] = useState(true);
  const isCollapsed = controlledCollapsed ?? uncontrolledCollapsed;
  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(DEFAULT_HEIGHT);
  const isAdmin = hasAdminAccess(currentUser.role);
  const visibleTabs = useMemo(
    () => ALL_TABS.filter((tab) => !tab.adminOnly || isAdmin),
    [isAdmin],
  );

  const setActiveTab = (tab: DetailTab) => {
    if (onActiveTabChange) {
      onActiveTabChange(tab);
      return;
    }
    setInternalActiveTab(tab);
  };

  useEffect(() => {
    if (visibleTabs.some((tab) => tab.id === activeTab)) {
      return;
    }
    setActiveTab("workflow");
  }, [activeTab, visibleTabs]);

  const setCollapsed = (next: boolean) => {
    if (controlledCollapsed === undefined) {
      setUncontrolledCollapsed(next);
    }
    onCollapsedChange?.(next);
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
    if (isCollapsed) {
      return;
    }
    event.preventDefault();
    isDraggingRef.current = true;
    startYRef.current = event.clientY;
    startHeightRef.current = height;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  };

  return (
    <div
      className="relative w-full shrink-0 overflow-hidden transition-[height] duration-300 ease-in-out"
      style={{ height: isCollapsed ? COLLAPSED_HEIGHT : height }}
    >
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        aria-label="상세 정보 펼치기"
        aria-hidden={!isCollapsed}
        tabIndex={isCollapsed ? 0 : -1}
        className={`absolute inset-x-0 bottom-0 z-20 flex h-9 items-center justify-center rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg transition-opacity duration-300 hover:border-slate-500 hover:bg-slate-800/90 ${
          isCollapsed ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        <span className="select-none text-xs font-semibold tracking-wide text-slate-200">
          상세 정보
        </span>
      </button>

      <section
        aria-hidden={isCollapsed}
        className={`absolute inset-x-0 top-0 flex w-full flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg transition-transform duration-300 ease-in-out ${
          isCollapsed ? "pointer-events-none translate-y-full" : "translate-y-0"
        }`}
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

        <div className="flex shrink-0 items-end gap-2 border-b border-slate-700 px-3 pt-2">
          <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
            {visibleTabs.map((tab) => (
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
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            aria-label="상세 정보 접기"
            title="패널 접기"
            className="mb-1.5 shrink-0 rounded-md border border-slate-700 bg-slate-800/60 p-1.5 text-slate-400 transition-colors hover:border-slate-500 hover:bg-slate-800 hover:text-slate-200"
          >
            <PanelCollapseDownIcon />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden overscroll-contain p-4">
          {activeTab === "workflow" ? (
            <JobWorkflowPanel currentUser={currentUser} active={activeTab === "workflow"} />
          ) : activeTab === "whatap" ? (
            <AgentLogsPanel
              currentUser={currentUser}
              agentId={WHATAP_EVENT_LOG_SOURCE}
              emptyMessage="표시할 Whatap 이벤트가 없습니다."
              loadingMessage="Whatap 이벤트 로그를 불러오는 중..."
              errorMessage="Whatap 이벤트 로그를 불러오지 못했습니다."
            />
          ) : activeTab === "job-mgmt" ? (
            <JobMgmtTab active={activeTab === "job-mgmt"} currentUser={currentUser} />
          ) : (
            <AgentLogsPanel
              currentUser={currentUser}
              excludeAgentIds={GENERAL_LOG_EXCLUDE_AGENT_IDS}
            />
          )}
        </div>
      </section>
    </div>
  );
}

export type { DetailTab };
