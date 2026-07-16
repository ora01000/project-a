import { useCallback, useEffect, useState } from "react";

import { TopologyProvider } from "./context/TopologyContext";
import { AgentListPage } from "./components/agents/AgentListPage";
import { InventoryCsvPage } from "./components/agents/InventoryCsvPage";
import { DashboardPage } from "./components/DashboardPage";
import { LoginPage } from "./components/LoginPage";
import { MenuBar } from "./components/MenuBar";
import { StatusBar } from "./components/StatusBar";
import { AgentAssignmentPage } from "./components/users/AgentAssignmentPage";
import { UserListPage } from "./components/users/UserListPage";
import type { AgentInfo, HealthInfo } from "./types/agent";
import type { AuthUser } from "./types/auth";
import type { AppView } from "./types/navigation";
import { ROLE_ADMIN } from "./types/user";
import { clearAuthUser, loadAuthUser, saveAuthUser, startAuthSession } from "./utils/authSession";

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(() => loadAuthUser());
  const [activeView, setActiveView] = useState<AppView>("dashboard");
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [integratedChatFullscreen, setIntegratedChatFullscreen] = useState(false);

  const toggleIntegratedChatFullscreen = useCallback(() => {
    setIntegratedChatFullscreen((current) => !current);
  }, []);

  const handleLoginSuccess = useCallback((loggedInUser: AuthUser) => {
    startAuthSession(loggedInUser);
    setUser(loggedInUser);
    setActiveView("dashboard");
  }, []);

  const handleUserUpdated = useCallback((updatedUser: AuthUser) => {
    saveAuthUser(updatedUser);
    setUser(updatedUser);
  }, []);

  const handleLogout = useCallback(() => {
    clearAuthUser();
    setUser(null);
    setActiveView("dashboard");
    setAgents([]);
    setHealth(null);
    setError(null);
    setIntegratedChatFullscreen(false);
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
    const adminOnlyViews: AppView[] = ["agent-list", "inventory-csv", "agent-assignment"];
    if (user.role !== ROLE_ADMIN && adminOnlyViews.includes(activeView)) {
      setActiveView("dashboard");
    }
  }, [activeView, user]);

  if (!user) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <TopologyProvider>
      <div className="flex h-screen flex-col overflow-hidden bg-slate-950 px-6 py-6">
        <header className="mb-4 shrink-0">
          <h1 className="text-2xl font-bold text-slate-100">AX 인프라 운영 콘솔</h1>
          <p className="mt-1 text-sm text-slate-400">
            에이전트 노드와 오른쪽 통합 채팅 창으로 멀티 에이전트를 관리합니다.
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
          <>
            <div className="mb-4">
              <StatusBar health={health} />
            </div>
            <DashboardPage
              agents={agents}
              health={health}
              error={error}
              user={user}
              integratedChatFullscreen={integratedChatFullscreen}
              onToggleIntegratedChatFullscreen={toggleIntegratedChatFullscreen}
              onChatComplete={loadDashboardData}
            />
          </>
        ) : null}

        {activeView === "agent-list" && user.role === ROLE_ADMIN ? <AgentListPage /> : null}

        {activeView === "inventory-csv" && user.role === ROLE_ADMIN ? <InventoryCsvPage /> : null}

        {activeView === "user-list" ? (
          <UserListPage currentUserIdx={user.idx} currentUserRole={user.role} />
        ) : null}

        {activeView === "agent-assignment" && user.role === ROLE_ADMIN ? (
          <AgentAssignmentPage onClose={() => setActiveView("dashboard")} />
        ) : null}
      </div>
    </TopologyProvider>
  );
}
