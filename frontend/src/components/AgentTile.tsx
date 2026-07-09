import type { AgentInfo } from "../types/agent";

interface AgentTileProps {
  agent: AgentInfo;
}

function statusColor(status: string): string {
  if (status === "connected") {
    return "bg-emerald-500";
  }
  if (status === "partial" || status === "disabled") {
    return "bg-amber-500";
  }
  return "bg-rose-500";
}

function usageBarColor(percent: number): string {
  if (percent >= 90) {
    return "bg-rose-500";
  }
  if (percent >= 70) {
    return "bg-amber-500";
  }
  return "bg-sky-500";
}

function formatTokenCount(value: number): string {
  return value.toLocaleString("ko-KR");
}

export function AgentTile({ agent }: AgentTileProps) {
  const usagePercent = Math.min(100, Math.max(0, agent.token_usage_percent));

  return (
    <div className="flex w-[500px] flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg">
      <div className="border-b border-slate-700 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-slate-100">{agent.name}</h2>
            <p className="text-sm text-slate-400">{agent.role}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-xs text-slate-400">
            <span className={`h-2 w-2 rounded-full ${statusColor(agent.status)}`} />
            <span>{agent.status}</span>
          </div>
        </div>
        <p className="mt-1 text-xs text-slate-500">MCP: {agent.mcp_servers.join(", ")}</p>
      </div>

      <div className="px-4 py-3">
        <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
          <span>토큰 사용량</span>
          <span className="font-medium text-slate-200">{usagePercent.toFixed(1)}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full rounded-full transition-all ${usageBarColor(usagePercent)}`}
            style={{ width: `${usagePercent}%` }}
          />
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
          <span>입력 {formatTokenCount(agent.input_tokens)}</span>
          <span>출력 {formatTokenCount(agent.output_tokens)}</span>
          <span>
            합계 {formatTokenCount(agent.total_tokens)} / {formatTokenCount(agent.max_context_tokens)}
          </span>
        </div>
      </div>
    </div>
  );
}
