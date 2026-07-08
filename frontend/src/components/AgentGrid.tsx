import type { AgentInfo } from "../types/agent";
import { AgentTile } from "./AgentTile";

interface AgentGridProps {
  agents: AgentInfo[];
}

export function AgentGrid({ agents }: AgentGridProps) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,500px)] justify-start gap-4">
      {agents.map((agent) => (
        <div key={agent.id} className="w-[500px]">
          <AgentTile agent={agent} />
        </div>
      ))}
    </div>
  );
}
