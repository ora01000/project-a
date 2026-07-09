import type { AgentInfo, HealthInfo } from "../types/agent";
import { AgentGrid } from "./AgentGrid";
import { AgentNodeListPanel } from "./AgentNodeListPanel";
import { DetailInfoPanel } from "./DetailInfoPanel";
import { IntegratedChatPanel } from "./IntegratedChatPanel";

interface DashboardPageProps {
  agents: AgentInfo[];
  health: HealthInfo | null;
  error: string | null;
  integratedChatFullscreen: boolean;
  onToggleIntegratedChatFullscreen: () => void;
  onChatComplete: () => void;
}

export function DashboardPage({
  agents,
  health,
  error,
  integratedChatFullscreen,
  onToggleIntegratedChatFullscreen,
  onChatComplete,
}: DashboardPageProps) {
  return (
    <>
      {error ? (
        <div className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 items-stretch gap-4">
        {!integratedChatFullscreen ? (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 self-stretch">
            <AgentNodeListPanel>
              {agents.length > 0 ? <AgentGrid agents={agents} /> : null}
            </AgentNodeListPanel>

            <DetailInfoPanel agents={agents} health={health} />
          </div>
        ) : null}

        <IntegratedChatPanel
          agents={agents}
          isFullscreen={integratedChatFullscreen}
          onToggleFullscreen={onToggleIntegratedChatFullscreen}
          onChatComplete={onChatComplete}
        />
      </div>
    </>
  );
}
