import { useState } from "react";

import { useTheme } from "../context/ThemeContext";
import type { AppTheme } from "../types/theme";
import { THEME_LABELS } from "../types/theme";

interface ThemeSettingsModalProps {
  onClose: () => void;
}

const THEME_OPTIONS: AppTheme[] = ["dark", "light"];

export function ThemeSettingsModal({ onClose }: ThemeSettingsModalProps) {
  const { theme, setTheme } = useTheme();
  const [selected, setSelected] = useState<AppTheme>(theme);

  const handleApply = () => {
    setTheme(selected);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="theme-settings-title"
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="theme-settings-title" className="text-lg font-semibold text-slate-100">
          화면 테마
        </h2>
        <p className="mt-1 text-sm text-slate-400">콘솔 화면의 밝기 테마를 선택합니다.</p>

        <div className="mt-4 space-y-2">
          {THEME_OPTIONS.map((option) => (
            <label
              key={option}
              className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 transition ${
                selected === option
                  ? "border-sky-600 bg-sky-950/40 text-sky-100"
                  : "border-slate-700 bg-slate-950/40 text-slate-200 hover:border-slate-500"
              }`}
            >
              <input
                type="radio"
                name="app-theme"
                value={option}
                checked={selected === option}
                onChange={() => setSelected(option)}
                className="accent-sky-500"
              />
              <span className="text-sm font-medium">{THEME_LABELS[option]}</span>
            </label>
          ))}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            적용
          </button>
        </div>
      </div>
    </div>
  );
}
