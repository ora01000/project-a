import { useState } from "react";

import { useTheme } from "../context/ThemeContext";
import type { AuthUser } from "../types/auth";
import { themeFromId } from "../types/theme";
import { userFromAuthResponse } from "../utils/authSession";

const PLATFORM_MODE_OPTIONS = [
  { value: 1, label: "개발" },
  { value: 2, label: "운영" },
] as const;

export function platformModeLabel(mode: number | null | undefined): string {
  return mode === 2 ? "운영" : "개발";
}

interface PlatformModeModalProps {
  user: AuthUser;
  onClose: () => void;
  onChanged: (user: AuthUser) => void;
}

export function PlatformModeModal({ user, onClose, onChanged }: PlatformModeModalProps) {
  const { setTheme } = useTheme();
  const currentMode = user.current_prod_mode === 2 ? 2 : 1;
  const [selectedMode, setSelectedMode] = useState<number>(currentMode);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (selectedMode === currentMode) {
      onClose();
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/prod-mode", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_prod_mode: selectedMode }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "관리 플랫폼 변경에 실패했습니다.");
      }
      const payload = (await response.json()) as Record<string, unknown>;
      const updated = userFromAuthResponse(payload);
      const themeId =
        selectedMode === 2 ? updated.theme_for_prod_mode : updated.theme_for_dev_mode;
      setTheme(themeFromId(themeId));
      onChanged(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "관리 플랫폼 변경에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="platform-mode-dialog-title"
        className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="platform-mode-dialog-title" className="text-lg font-semibold text-slate-100">
          관리 플랫폼 선택
        </h2>

        <form onSubmit={(event) => void handleSubmit(event)} className="mt-4 space-y-3">
          <div className="space-y-2">
            {PLATFORM_MODE_OPTIONS.map((option) => {
              const isDisabled = isSaving || (option.value === 2 && !user.prod_auth);
              return (
                <label
                  key={option.value}
                  className={`flex items-center gap-2 text-sm ${
                    isDisabled ? "text-slate-500" : "text-slate-200"
                  }`}
                >
                  <input
                    type="radio"
                    name="platform-mode"
                    value={option.value}
                    checked={selectedMode === option.value}
                    disabled={isDisabled}
                    onChange={() => setSelectedMode(option.value)}
                    className="h-4 w-4 border-slate-600 bg-slate-950 text-sky-500 focus:ring-sky-500"
                  />
                  <span>{option.label}</span>
                  {option.value === 2 && !user.prod_auth ? (
                    <span className="text-xs text-slate-500">(운영 플랫폼 관리 권한 없음)</span>
                  ) : null}
                </label>
              );
            })}
          </div>

          {error ? (
            <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
              {error}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSaving}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              닫기
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:bg-slate-700"
            >
              {isSaving ? "저장 중..." : "선택"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
