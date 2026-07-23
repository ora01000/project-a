import { useEffect, useRef, useState } from "react";

import type { AuthUser } from "../types/auth";
import type { AppView } from "../types/navigation";
import { ROLE_ADMIN } from "../types/user";
import { formatUserLabel } from "../utils/authSession";
import { formatCurrentTime } from "../utils/datetime";
import { AboutModal } from "./AboutModal";
import { ConfirmDialog } from "./ConfirmDialog";
import { InfraCollectModal } from "./admin/InfraCollectModal";
import { ProfileEditModal } from "./ProfileEditModal";
import { ReleaseNotesModal } from "./ReleaseNotesModal";
import { TableDebugModal } from "./TableDebugModal";
import { TestJobSendModal } from "./jobs/TestJobSendModal";

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
      ? "bg-slate-800 text-white"
      : "text-slate-200 hover:bg-slate-800 hover:text-white"
  }`;
}

export function MenuBar({ activeView, user, onNavigate, onLogout, onUserUpdated }: MenuBarProps) {
  const [currentTime, setCurrentTime] = useState(formatCurrentTime(new Date()));
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const [showReleaseNotes, setShowReleaseNotes] = useState(false);
  const [showTestJobSend, setShowTestJobSend] = useState(false);
  const [showTableDebug, setShowTableDebug] = useState(false);
  const [showInfraCollect, setShowInfraCollect] = useState(false);
  const [showProfileEdit, setShowProfileEdit] = useState(false);
  const [showSaveSuccess, setShowSaveSuccess] = useState(false);
  const [showAgentMenu, setShowAgentMenu] = useState(false);
  const [showJobMenu, setShowJobMenu] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const [showAdminWorkMenu, setShowAdminWorkMenu] = useState(false);
  const agentMenuRef = useRef<HTMLDivElement>(null);
  const jobMenuRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const settingsMenuRef = useRef<HTMLDivElement>(null);
  const userLabel = formatUserLabel(user);
  const isAdmin = user.role === ROLE_ADMIN;

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCurrentTime(formatCurrentTime(new Date()));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!agentMenuRef.current?.contains(event.target as Node)) {
        setShowAgentMenu(false);
      }
      if (!jobMenuRef.current?.contains(event.target as Node)) {
        setShowJobMenu(false);
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
    isAdmin &&
    (activeView === "agent-list" ||
      activeView === "inventory-csv" ||
      activeView === "agent-assignment" ||
      activeView === "token-management");

  const isJobManagementActive = activeView === "job-list" || activeView === "job-create";
  const isUserManagementActive = activeView === "user-list";

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
                      onNavigate("agent-list");
                      setShowAgentMenu(false);
                    }}
                    className={`block w-full px-3 py-2 text-left text-sm ${
                      activeView === "agent-list"
                        ? "bg-slate-800 text-sky-200"
                        : "text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    에이전트 관리
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onNavigate("inventory-csv");
                      setShowAgentMenu(false);
                    }}
                    className={`block w-full px-3 py-2 text-left text-sm ${
                      activeView === "inventory-csv"
                        ? "bg-slate-800 text-sky-200"
                        : "text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    인벤토리 CSV
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
                  <button
                    type="button"
                    onClick={() => {
                      onNavigate("token-management");
                      setShowAgentMenu(false);
                    }}
                    className={`block w-full px-3 py-2 text-left text-sm ${
                      activeView === "token-management"
                        ? "bg-slate-800 text-sky-200"
                        : "text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    토큰관리
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {isAdmin ? <span className="text-slate-600">|</span> : null}

          <div ref={jobMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setShowJobMenu((current) => !current)}
              className={menuButtonClass(isJobManagementActive)}
            >
              작업관리 ▾
            </button>
            {showJobMenu ? (
              <div className="absolute left-0 top-full z-20 mt-1 min-w-[160px] rounded-md border border-slate-700 bg-slate-900 py-1 shadow-lg">
                <button
                  type="button"
                  onClick={() => {
                    onNavigate("job-list");
                    setShowJobMenu(false);
                  }}
                  className={`block w-full px-3 py-2 text-left text-sm ${
                    activeView === "job-list"
                      ? "bg-slate-800 text-sky-200"
                      : "text-slate-200 hover:bg-slate-800"
                  }`}
                >
                  작업 목록
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onNavigate("job-create");
                    setShowJobMenu(false);
                  }}
                  className={`block w-full px-3 py-2 text-left text-sm ${
                    activeView === "job-create"
                      ? "bg-slate-800 text-sky-200"
                      : "text-slate-200 hover:bg-slate-800"
                  }`}
                >
                  작업 생성
                </button>
              </div>
            ) : null}
          </div>

          <span className="text-slate-600">|</span>

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
                  showTestJobSend ||
                  showTableDebug ||
                  showInfraCollect,
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
                        showTestJobSend ||
                        showTableDebug ||
                        showInfraCollect
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
                            setShowInfraCollect(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          인프라 정보 수집
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setShowSettingsMenu(false);
                            setShowAdminWorkMenu(false);
                            setShowTestJobSend(true);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                        >
                          테스트 작업 발송
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
          <time className="font-mono text-slate-400">{currentTime}</time>
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

      {showAbout ? <AboutModal onClose={() => setShowAbout(false)} /> : null}
      {showReleaseNotes ? <ReleaseNotesModal onClose={() => setShowReleaseNotes(false)} /> : null}
      {showTestJobSend && isAdmin ? (
        <TestJobSendModal onClose={() => setShowTestJobSend(false)} />
      ) : null}
      {showTableDebug && isAdmin ? (
        <TableDebugModal onClose={() => setShowTableDebug(false)} />
      ) : null}
      {showInfraCollect && isAdmin ? (
        <InfraCollectModal viewerRole={user.role} onClose={() => setShowInfraCollect(false)} />
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
