import { useEffect, useRef, useState } from "react";

import type { AuthUser } from "../types/auth";
import type { AppView } from "../types/navigation";
import { hasAdminAccess } from "../types/user";
import { EventReportSubscriptionModal } from "./users/EventReportSubscriptionModal";
import {
  extendAuthSession,
  formatAuthSessionRemaining,
  formatUserLabel,
  getAuthSessionRemainingMs,
  SESSION_EXTEND_THRESHOLD_MS,
} from "../utils/authSession";
import { formatCurrentTime } from "../utils/datetime";
import { AboutModal } from "./AboutModal";
import { ConfirmDialog } from "./ConfirmDialog";
import { MockLlmSelectModal } from "./admin/MockLlmSelectModal";
import { PostmanDebugModal } from "./admin/PostmanDebugModal";
import { WhatapEventTestModal } from "./admin/WhatapEventTestModal";
import { K8sInfraConfigModal } from "./admin/K8sInfraConfigModal";
import { MailServerConfigModal } from "./admin/MailServerConfigModal";
import { MailTestModal } from "./admin/MailTestModal";
import { ReceivedMailDebugModal } from "./admin/ReceivedMailDebugModal";
import { ProfileEditModal } from "./ProfileEditModal";
import { ReleaseNotesModal } from "./ReleaseNotesModal";
import { TableDebugModal } from "./TableDebugModal";
import { ThemeSettingsModal } from "./ThemeSettingsModal";

interface MenuBarProps {
  activeView: AppView;
  user: AuthUser;
  onNavigate: (view: AppView) => void;
  onLogout: () => void;
  onUserUpdated: (user: AuthUser) => void;
}

function menuButtonClass(isActive: boolean): string {
  return `rounded-md px-3 py-1.5 transition ${
    isActive
      ? "bg-slate-800 text-slate-100"
      : "text-slate-200 hover:bg-slate-800 hover:text-slate-100"
  }`;
}

