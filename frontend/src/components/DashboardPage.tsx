import { useCallback, useEffect, useState } from "react";

import type { AgentInfo, HealthInfo } from "../types/agent";
import type { AuthUser } from "../types/auth";
import type { JobNotification } from "../types/job";
import { JOB_NOTIFICATION_REVIEW } from "../types/job";
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
  const [jobNotifications, setJobNotifications] = useState<JobNotification[]>([]);
  const [signupNotifications, setSignupNotifications] = useState<SignupNotification[]>([]);
  const [jobActionError, setJobActionError] = useState<string | null>(null);
  const [isJobActionProcessing, setIsJobActionProcessing] = useState(false);
  const [isSignupActionProcessing, setIsSignupActionProcessing] = useState(false);

  const loadJobNotifications = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/jobs/notifications/${encodeURIComponent(user.userid)}`,
      );
      if (!response.ok) {
        setJobNotifications([]);
        return;
      }
      setJobNotifications((await response.json()) as JobNotification[]);
    } catch {
      setJobNotifications([]);
    }
  }, [user.userid]);

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
    void loadJobNotifications();
    void loadSignupNotifications();
    const interval = window.setInterval(() => {
      void loadJobNotifications();
      void loadSignupNotifications();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [loadJobNotifications, loadSignupNotifications]);

  const runJobAction = useCallback(
    async (jobIdx: number, action: "review" | "approve" | "pending" | "reject") => {
      setIsJobActionProcessing(true);
      setJobActionError(null);
      if (action === "approve" || action === "pending" || action === "reject") {
        setJobNotifications((current) =>
          current.filter(
            (notification) =>
              !(
                notification.job_idx === jobIdx &&
                notification.notification_type === JOB_NOTIFICATION_REVIEW
              ),
          ),
        );
      }
      try {
        const response = await fetch(`/api/jobs/${jobIdx}/actions/${action}`, {
          method: "POST",
          headers: action === "reject" ? { "Content-Type": "application/json" } : undefined,
          body: action === "reject" ? JSON.stringify({ reason: "" }) : undefined,
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "작업 처리에 실패했습니다."));
        }
        // approve/retry are accepted immediately (202); results arrive via notification polling.
        await loadJobNotifications();
        if (action === "review") {
          setDetailTab("review");
        }
      } catch (err) {
        setJobActionError(err instanceof Error ? err.message : "작업 처리에 실패했습니다.");
        await loadJobNotifications();
      } finally {
        setIsJobActionProcessing(false);
      }
    },
    [loadJobNotifications],
  );

  const runSignupAction = useCallback(
    async (action: "approve" | "reject", userIdx: number, reason = "") => {
      setIsSignupActionProcessing(true);
      setJobActionError(null);
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
        setJobActionError(err instanceof Error ? err.message : "가입 신청 처리에 실패했습니다.");
      } finally {
        setIsSignupActionProcessing(false);
      }
    },
    [loadSignupNotifications],
  );

  const dismissSignupNotification = useCallback(
    async (notificationIdx: number) => {
      setIsSignupActionProcessing(true);
      setJobActionError(null);
      try {
        const response = await fetch(`/api/signup/notifications/${notificationIdx}/dismiss`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "알림 처리에 실패했습니다."));
        }
        await loadSignupNotifications();
      } catch (err) {
        setJobActionError(err instanceof Error ? err.message : "알림 처리에 실패했습니다.");
      } finally {
        setIsSignupActionProcessing(false);
      }
    },
    [loadSignupNotifications],
  );

  const dismissJobNotification = useCallback(
    async (notificationIdx: number) => {
      setIsJobActionProcessing(true);
      setJobActionError(null);
      try {
        const response = await fetch(`/api/jobs/notifications/${notificationIdx}/dismiss`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "작업 알림 해제에 실패했습니다."));
        }
        await loadJobNotifications();
      } catch (err) {
        setJobActionError(err instanceof Error ? err.message : "작업 알림 해제에 실패했습니다.");
      } finally {
        setIsJobActionProcessing(false);
      }
    },
    [loadJobNotifications],
  );

  const retryFailedJob = useCallback(
    async (jobIdx: number, notificationIdx: number) => {
      setIsJobActionProcessing(true);
      setJobActionError(null);
      setJobNotifications((current) =>
        current.filter((notification) => notification.idx !== notificationIdx),
      );
      try {
        const response = await fetch(`/api/jobs/${jobIdx}/actions/retry`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "재작업 요청에 실패했습니다."));
        }
        await loadJobNotifications();
      } catch (err) {
        setJobActionError(err instanceof Error ? err.message : "재작업 요청에 실패했습니다.");
        await loadJobNotifications();
      } finally {
        setIsJobActionProcessing(false);
      }
    },
    [loadJobNotifications],
  );

  return (
    <>
      {error ? (
        <div className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {jobActionError ? (
        <div className="mb-4 rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          {jobActionError}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 items-stretch gap-4">
        {!integratedChatFullscreen ? (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 self-stretch">
            <AgentNodeListPanel>
              {agents.length > 0 ? <AgentGrid agents={agents} /> : null}
            </AgentNodeListPanel>

            <DetailInfoPanel
              agents={agents}
              health={health}
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
          jobNotifications={jobNotifications}
          signupNotifications={signupNotifications}
          isJobActionProcessing={isJobActionProcessing}
          isSignupActionProcessing={isSignupActionProcessing}
          onJobReview={(jobIdx) => void runJobAction(jobIdx, "review")}
          onJobApprove={(jobIdx) => void runJobAction(jobIdx, "approve")}
          onJobPending={(jobIdx) => void runJobAction(jobIdx, "pending")}
          onJobReject={(jobIdx) => void runJobAction(jobIdx, "reject")}
          onJobDismiss={(notificationIdx) => void dismissJobNotification(notificationIdx)}
          onJobRetry={(jobIdx, notificationIdx) => void retryFailedJob(jobIdx, notificationIdx)}
          onSignupApprove={(userIdx) => void runSignupAction("approve", userIdx)}
          onSignupReject={(userIdx, reason) => void runSignupAction("reject", userIdx, reason)}
          onSignupHold={(notificationIdx) => void dismissSignupNotification(notificationIdx)}
        />
      </div>
    </>
  );
}
