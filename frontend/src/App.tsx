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
import { clearAuthUser, loadAuthUser, saveAuthUser } from "./utils/authSession";

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
    saveAuthUser(loggedInUser);
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

  const loadDashboardData = useCallback(async () => {
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
  }, []);

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

        {activeView === "agent-list" ? <AgentListPage /> : null}

        {activeView === "inventory-csv" ? <InventoryCsvPage /> : null}

        {activeView === "user-list" ? (
          <UserListPage currentUserIdx={user.idx} currentUserRole={user.role} />
        ) : null}

        {activeView === "agent-assignment" ? <AgentAssignmentPage /> : null}
      </div>
    </TopologyProvider>
  );
}
