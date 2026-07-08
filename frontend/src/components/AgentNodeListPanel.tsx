import type { ReactNode } from "react";

interface AgentNodeListPanelProps {
  children: ReactNode;
}

export function AgentNodeListPanel({ children }: AgentNodeListPanelProps) {
  return (
    <section className="relative flex min-h-0 min-w-0 flex-1 flex-col">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner"
      />

      <div className="relative z-10 flex min-h-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-slate-700/80 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-200">에이전트 노드 목록</h2>
          <p className="mt-0.5 text-xs text-slate-500">등록된 에이전트 노드를 확인하고 관리합니다.</p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">{children}</div>
      </div>
    </section>
  );
}
