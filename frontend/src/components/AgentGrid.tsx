import type { AgentInfo } from "../types/agent";
import { AGENT_TILE_WIDTH_PX, AgentTile } from "./AgentTile";

interface AgentGridProps {
  agents: AgentInfo[];
}

export function AgentGrid({ agents }: AgentGridProps) {
  return (
    <div
      className="grid w-full items-start justify-start gap-4"
      style={{
        gridTemplateColumns: `repeat(auto-fill, ${AGENT_TILE_WIDTH_PX}px)`,
      }}
    >
      {agents.map((agent) => (
        <AgentTile key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
