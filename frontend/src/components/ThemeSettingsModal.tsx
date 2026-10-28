import { useState } from "react";

import { useTheme } from "../context/ThemeContext";
import type { AuthUser } from "../types/auth";
import type { AppTheme } from "../types/theme";
import { THEME_LABELS, themeToId } from "../types/theme";
import { userFromAuthResponse } from "../utils/authSession";

interface ThemeSettingsModalProps {
  onClose: () => void;
  user?: AuthUser | null;
  onUserUpdated?: (user: AuthUser) => void;
}

const THEME_OPTIONS: AppTheme[] = ["dark", "light", "homebrew", "monochrome"];

export function ThemeSettingsModal({ onClose, user, onUserUpdated }: ThemeSettingsModalProps) {
  const { theme, setTheme } = useTheme();
  const [selected, setSelected] = useState<AppTheme>(theme);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleApply = async () => {
    setIsSaving(true);
    setError(null);
    try {
      setTheme(selected);
      if (user) {
        const response = await fetch("/api/auth/theme", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            theme_id: themeToId(selected),
            prod_mode: user.current_prod_mode === 2 ? 2 : 1,
          }),
        });
        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(payload?.detail ?? "테마 저장에 실패했습니다.");
        }
        const payload = (await response.json()) as Record<string, unknown>;
        onUserUpdated?.(userFromAuthResponse(payload));
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "테마 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
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
        <p className="mt-1 text-sm text-slate-400">
          현재 관리 플랫폼({user?.current_prod_mode === 2 ? "운영" : "개발"})에 적용할 색상 테마를
          선택합니다.
        </p>

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
              <span className="text-sm font-medium">
                {THEME_LABELS[option]}
                {option === theme ? " (현재)" : ""}
              </span>
            </label>
          ))}
        </div>

        {error ? (
          <div className="mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isSaving}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={() => void handleApply()}
            disabled={isSaving}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:bg-slate-700"
          >
            {isSaving ? "저장 중..." : "적용"}
          </button>
        </div>
      </div>
    </div>
  );
}
