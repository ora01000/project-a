import type { AgentInfo } from "../types/agent";
import { connectionStatusDotClass } from "../utils/agentStatusStyle";

interface AgentTileProps {
  agent: AgentInfo;
  stacked?: boolean;
}

export const AGENT_TILE_WIDTH_PX = 280;
export const AGENT_TILE_HEIGHT_PX = 108;

function operationStatusColor(status: AgentInfo["operation_status"]): string {
  if (status === "working") {
    return "bg-emerald-500";
  }
  if (status === "idle") {
    return "bg-amber-500";
  }
  return "bg-rose-500";
}

function resolveOperationDetails(agent: AgentInfo): string[] {
  if (agent.operation_details && agent.operation_details.length > 0) {
    return agent.operation_details;
  }
  if (agent.operation_detail?.trim()) {
    return [agent.operation_detail.trim()];
  }
  return [];
}

export function AgentTile({ agent, stacked = false }: AgentTileProps) {
  const operationDetails = resolveOperationDetails(agent);
  const activeCount = agent.active_count ?? operationDetails.length;
  const operationStatusLabel =
    agent.operation_status === "working" && activeCount > 1
      ? `working (${activeCount})`
      : agent.operation_status;

  return (
    <div
      className="flex shrink-0 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg"
      style={
        stacked
          ? {
              width: "100%",
              minHeight: AGENT_TILE_HEIGHT_PX,
            }
          : {
              width: AGENT_TILE_WIDTH_PX,
              height: AGENT_TILE_HEIGHT_PX,
              minWidth: AGENT_TILE_WIDTH_PX,
              minHeight: AGENT_TILE_HEIGHT_PX,
            }
      }
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
              <span>동작 {operationStatusLabel}</span>
            </div>
          </div>
        </div>
      </div>

      {agent.operation_status === "working" && operationDetails.length > 0 ? (
        <div className="flex min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-2">
          <ul className="min-w-0 space-y-1">
            {operationDetails.map((detail, index) => (
              <li
                key={`${index}-${detail}`}
                className="rounded border border-emerald-800/60 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200"
                title={detail}
              >
                <span className="line-clamp-2 break-words">{detail}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
