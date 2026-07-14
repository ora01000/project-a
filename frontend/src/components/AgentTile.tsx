import type { AgentInfo } from "../types/agent";
import { connectionStatusDotClass } from "../utils/agentStatusStyle";

interface AgentTileProps {
  agent: AgentInfo;
}

export const AGENT_TILE_WIDTH_PX = 280;
export const AGENT_TILE_HEIGHT_PX = 148;

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
    <div
      className="flex shrink-0 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg"
      style={{ width: AGENT_TILE_WIDTH_PX, height: AGENT_TILE_HEIGHT_PX, minWidth: AGENT_TILE_WIDTH_PX, minHeight: AGENT_TILE_HEIGHT_PX }}
    >
      <div className="shrink-0 border-b border-slate-700 px-3 py-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold text-slate-100" title={agent.name}>
              {agent.name}
            </h2>
            <p className="truncate text-xs text-slate-400" title={agent.role}>
              {agent.role}
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1 text-[11px] text-slate-400">
            <div className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${connectionStatusDotClass(agent.status)}`} />
              <span>연결 {agent.status}</span>
            </div>
            <div
              className="flex items-center gap-1.5"
              title={agent.operation_error ? `오류 원인: ${agent.operation_error}` : undefined}
            >
              <span
                className={`h-2 w-2 rounded-full ${operationStatusColor(agent.operation_status)}`}
              />
              <span>동작 {agent.operation_status}</span>
            </div>
          </div>
        </div>
        <p className="mt-1 truncate text-[11px] text-slate-500" title={agent.mcp_servers.join(", ")}>
          MCP: {agent.mcp_servers.join(", ") || "-"}
        </p>
      </div>

      <div className="flex min-h-0 flex-1 flex-col justify-center px-3 py-2">
        <div className="mb-1 text-[11px] text-slate-400">토큰 사용량</div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
          <span>입력 {formatTokenCount(agent.input_tokens)}</span>
          <span>출력 {formatTokenCount(agent.output_tokens)}</span>
        </div>
      </div>
    </div>
  );
}
