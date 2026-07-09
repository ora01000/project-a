import { useCallback, useEffect, useRef, useState } from "react";

import type { AgentInfo, HealthInfo } from "../types/agent";
import { TopologyMap } from "./TopologyMap";

interface DetailInfoPanelProps {
  agents: AgentInfo[];
  health: HealthInfo | null;
}

type DetailTab = "topology" | "logs";

const DEFAULT_HEIGHT = 500;
const MIN_HEIGHT = 200;
const MAX_HEIGHT_RATIO = 0.85;

export function DetailInfoPanel({ agents, health }: DetailInfoPanelProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>("topology");
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(DEFAULT_HEIGHT);

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

      <div className="flex shrink-0 gap-1 border-b border-slate-700 px-3 pt-2">
        <button
          type="button"
          onClick={() => setActiveTab("topology")}
          className={`rounded-t-md px-3 py-2 text-xs font-medium ${
            activeTab === "topology"
              ? "border border-b-0 border-slate-600 bg-slate-800 text-sky-200"
              : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
          }`}
        >
          Topology 맵
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("logs")}
          className={`rounded-t-md px-3 py-2 text-xs font-medium ${
            activeTab === "logs"
              ? "border border-b-0 border-slate-600 bg-slate-800 text-sky-200"
              : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
          }`}
        >
          로그
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {activeTab === "topology" ? (
          <TopologyMap agents={agents} health={health} embedded />
        ) : (
          <div className="flex h-full min-h-[120px] items-center justify-center rounded-md border border-dashed border-slate-700 bg-slate-950/40 text-sm text-slate-500">
            표시할 로그가 없습니다.
          </div>
        )}
      </div>
    </section>
  );
}
