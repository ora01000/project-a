import { useState } from "react";

import { PasswordInput } from "./PasswordInput";

interface AdminBypassPasskeyModalProps {
  onClose: () => void;
  onSubmit: (passkey: string) => void;
  isLoading: boolean;
  error: string | null;
}

export function AdminBypassPasskeyModal({
  onClose,
  onSubmit,
  isLoading,
  error,
}: AdminBypassPasskeyModalProps) {
  const [passkey, setPasskey] = useState("");

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = passkey.trim();
    if (!trimmed) {
      return;
    }
    onSubmit(trimmed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-bypass-passkey-title"
        className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="admin-bypass-passkey-title" className="text-base font-semibold text-slate-100">
          관리자 로그인
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          패스키를 입력하면 시스템 관리자(root) 계정으로 로그인합니다.
        </p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>패스키</span>
            <PasswordInput
              value={passkey}
              onChange={setPasskey}
              autoComplete="off"
              disabled={isLoading}
              placeholder="xxxx-xxxx-xxxx-xxxx"
            />
          </label>

          {error ? (
            <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
              {error}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-60"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {isLoading ? "확인 중..." : "확인"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
