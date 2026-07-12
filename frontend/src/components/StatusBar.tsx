import type { HealthInfo } from "../types/agent";

interface StatusBarProps {
  health: HealthInfo | null;
}

import { isHealthyConnectionStatus } from "../utils/agentStatusStyle";

function statusBadge(value: string): string {
  if (isHealthyConnectionStatus(value) || value === "ok") {
    return "text-emerald-300";
  }
  if (value === "disabled") {
    return "text-amber-300";
  }
  return "text-rose-300";
}

export function StatusBar({ health }: StatusBarProps) {
  if (!health) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-400">
        상태 확인 중...
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-4">
        <span>
          API: <span className={statusBadge(health.status)}>{health.status}</span>
        </span>
        <span>
          LLM: <span className={statusBadge(health.llm)}>{health.llm}</span>
        </span>
        {Object.entries(health.mcp).map(([name, status]) => (
          <span key={name}>
            MCP {name}: <span className={statusBadge(status)}>{status}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
