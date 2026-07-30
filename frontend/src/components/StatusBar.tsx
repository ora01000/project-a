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

const RUNTIME_MODE_LABELS: Record<string, string> = {
  mock: "Runtime (mock)",
  http: "Runtime (sandbox)",
  local: "Runtime (mock)",
};

function runtimeModeLabel(mode: string | undefined): string {
  if (!mode) {
    return "Runtime";
  }
  return RUNTIME_MODE_LABELS[mode] ?? `Runtime (${mode})`;
}

function runtimeModeClass(mode: string | undefined): string {
  const base =
    "cursor-default rounded-md border px-2.5 py-1 text-xs font-medium transition";
  if (mode === "http") {
    return `${base} border-sky-700/70 bg-sky-950/70 text-sky-200`;
  }
  return `${base} border-amber-700/70 bg-amber-950/70 text-amber-200`;
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
  if (value === "partial" || value === "disabled" || value === "degraded") {
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
          <button type="button" tabIndex={-1} className={runtimeModeClass(undefined)}>
            Runtime
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
          className={statusButtonClass(health.runtime_status)}
          title={`${runtimeModeLabel(health.runtime_mode)}: ${health.runtime_status}`}
          role="listitem"
        >
          {runtimeModeLabel(health.runtime_mode)}
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
