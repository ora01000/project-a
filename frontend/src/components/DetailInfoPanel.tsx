import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AgentInfo, HealthInfo } from "../types/agent";
import type { JobDetailTab } from "../types/job";
import { ROLE_ADMIN } from "../types/user";
import { AgentLogsPanel } from "./AgentLogsPanel";
import { PromptDebugPanel } from "./PromptDebugPanel";
import { JobWorkPanel } from "./jobs/JobWorkPanel";
import { TopologyMap } from "./TopologyMap";

interface DetailInfoPanelProps {
  agents: AgentInfo[];
  health: HealthInfo | null;
  viewerRole: number;
  activeTab?: DetailTab;
  onActiveTabChange?: (tab: DetailTab) => void;
}

type DetailTab = "topology" | "logs" | "debug" | JobDetailTab;

const BASE_TABS: { id: DetailTab; label: string }[] = [
  { id: "topology", label: "Topology 맵" },
  { id: "logs", label: "로그" },
  { id: "review", label: "검토 작업" },
  { id: "pending", label: "보류 작업" },
  { id: "completed", label: "완료 작업" },
];

const DEFAULT_HEIGHT = 500;
const MIN_HEIGHT = 200;
const MAX_HEIGHT_RATIO = 0.85;

export function DetailInfoPanel({
  agents,
  health,
  viewerRole,
  activeTab: controlledActiveTab,
  onActiveTabChange,
}: DetailInfoPanelProps) {
  const isAdmin = viewerRole === ROLE_ADMIN;
  const tabs = useMemo(() => {
    if (!isAdmin) {
      return BASE_TABS;
    }
    return [...BASE_TABS, { id: "debug" as const, label: "디버깅" }];
  }, [isAdmin]);

  const [internalActiveTab, setInternalActiveTab] = useState<DetailTab>("topology");
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

  useEffect(() => {
    if (!isAdmin && activeTab === "debug") {
      if (onActiveTabChange) {
        onActiveTabChange("topology");
      } else {
        setInternalActiveTab("topology");
      }
    }
  }, [activeTab, isAdmin, onActiveTabChange]);

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
        {tabs.map((tab) => (
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

      <div
        className={`min-h-0 flex-1 overscroll-contain p-4 ${
          activeTab === "topology" || activeTab === "debug"
            ? "flex flex-col overflow-hidden"
            : "overflow-y-auto"
        }`}
      >
        {activeTab === "topology" ? (
          <TopologyMap agents={agents} health={health} embedded />
        ) : activeTab === "logs" ? (
          <AgentLogsPanel />
        ) : activeTab === "debug" && isAdmin ? (
          <PromptDebugPanel agents={agents} />
        ) : (
          <JobWorkPanel key={activeTab} tab={activeTab as JobDetailTab} />
        )}
      </div>
    </section>
  );
}

export type { DetailTab };
