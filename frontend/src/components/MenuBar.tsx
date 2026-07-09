import { useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import type { AppView } from "../types/navigation";

interface MenuBarProps {
  activeView: AppView;
  userLabel: string;
  onNavigate: (view: AppView) => void;
  onLogout: () => void;
}

function formatCurrentTime(date: Date): string {
  const year = String(date.getFullYear()).slice(-2);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");

  return `${year}년 ${month}월 ${day}일 ${hours}:${minutes}:${seconds}`;
}

function menuButtonClass(isActive: boolean): string {
  return `rounded-md px-3 py-1.5 transition ${
    isActive
      ? "bg-slate-800 text-white"
      : "text-slate-200 hover:bg-slate-800 hover:text-white"
  }`;
}

export function MenuBar({ activeView, userLabel, onNavigate, onLogout }: MenuBarProps) {
  const [currentTime, setCurrentTime] = useState(formatCurrentTime(new Date()));
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCurrentTime(formatCurrentTime(new Date()));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!userMenuRef.current?.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
    };
    window.addEventListener("mousedown", handleClickOutside);
    return () => window.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const isUserManagementActive =
    activeView === "user-list" || activeView === "agent-assignment";

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
          <button type="button" className={menuButtonClass(false)}>
            에이전트 관리
          </button>
          <span className="text-slate-600">|</span>
          <button type="button" className={menuButtonClass(false)}>
            LLM 관리
          </button>
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
                <button
                  type="button"
                  onClick={() => {
                    onNavigate("agent-assignment");
                    setShowUserMenu(false);
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

          <span className="text-slate-600">|</span>
          <button type="button" className={menuButtonClass(false)}>
            환경설정
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
          <time className="font-mono text-slate-400">{currentTime}</time>
          <span className="text-slate-200">{userLabel}</span>
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
    </>
  );
}
