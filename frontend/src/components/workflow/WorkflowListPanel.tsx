import { useState, type ReactNode } from "react";

import { WorkflowIcon } from "./WorkflowIcon";

interface WorkflowListPanelProps {
  children: ReactNode;
  className?: string;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  onCreate: () => void;
}

function PanelCollapseIcon() {
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
      <path d="M9 4v16" />
      <path d="M15 9l-3 3 3 3" />
    </svg>
  );
}

export function WorkflowListPanel({
  children,
  className = "",
  collapsed: controlledCollapsed,
  onCollapsedChange,
  onCreate,
}: WorkflowListPanelProps) {
  const [uncontrolledCollapsed, setUncontrolledCollapsed] = useState(false);
  const isCollapsed = controlledCollapsed ?? uncontrolledCollapsed;

  const setCollapsed = (next: boolean) => {
    if (controlledCollapsed === undefined) {
      setUncontrolledCollapsed(next);
    }
    onCollapsedChange?.(next);
  };

  return (
    <div
      className={`relative flex min-h-0 shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out ${
        isCollapsed ? "w-9" : "w-[280px]"
      } ${className}`.trim()}
    >
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        aria-label="작업 워크플로우 목록 펼치기"
        aria-hidden={!isCollapsed}
        tabIndex={isCollapsed ? 0 : -1}
        className={`absolute inset-y-0 left-0 z-20 flex w-9 flex-col items-center justify-center rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner transition-opacity duration-300 hover:border-slate-500 hover:bg-slate-800/70 ${
          isCollapsed ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        <span className="select-none text-xs font-semibold tracking-wide text-slate-200 [writing-mode:vertical-rl]">
          작업 워크플로우 목록
        </span>
      </button>

      <section
        aria-hidden={isCollapsed}
        className={`relative flex h-full w-[280px] min-h-0 min-w-0 flex-col transition-transform duration-300 ease-in-out ${
          isCollapsed ? "pointer-events-none -translate-x-full" : "translate-x-0"
        }`}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner"
        />

        <div className="relative z-10 flex min-h-0 flex-1 flex-col">
          <header className="flex shrink-0 items-start justify-between gap-2 border-b border-slate-700/80 px-4 py-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-200">작업 워크플로우 목록</h2>
              <p className="mt-0.5 text-xs text-slate-500">등록된 작업 워크플로우를 선택합니다.</p>
            </div>
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              aria-label="작업 워크플로우 목록 접기"
              title="패널 접기"
              className="shrink-0 rounded-md border border-slate-700 bg-slate-800/60 p-1.5 text-slate-400 transition-colors hover:border-slate-500 hover:bg-slate-800 hover:text-slate-200"
            >
              <PanelCollapseIcon />
            </button>
          </header>

          <div className="shrink-0 px-4 pt-3">
            <button
              type="button"
              onClick={onCreate}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-sky-700 bg-sky-950/50 px-3 py-2 text-sm font-medium text-sky-100 hover:bg-sky-900/60"
            >
              <WorkflowIcon name="edit" size="sm" label="새로운 작업 워크플로우" />
              새로운 작업 워크플로우
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">{children}</div>
        </div>
      </section>
    </div>
  );
}
