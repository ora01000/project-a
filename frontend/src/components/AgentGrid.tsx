import type { AgentInfo } from "../types/agent";
import { AgentTile } from "./AgentTile";

interface AgentGridProps {
  agents: AgentInfo[];
}

export function AgentGrid({ agents }: AgentGridProps) {
  return (
    <div className="grid w-full grid-cols-[repeat(auto-fill,500px)] justify-start gap-4">
      {agents.map((agent) => (
        <AgentTile key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
