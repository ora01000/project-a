import { useEffect, useState } from "react";

const MENU_ITEMS = ["대시보드", "에이전트 관리", "LLM 관리", "사용자 관리", "환경설정"] as const;
const LOGGED_IN_USER = "윤인수 책임";

function formatCurrentTime(date: Date): string {
  const year = String(date.getFullYear()).slice(-2);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");

  return `${year}년 ${month}월 ${day}일 ${hours}:${minutes}:${seconds}`;
}

export function MenuBar() {
  const [currentTime, setCurrentTime] = useState(formatCurrentTime(new Date()));

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCurrentTime(formatCurrentTime(new Date()));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <nav className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/80 px-4 py-3">
      <div className="flex flex-wrap items-center gap-1 text-sm">
        {MENU_ITEMS.map((item, index) => (
          <div key={item} className="flex items-center gap-1">
            <button
              type="button"
              className="rounded-md px-3 py-1.5 text-slate-200 transition hover:bg-slate-800 hover:text-white"
            >
              {item}
            </button>
            {index < MENU_ITEMS.length - 1 ? <span className="text-slate-600">|</span> : null}
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
        <time className="font-mono text-slate-400">{currentTime}</time>
        <span className="text-slate-200">{LOGGED_IN_USER}</span>
        <button
          type="button"
          className="rounded-md border border-slate-700 px-3 py-1.5 text-slate-200 transition hover:bg-slate-800"
        >
          로그아웃
        </button>
      </div>
    </nav>
  );
}
