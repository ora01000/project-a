import { useEffect, useState } from "react";

import type { AuthUser } from "../types/auth";
import { roleLabel } from "../types/user";
import { PasswordInput } from "./PasswordInput";

interface ProfileEditModalProps {
  user: AuthUser;
  onClose: () => void;
  onSaved: (user: AuthUser) => void;
}

export function ProfileEditModal({ user, onClose, onSaved }: ProfileEditModalProps) {
  const [email, setEmail] = useState(user.email);
  const [username, setUsername] = useState(user.username);
  const [depart, setDepart] = useState(user.depart);
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setEmail(user.email);
    setUsername(user.username);
    setDepart(user.depart);
    setPassword("");
    setPasswordConfirm("");
    setError(null);
  }, [user]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim() || !username.trim() || !depart.trim()) {
      setError("이메일, 이름, 조직을 입력해 주세요.");
      return;
    }

    const nextPassword = password.trim();
    const nextPasswordConfirm = passwordConfirm.trim();
    if (nextPassword || nextPasswordConfirm) {
      if (nextPassword !== nextPasswordConfirm) {
        setError("패스워드와 패스워드 확인이 일치하지 않습니다.");
        return;
      }
      if (!nextPassword) {
        setError("패스워드를 입력해 주세요.");
        return;
      }
    }

    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idx: user.idx,
          email: email.trim(),
          username: username.trim(),
          depart: depart.trim(),
          password: nextPassword ? nextPassword : null,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "개인정보 저장에 실패했습니다.");
      }
      const updated = (await response.json()) as AuthUser;
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "개인정보 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-edit-dialog-title"
        className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="profile-edit-dialog-title" className="text-lg font-semibold text-slate-100">
          개인정보 수정
        </h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>아이디</span>
            <input
              value={user.userid}
              disabled
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>역할</span>
            <input
              value={`${user.role}: ${roleLabel(user.role)}`}
              disabled
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>이메일</span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>이름</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>조직</span>
            <input
              value={depart}
              onChange={(event) => setDepart(event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>패스워드</span>
            <PasswordInput
              value={password}
              onChange={setPassword}
              disabled={isSaving}
              placeholder="변경 시에만 입력"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>패스워드 확인</span>
            <PasswordInput
              value={passwordConfirm}
              onChange={setPasswordConfirm}
              disabled={isSaving}
              placeholder="변경 시에만 입력"
            />
          </label>

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
              {isSaving ? "저장 중..." : "저장"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
