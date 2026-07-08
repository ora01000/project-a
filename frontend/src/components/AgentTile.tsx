import type { AgentInfo } from "../types/agent";
import { ChatPanel } from "./ChatPanel";

interface AgentTileProps {
  agent: AgentInfo;
}

function statusColor(status: string): string {
  if (status === "connected") {
    return "bg-emerald-500";
  }
  if (status === "partial") {
    return "bg-amber-500";
  }
  if (status === "disabled") {
    return "bg-amber-500";
  }
  return "bg-rose-500";
}

export function AgentTile({ agent }: AgentTileProps) {
  const isDisabled = agent.status === "disabled";

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg">
      <div className="border-b border-slate-700 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-slate-100">{agent.name}</h2>
            <p className="text-sm text-slate-400">{agent.role}</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className={`h-2 w-2 rounded-full ${statusColor(agent.status)}`} />
            <span>{agent.status}</span>
          </div>
        </div>
        <p className="mt-1 text-xs text-slate-500">MCP: {agent.mcp_servers.join(", ")}</p>
      </div>

      <div className="flex-1 p-3">
        <ChatPanel agentId={agent.id} disabled={isDisabled} />
      </div>
    </div>
  );
}
