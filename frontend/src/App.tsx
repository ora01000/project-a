import { useCallback, useEffect, useState } from "react";

import { TopologyProvider } from "./context/TopologyContext";
import { DashboardPage } from "./components/DashboardPage";
import { LoginPage } from "./components/LoginPage";
import { MenuBar } from "./components/MenuBar";
import { TeamsInboundDebugWatcher } from "./components/TeamsInboundDebugWatcher";
import { NoticeBoardPage } from "./components/notices/NoticeBoardPage";
import { AgentConnectionListPage } from "./components/agentruntime/AgentConnectionListPage";
import { AgentAssignmentPage } from "./components/users/AgentAssignmentPage";
import { UserListPage } from "./components/users/UserListPage";
import type { AgentInfo, HealthInfo } from "./types/agent";
import type { AuthUser } from "./types/auth";
import type { AppView } from "./types/navigation";
import { ROLE_ADMIN, ROLE_PENDING } from "./types/user";
import { logoutSession, setUnauthorizedHandler } from "./utils/api";
import {
  clearAuthUser,
  getAccessToken,
  loadAuthUser,
  saveAuthUser,
  startAuthSession,
  userFromAuthResponse,
} from "./utils/authSession";

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authBootstrapping, setAuthBootstrapping] = useState(() => Boolean(getAccessToken()));
  const [activeView, setActiveView] = useState<AppView>("dashboard");
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [integratedChatFullscreen, setIntegratedChatFullscreen] = useState(false);

  const toggleIntegratedChatFullscreen = useCallback(() => {
    setIntegratedChatFullscreen((current) => !current);
  }, []);

  const handleLoginSuccess = useCallback(
    (loggedInUser: AuthUser, accessToken: string, expiresInSeconds: number) => {
      startAuthSession(loggedInUser, accessToken, expiresInSeconds);
      setUser(loggedInUser);
      setActiveView("dashboard");
    },
    [],
  );

  const handleUserUpdated = useCallback((updatedUser: AuthUser) => {
    saveAuthUser(updatedUser);
    setUser(updatedUser);
  }, []);

  const handleLogout = useCallback(() => {
    void logoutSession();
    setUser(null);
    setActiveView("dashboard");
    setAgents([]);
    setHealth(null);
    setError(null);
    setIntegratedChatFullscreen(false);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearAuthUser();
      setUser(null);
      setActiveView("dashboard");
      setAgents([]);
      setHealth(null);
      setError(null);
      setIntegratedChatFullscreen(false);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setAuthBootstrapping(false);
      return;
    }

    let cancelled = false;
    const restoreSession = async () => {
      try {
        const response = await fetch("/api/auth/me");
        if (!response.ok) {
          clearAuthUser();
          if (!cancelled) {
            setUser(null);
          }
          return;
        }

        const payload = (await response.json()) as Record<string, unknown>;
        const restoredUser = userFromAuthResponse(payload);
        if (restoredUser.role === ROLE_PENDING) {
          clearAuthUser();
          if (!cancelled) {
            setUser(null);
          }
          return;
        }
        const expiresIn = typeof payload.expires_in === "number" ? payload.expires_in : 3600;
        if (!cancelled) {
          startAuthSession(restoredUser, token, expiresIn);
          setUser(restoredUser);
        }
      } catch {
        const cachedUser = loadAuthUser();
        if (!cancelled) {
          setUser(cachedUser);
        }
      } finally {
        if (!cancelled) {
          setAuthBootstrapping(false);
        }
      }
    };

    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!user) {
      return;
    }

    const checkSession = () => {
      const current = loadAuthUser();
      if (!current) {
        handleLogout();
      }
    };

    checkSession();
    const interval = window.setInterval(checkSession, 15_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        checkSession();
      }
    };
    const onFocus = () => {
      checkSession();
    };

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [user, handleLogout]);
  const userIdx = user?.idx;
  const userRole = user?.role;

  const loadDashboardData = useCallback(async () => {
    if (userIdx == null || userRole == null) {
      return;
    }

    try {
      const [agentsResponse, healthResponse, usersResponse] = await Promise.all([
        fetch("/api/agents"),
        fetch("/api/health"),
        fetch(`/api/users?viewer_role=${userRole}`),
      ]);

      if (!agentsResponse.ok || !healthResponse.ok) {
        throw new Error("백엔드 API에 연결할 수 없습니다.");
      }

      const agentsData = (await agentsResponse.json()) as AgentInfo[];
      const healthData = (await healthResponse.json()) as HealthInfo;
      setAgents(agentsData);
      setHealth(healthData);
      setError(null);

      if (usersResponse.ok) {
        const usersData = (await usersResponse.json()) as AuthUser[];
        const me = usersData.find((entry) => entry.idx === userIdx);
        if (me) {
          setUser((current) => {
            if (!current || current.idx !== userIdx) {
              return current;
            }
            const nextAgents = me.agents ?? "";
            const nextAgentIds = me.agent_ids ?? [];
            const prevIds = (current.agent_ids ?? []).join(",");
            const nextIds = nextAgentIds.join(",");
            if (prevIds === nextIds && (current.agents ?? "") === nextAgents) {
              return current;
            }
            const nextUser: AuthUser = {
              ...current,
              agents: nextAgents,
              agent_ids: nextAgentIds,
            };
            saveAuthUser(nextUser);
            return nextUser;
          });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }, [userIdx, userRole]);

  useEffect(() => {
    if (!user || activeView !== "dashboard") {
      return;
    }

    loadDashboardData();
    const interval = window.setInterval(loadDashboardData, 15000);
    return () => window.clearInterval(interval);
  }, [activeView, loadDashboardData, user]);

  useEffect(() => {
    if (activeView !== "dashboard") {
      setIntegratedChatFullscreen(false);
    }
  }, [activeView]);

  useEffect(() => {
    if (!user) {
      return;
    }
    const adminOnlyViews: AppView[] = ["agent-assignment", "agent-connections"];
    const disabledViews: AppView[] = ["token-management"];
    if (
      (user.role !== ROLE_ADMIN && adminOnlyViews.includes(activeView)) ||
      disabledViews.includes(activeView)
    ) {
      setActiveView("dashboard");
    }
  }, [activeView, user]);

  if (authBootstrapping) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        세션 확인 중...
      </div>
    );
  }

  if (!user) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <TopologyProvider>
      <div className="flex h-screen flex-col overflow-hidden bg-slate-950 px-6 py-6">
        <header className="mb-4 shrink-0">
          <h1 className="text-2xl font-bold text-slate-100">AX 인프라 운영 콘솔</h1>
          <p className="mt-1 text-sm text-slate-400">
            에이전트 노드와 오른쪽 대화형 터미널로 멀티 에이전트를 관리합니다.
          </p>
        </header>

        <MenuBar
          activeView={activeView}
          user={user}
          onNavigate={setActiveView}
          onLogout={handleLogout}
          onUserUpdated={handleUserUpdated}
        />

        {activeView === "dashboard" ? (
          <DashboardPage
            agents={agents}
            health={health}
            error={error}
            user={user}
            integratedChatFullscreen={integratedChatFullscreen}
            onToggleIntegratedChatFullscreen={toggleIntegratedChatFullscreen}
            onChatComplete={loadDashboardData}
          />
        ) : null}

        {activeView === "user-list" ? (
          <UserListPage currentUserIdx={user.idx} currentUserRole={user.role} />
        ) : null}

        {activeView === "agent-assignment" && user.role === ROLE_ADMIN ? (
          <AgentAssignmentPage onClose={() => setActiveView("dashboard")} />
        ) : null}

        {activeView === "agent-connections" && user.role === ROLE_ADMIN ? (
          <AgentConnectionListPage user={user} onAgentRuntimeChanged={loadDashboardData} />
        ) : null}

        {activeView === "notice-board" ? <NoticeBoardPage user={user} /> : null}
      </div>
      <TeamsInboundDebugWatcher />
    </TopologyProvider>
  );
}
