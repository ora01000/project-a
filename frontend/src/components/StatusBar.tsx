import type { HealthInfo } from "../types/agent";
import { isHealthyConnectionStatus } from "../utils/agentStatusStyle";

interface StatusBarProps {
  health: HealthInfo | null;
}

const MCP_LABELS: Record<string, string> = {
  kubernetes: "MCP Kubernetes",
  kubectl_ai: "MCP kubectl_ai",
  kubevirt: "MCP Kubevirt",
  vcenter: "MCP vcenter",
  ansible: "MCP ansible",
};

const MCP_DISPLAY_ORDER = ["kubernetes", "kubectl_ai", "kubevirt", "vcenter", "ansible"];

function mcpLabel(name: string): string {
  return MCP_LABELS[name] ?? `MCP ${name}`;
}

function statusButtonClass(value: string | null): string {
  const base =
    "cursor-default rounded-md border px-2.5 py-1 text-xs font-medium transition";
  if (value == null) {
    return `${base} border-slate-700 bg-slate-800 text-slate-400`;
  }
  if (isHealthyConnectionStatus(value) || value === "ok") {
    return `${base} border-emerald-700/70 bg-emerald-950/70 text-emerald-200`;
  }
  if (value === "partial" || value === "disabled") {
    return `${base} border-amber-700/70 bg-amber-950/70 text-amber-200`;
  }
  return `${base} border-rose-700/70 bg-rose-950/70 text-rose-200`;
}

function orderedMcpEntries(mcp: Record<string, string>): [string, string][] {
  const remaining = new Set(Object.keys(mcp));
  const ordered: [string, string][] = [];
  for (const key of MCP_DISPLAY_ORDER) {
    if (remaining.has(key)) {
      ordered.push([key, mcp[key]]);
      remaining.delete(key);
    }
  }
  for (const key of [...remaining].sort()) {
    ordered.push([key, mcp[key]]);
  }
  return ordered;
}

export function StatusBar({ health }: StatusBarProps) {
  if (!health) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" tabIndex={-1} className={statusButtonClass(null)}>
            API
          </button>
          <button type="button" tabIndex={-1} className={statusButtonClass(null)}>
            LLM
          </button>
          {MCP_DISPLAY_ORDER.map((name) => (
            <button key={name} type="button" tabIndex={-1} className={statusButtonClass(null)}>
              {mcpLabel(name)}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2" role="list" aria-label="연결 상태">
        <button
          type="button"
          tabIndex={-1}
          className={statusButtonClass(health.status)}
          title={`API: ${health.status}`}
          role="listitem"
        >
          API
        </button>
        <button
          type="button"
          tabIndex={-1}
          className={statusButtonClass(health.llm)}
          title={`LLM: ${health.llm}`}
          role="listitem"
        >
          LLM
        </button>
        {orderedMcpEntries(health.mcp).map(([name, status]) => (
          <button
            key={name}
            type="button"
            tabIndex={-1}
            className={statusButtonClass(status)}
            title={`${mcpLabel(name)}: ${status}`}
            role="listitem"
          >
            {mcpLabel(name)}
          </button>
        ))}
      </div>
    </div>
  );
}
