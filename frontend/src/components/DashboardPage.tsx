import { useCallback, useEffect, useMemo, useState } from "react";

import type { AgentInfo, HealthInfo } from "../types/agent";
import type { AuthUser } from "../types/auth";
import type { SignupNotification } from "../types/signup";
import { ROLE_ADMIN } from "../types/user";
import { AgentGrid } from "./AgentGrid";
import { AgentNodeListPanel } from "./AgentNodeListPanel";
import { DetailInfoPanel, type DetailTab } from "./DetailInfoPanel";
import { IntegratedChatPanel } from "./IntegratedChatPanel";

interface DashboardPageProps {
  agents: AgentInfo[];
  health: HealthInfo | null;
  error: string | null;
  user: AuthUser;
  integratedChatFullscreen: boolean;
  onToggleIntegratedChatFullscreen: () => void;
  onChatComplete: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function mergeSignupNotifications(...lists: SignupNotification[][]): SignupNotification[] {
  const byId = new Map<number, SignupNotification>();
  for (const list of lists) {
    for (const notification of list) {
      byId.set(notification.idx, notification);
    }
  }
  return [...byId.values()].sort((a, b) => b.idx - a.idx);
}

export function DashboardPage({
  agents,
  health,
  error,
  user,
  integratedChatFullscreen,
  onToggleIntegratedChatFullscreen,
  onChatComplete,
}: DashboardPageProps) {
  const [detailTab, setDetailTab] = useState<DetailTab>("topology");
  const [signupNotifications, setSignupNotifications] = useState<SignupNotification[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSignupActionProcessing, setIsSignupActionProcessing] = useState(false);

  const assignedAgents = useMemo(() => {
    const assignedIds = new Set(
      (user.agent_ids ?? []).map((id) => id.trim()).filter(Boolean),
    );
    return agents.filter((agent) => assignedIds.has(agent.id));
  }, [agents, user.agent_ids]);

  const loadSignupNotifications = useCallback(async () => {
    if (user.role !== ROLE_ADMIN) {
      setSignupNotifications([]);
      return;
    }

    try {
      const [useridResponse, usernameResponse] = await Promise.all([
        fetch(`/api/signup/notifications/${encodeURIComponent(user.userid)}`),
        fetch(`/api/signup/notifications/${encodeURIComponent(user.username)}`),
      ]);

      const lists: SignupNotification[][] = [];
      if (useridResponse.ok) {
        lists.push((await useridResponse.json()) as SignupNotification[]);
      }
      if (usernameResponse.ok) {
        lists.push((await usernameResponse.json()) as SignupNotification[]);
      }
      setSignupNotifications(mergeSignupNotifications(...lists));
    } catch {
      setSignupNotifications([]);
    }
  }, [user.role, user.userid, user.username]);

  useEffect(() => {
    void loadSignupNotifications();
    const interval = window.setInterval(() => {
      void loadSignupNotifications();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [loadSignupNotifications]);

  const runSignupAction = useCallback(
    async (action: "approve" | "reject", userIdx: number, reason = "") => {
      setIsSignupActionProcessing(true);
      setActionError(null);
      try {
        const response =
          action === "approve"
            ? await fetch(`/api/signup/users/${userIdx}/approve`, { method: "POST" })
            : await fetch(`/api/signup/users/${userIdx}/reject`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reason }),
              });

        if (!response.ok) {
          throw new Error(await parseError(response, "가입 신청 처리에 실패했습니다."));
        }

        await loadSignupNotifications();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "가입 신청 처리에 실패했습니다.");
      } finally {
        setIsSignupActionProcessing(false);
      }
    },
    [loadSignupNotifications],
  );

  const dismissSignupNotification = useCallback(
    async (notificationIdx: number) => {
      setIsSignupActionProcessing(true);
      setActionError(null);
      try {
        const response = await fetch(`/api/signup/notifications/${notificationIdx}/dismiss`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "알림 처리에 실패했습니다."));
        }
        await loadSignupNotifications();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "알림 처리에 실패했습니다.");
      } finally {
        setIsSignupActionProcessing(false);
      }
    },
    [loadSignupNotifications],
  );

  return (
    <>
      {error ? (
        <div className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {actionError ? (
        <div className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          {actionError}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 items-stretch gap-4">
        {!integratedChatFullscreen ? (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 self-stretch">
            <AgentNodeListPanel>
              {assignedAgents.length > 0 ? <AgentGrid agents={assignedAgents} /> : null}
            </AgentNodeListPanel>

            <DetailInfoPanel
              agents={assignedAgents}
              health={health}
              viewerRole={user.role}
              activeTab={detailTab}
              onActiveTabChange={setDetailTab}
            />
          </div>
        ) : null}

        <IntegratedChatPanel
          agents={agents}
          user={user}
          isFullscreen={integratedChatFullscreen}
          onToggleFullscreen={onToggleIntegratedChatFullscreen}
          onChatComplete={onChatComplete}
          signupNotifications={signupNotifications}
          isSignupActionProcessing={isSignupActionProcessing}
          onSignupApprove={(userIdx) => void runSignupAction("approve", userIdx)}
          onSignupReject={(userIdx, reason) => void runSignupAction("reject", userIdx, reason)}
          onSignupHold={(notificationIdx) => void dismissSignupNotification(notificationIdx)}
        />
      </div>
    </>
  );
}
