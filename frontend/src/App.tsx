import { useEffect, useState } from "react";

import { TopologyProvider } from "./context/TopologyContext";
import { AgentGrid } from "./components/AgentGrid";
import { MenuBar } from "./components/MenuBar";
import { StatusBar } from "./components/StatusBar";
import { TopologyMap } from "./components/TopologyMap";
import type { AgentInfo, HealthInfo } from "./types/agent";

export default function App() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [agentsResponse, healthResponse] = await Promise.all([
          fetch("/api/agents"),
          fetch("/api/health"),
        ]);

        if (!agentsResponse.ok || !healthResponse.ok) {
          throw new Error("백엔드 API에 연결할 수 없습니다.");
        }

        const agentsData = (await agentsResponse.json()) as AgentInfo[];
        const healthData = (await healthResponse.json()) as HealthInfo;
        setAgents(agentsData);
        setHealth(healthData);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    };

    load();
    const interval = window.setInterval(load, 15000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <TopologyProvider>
      <div className="min-h-screen bg-slate-950 px-6 py-6">
        <header className="mb-4">
          <h1 className="text-2xl font-bold text-slate-100">LangGraph Multi-Agent Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">
            화면 크기에 따라 에이전트 타일이 자동으로 배치됩니다.
          </p>
        </header>

        <MenuBar />

        <div className="mb-4">
          <StatusBar health={health} />
        </div>

        {error ? (
          <div className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        {agents.length > 0 ? <AgentGrid agents={agents} /> : null}

        <TopologyMap agents={agents} health={health} />
      </div>
    </TopologyProvider>
  );
}
