import type { AgentInfo } from "../types/agent";
import { AgentTile } from "./AgentTile";

interface AgentGridProps {
  agents: AgentInfo[];
}

export function AgentGrid({ agents }: AgentGridProps) {
  return (
    <div className="flex w-full flex-col gap-3">
      {agents.map((agent) => (
        <AgentTile key={agent.id} agent={agent} stacked />
      ))}
    </div>
  );
}