export function MenuBar({ activeView, user, onNavigate, onLogout, onUserUpdated }: MenuBarProps) {
  const [currentTime, setCurrentTime] = useState(formatCurrentTime(new Date()));
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [showSessionExtendConfirm, setShowSessionExtendConfirm] = useState(false);
  const [sessionRemainingMs, setSessionRemainingMs] = useState(() => getAuthSessionRemainingMs());
  const [isExtendingSession, setIsExtendingSession] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const [showReleaseNotes, setShowReleaseNotes] = useState(false);
  const [showThemeSettings, setShowThemeSettings] = useState(false);
  const [showTableDebug, setShowTableDebug] = useState(false);
  const [showPostmanDebug, setShowPostmanDebug] = useState(false);
  const [showMockLlmSelect, setShowMockLlmSelect] = useState(false);
  const [showWhatapEventTest, setShowWhatapEventTest] = useState(false);
  const [showK8sInfraConfig, setShowK8sInfraConfig] = useState(false);
  const [showMailServerConfig, setShowMailServerConfig] = useState(false);
  const [showMailTest, setShowMailTest] = useState(false);
  const [showReceivedMailDebug, setShowReceivedMailDebug] = useState(false);
  const [showEventReportSub, setShowEventReportSub] = useState(false);
  const [runtimeMode, setRuntimeMode] = useState<string>("mock");
  const [showProfileEdit, setShowProfileEdit] = useState(false);
  const [showSaveSuccess, setShowSaveSuccess] = useState(false);
  const [showAgentMenu, setShowAgentMenu] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const [showAdminWorkMenu, setShowAdminWorkMenu] = useState(false);
  const agentMenuRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const settingsMenuRef = useRef<HTMLDivElement>(null);
  const userLabel = formatUserLabel(user);
  const isAdmin = hasAdminAccess(user.role);
  const isMockRuntime = runtimeMode === "mock" || runtimeMode === "local";

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCurrentTime(formatCurrentTime(new Date()));
      setSessionRemainingMs(getAuthSessionRemainingMs());
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const canExtendSession =
    sessionRemainingMs > 0 && sessionRemainingMs <= SESSION_EXTEND_THRESHOLD_MS;

  const handleConfirmSessionExtend = () => {
    setShowSessionExtendConfirm(false);
    setIsExtendingSession(true);
    void extendAuthSession()
      .then(() => {
        setSessionRemainingMs(getAuthSessionRemainingMs());
      })
      .catch(() => {
        // 401 등은 fetch 인터셉터가 처리
      })
      .finally(() => {
        setIsExtendingSession(false);
      });
  };

  useEffect(() => {
    let cancelled = false;

    const loadRuntimeMode = async () => {
      try {
        const response = await fetch("/api/health");
        if (!response.ok) {
          return;
        }
        const health = (await response.json()) as { runtime_mode?: string };
        if (!cancelled) {
          setRuntimeMode(health.runtime_mode ?? "mock");
        }
      } catch {
        if (!cancelled) {
          setRuntimeMode("mock");
        }
      }
    };

    void loadRuntimeMode();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!agentMenuRef.current?.contains(event.target as Node)) {
        setShowAgentMenu(false);
      }
      if (!userMenuRef.current?.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
      if (!settingsMenuRef.current?.contains(event.target as Node)) {
        setShowSettingsMenu(false);
        setShowAdminWorkMenu(false);
      }
    };
    window.addEventListener("mousedown", handleClickOutside);
    return () => window.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const isAgentMenuActive =
    isAdmin && (activeView === "agent-assignment" || activeView === "agent-connections");


  const isUserManagementActive = activeView === "user-list" || showEventReportSub;

  return (
    <>
      <nav className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/80 px-4 py-3">
        <div className="flex flex-wrap items-center gap-1 text-sm">
          <button
            type="button"
            onClick={() => onNavigate("dashboard")}
            className={menuButtonClass(activeView === "dashboard")}
          >
            대시보드
          </button>
          <span className="text-slate-600">|</span>

          {isAdmin ? (
            <div ref={agentMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setShowAgentMenu((current) => !current)}
                className={menuButtonClass(isAgentMenuActive)}
              >
                에이전트 ▾
              </button>
              {showAgentMenu ? (
                <div className="absolute left-0 top-full z-20 mt-1 min-w-[160px] rounded-md border border-slate-700 bg-slate-900 py-1 shadow-lg">
                  <button
                    type="button"
                    onClick={() => {
                      onNavigate("agent-connections");
                      setShowAgentMenu(false);
                    }}
                    className={`block w-full px-3 py-2 text-left text-sm ${
                      activeView === "agent-connections"
                        ? "bg-slate-800 text-sky-200"
                        : "text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    에이전트 연결
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onNavigate("agent-assignment");
                      setShowAgentMenu(false);
                    }}
                    className={`block w-full px-3 py-2 text-left text-sm ${
                      activeView === "agent-assignment"
                        ? "bg-slate-800 text-sky-200"
                        : "text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    에이전트 할당
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {isAdmin ? <span className="text-slate-600">|</span> : null}

          <div ref={userMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setShowUserMenu((current) => !current)}
              className={menuButtonClass(isUserManagementActive)}
            >
              사용자 관리 ▾
            </button>
            {showUserMenu ? (
              <div className="absolute left-0 top-full z-20 mt-1 min-w-[160px] rounded-md border border-slate-700 bg-slate-900 py-1 shadow-lg">
                <button
                  type="button"
                  onClick={() => {
                    onNavigate("user-list");
                    setShowUserMenu(false);
                  }}
                  className={`block w-full px-3 py-2 text-left text-sm ${
                    activeView === "user-list"
                      ? "bg-slate-800 text-sky-200"
                      : "text-slate-200 hover:bg-slate-800"
                  }`}
                >
                  사용자 조회
                </button>
                {isAdmin ? (
                  <button
                    type="button"
                    onClick={() => {
                      setShowEventReportSub(true);
                      setShowUserMenu(false);
                    }}
                    className={`block w-full px-3 py-2 text-left text-sm ${
                      showEventReportSub
                        ? "bg-slate-800 text-sky-200"
                        : "text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    이벤트 리포트 구독
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>

          <span className="text-slate-600">|</span>

          <div ref={settingsMenuRef} className="relative">
            <button
              type="button"
              onClick={() => {
                setShowSettingsMenu((current) => {
                  const next = !current;
                  if (!next) {
                    setShowAdminWorkMenu(false);
                  }
                  return next;
                });
              }}
              className={menuButtonClass(
                showAbout ||
                  showReleaseNotes ||
                  showTableDebug ||
                        showPostmanDebug ||
                        showMockLlmSelect ||
                        showWhatapEventTest ||
                        showK8sInfraConfig ||
                        showMailServerConfig ||
                        showMailTest ||
                        showReceivedMailDebug ||
                  showThemeSettings,
              )}
            >
              환경설정 ▾
            </button>
            {showSettingsMenu ? (
              <div className="absolute left-0 top-full z-20 mt-1 min-w-[180px] rounded-md border border-slate-700 bg-slate-900 py-1 shadow-lg">
                {isAdmin ? (
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setShowAdminWorkMenu((current) => !current)}
                      className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm ${
                        showAdminWorkMenu ||
                        showTableDebug ||
                        showPostmanDebug ||
                        showMockLlmSelect ||
                        showWhatapEventTest ||
                        showK8sInfraConfig ||
                        showMailServerConfig ||
                        showMailTest ||
                        showReceivedMailDebug
                          ? "bg-slate-800 text-sky-200"
                          : "text-slate-200 hover:bg-slate-800"
                      }`}
                    >
                      <span>관리자 작업</span>
                      <span className="text-slate-500">▸</span>
                    </button>
                    {showAdminWorkMenu ? (
                      <div className="absolute left-full top-0 z-30 ml-1 min-w-[180px] rounded-md border border-slate-700 bg-slate-900 py-1 shadow-lg">
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowPostmanDebug(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          postman
                        </button>
                        {isMockRuntime ? (
                          <button
                            type="button"
                            onClick={() => {
                              setShowSettingsMenu(false);
                              setShowAdminWorkMenu(false);
                              setShowMockLlmSelect(true);
                            }}
                            className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                          >
                            (목업)LLM 변경
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowWhatapEventTest(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          Whatap 이벤트 테스트
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowK8sInfraConfig(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          인프라 구성
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowMailServerConfig(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          메일 서버 설정
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowMailTest(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          테스트 메일 발송(디버깅)
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowReceivedMailDebug(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          수신메일 목록(디버깅)
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowTableDebug(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          테이블 조회(디버깅)
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    setShowSettingsMenu(false);
                    setShowAdminWorkMenu(false);
                    setShowThemeSettings(true);
                  }}
                  className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                >
                  화면 테마
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowSettingsMenu(false);
                    setShowAdminWorkMenu(false);
                    setShowReleaseNotes(true);
                  }}
                  className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                >
                  변경이력
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowSettingsMenu(false);
                    setShowAdminWorkMenu(false);
                    setShowAbout(true);
                  }}
                  className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                >
                  About
                </button>
              </div>
            ) : null}
          </div>

          <span className="text-slate-600">|</span>

          <button
            type="button"
            onClick={() => onNavigate("notice-board")}
            className={menuButtonClass(activeView === "notice-board")}
          >
            공지사항
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
          <div className="flex items-center gap-2">
            <time className="font-mono text-slate-400">{currentTime}</time>
            <button
              type="button"
              disabled={!canExtendSession || isExtendingSession}
              onClick={() => setShowSessionExtendConfirm(true)}
              title={
                canExtendSession
                  ? "세션 만료 전 연장 (클릭)"
                  : "세션 만료까지 남은 시간 (5분 이하일 때 연장 가능)"
              }
              className={`rounded-md border px-2.5 py-1 font-mono text-xs transition ${
                canExtendSession
                  ? "border-amber-600/80 bg-amber-950/40 text-amber-100 hover:bg-amber-900/50 disabled:opacity-50"
                  : "cursor-default border-slate-700 text-slate-500 disabled:opacity-100"
              }`}
            >
              {formatAuthSessionRemaining(sessionRemainingMs)}
            </button>
          </div>
          <button
            type="button"
            onClick={() => setShowProfileEdit(true)}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-slate-200 transition hover:bg-slate-800"
            title="개인정보 수정"
          >
            {userLabel}
          </button>
          <button
            type="button"
            onClick={() => setShowLogoutConfirm(true)}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-slate-200 transition hover:bg-slate-800"
          >
            로그아웃
          </button>
        </div>
      </nav>

      {showLogoutConfirm ? (
        <ConfirmDialog
          title="로그아웃"
          message="로그아웃 하시겠습니까?"
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setShowLogoutConfirm(false)}
          onConfirm={() => {
            setShowLogoutConfirm(false);
            onLogout();
          }}
        />
      ) : null}

      {showSessionExtendConfirm ? (
        <ConfirmDialog
          title="세션 연장"
          message="세션을 연장하시겠습니까?"
          confirmLabel="연장"
          onCancel={() => setShowSessionExtendConfirm(false)}
          onConfirm={handleConfirmSessionExtend}
        />
      ) : null}

      {showThemeSettings ? <ThemeSettingsModal onClose={() => setShowThemeSettings(false)} /> : null}
      {showAbout ? <AboutModal onClose={() => setShowAbout(false)} /> : null}
      {showReleaseNotes ? <ReleaseNotesModal onClose={() => setShowReleaseNotes(false)} /> : null}
      {showPostmanDebug && isAdmin ? (
        <PostmanDebugModal viewerRole={user.role} onClose={() => setShowPostmanDebug(false)} />
      ) : null}
      {showMockLlmSelect && isAdmin && isMockRuntime ? (
        <MockLlmSelectModal viewerRole={user.role} onClose={() => setShowMockLlmSelect(false)} />
      ) : null}
      {showTableDebug && isAdmin ? (
        <TableDebugModal onClose={() => setShowTableDebug(false)} />
      ) : null}
      {showWhatapEventTest && isAdmin ? (
        <WhatapEventTestModal viewerRole={user.role} onClose={() => setShowWhatapEventTest(false)} />
      ) : null}
      {showK8sInfraConfig && isAdmin ? (
        <K8sInfraConfigModal viewerRole={user.role} onClose={() => setShowK8sInfraConfig(false)} />
      ) : null}
      {showMailServerConfig && isAdmin ? (
        <MailServerConfigModal
          viewerRole={user.role}
          onClose={() => setShowMailServerConfig(false)}
        />
      ) : null}
      {showMailTest && isAdmin ? (
        <MailTestModal viewerRole={user.role} onClose={() => setShowMailTest(false)} />
      ) : null}
      {showReceivedMailDebug && isAdmin ? (
        <ReceivedMailDebugModal
          viewerRole={user.role}
          onClose={() => setShowReceivedMailDebug(false)}
        />
      ) : null}
      {showEventReportSub && isAdmin ? (
        <EventReportSubscriptionModal
          viewerRole={user.role}
          onClose={() => setShowEventReportSub(false)}
        />
      ) : null}
      {showProfileEdit ? (
        <ProfileEditModal
          user={user}
          onClose={() => setShowProfileEdit(false)}
          onSaved={(updated) => {
            onUserUpdated(updated);
            setShowProfileEdit(false);
            setShowSaveSuccess(true);
          }}
        />
      ) : null}
      {showSaveSuccess ? (
        <ConfirmDialog
          title="저장 완료"
          message="개인정보가 저장되었습니다."
          confirmLabel="확인"
          cancelLabel="닫기"
          onCancel={() => setShowSaveSuccess(false)}
          onConfirm={() => setShowSaveSuccess(false)}
        />
      ) : null}
    </>
  );
}
