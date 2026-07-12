import type { AgentInfo } from "../types/agent";
import { connectionStatusDotClass } from "../utils/agentStatusStyle";

interface AgentTileProps {
  agent: AgentInfo;
}

function operationStatusColor(status: AgentInfo["operation_status"]): string {
  if (status === "working") {
    return "bg-emerald-500";
  }
  if (status === "idle") {
    return "bg-amber-500";
  }
  return "bg-rose-500";
}

function formatTokenCount(value: number): string {
  return value.toLocaleString("ko-KR");
}

export function AgentTile({ agent }: AgentTileProps) {
  return (
    <div className="flex w-[500px] flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg">
      <div className="border-b border-slate-700 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-slate-100">{agent.name}</h2>
            <p className="text-sm text-slate-400">{agent.role}</p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${connectionStatusDotClass(agent.status)}`} />
              <span>연결 {agent.status}</span>
            </div>
            <div
              className="flex items-center gap-2"
              title={agent.operation_error ? `오류 원인: ${agent.operation_error}` : undefined}
            >
              <span
                className={`h-2 w-2 rounded-full ${operationStatusColor(agent.operation_status)}`}
              />
              <span>동작 {agent.operation_status}</span>
            </div>
          </div>
        </div>
        <p className="mt-1 text-xs text-slate-500">MCP: {agent.mcp_servers.join(", ")}</p>
      </div>

      <div className="px-4 py-3">
        <div className="mb-2 text-xs text-slate-400">토큰 사용량</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
          <span>입력 {formatTokenCount(agent.input_tokens)}</span>
          <span>출력 {formatTokenCount(agent.output_tokens)}</span>
        </div>
      </div>
    </div>
  );
}
