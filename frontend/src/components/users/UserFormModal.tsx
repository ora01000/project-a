import { useEffect, useState } from "react";

import { PasswordInput } from "../PasswordInput";
import type { UserFormValues, UserRecord } from "../../types/user";
import { BAND_OPTIONS, EMPTY_USER_FORM } from "../../types/user";

interface UserFormModalProps {
  mode: "create" | "edit";
  user?: UserRecord;
  onClose: () => void;
  onSave: (values: UserFormValues) => Promise<void>;
}

export function UserFormModal({ mode, user, onClose, onSave }: UserFormModalProps) {
  const [values, setValues] = useState<UserFormValues>(EMPTY_USER_FORM);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (mode === "edit" && user) {
      setValues({
        userid: user.userid,
        email: user.email,
        username: user.username,
        password: "",
        depart: user.depart,
        role: user.role,
        band: user.band ?? 1,
      });
      return;
    }

    setValues(EMPTY_USER_FORM);
  }, [mode, user]);

  const updateField = <K extends keyof UserFormValues>(key: K, value: UserFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!values.userid.trim() && mode === "create") {
      setError("아이디를 입력해 주세요.");
      return;
    }
    if (!values.email.trim() || !values.username.trim() || !values.depart.trim()) {
      setError("필수 항목을 입력해 주세요.");
      return;
    }
    if (mode === "create" && !values.password.trim()) {
      setError("패스워드를 입력해 주세요.");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await onSave(values);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-slate-100">
          {mode === "create" ? "사용자 추가" : "사용자 수정"}
        </h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>아이디</span>
            <input
              value={values.userid}
              onChange={(event) => updateField("userid", event.target.value)}
              disabled={mode === "edit" || isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500 disabled:text-slate-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>이메일</span>
            <input
              value={values.email}
              onChange={(event) => updateField("email", event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>이름</span>
            <input
              value={values.username}
              onChange={(event) => updateField("username", event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>패스워드</span>
            <PasswordInput
              value={values.password}
              onChange={(value) => updateField("password", value)}
              disabled={isSaving}
              placeholder={mode === "edit" ? "변경 시에만 입력" : undefined}
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>조직</span>
            <input
              value={values.depart}
              onChange={(event) => updateField("depart", event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>직책 (band)</span>
            <select
              value={values.band}
              onChange={(event) => updateField("band", Number(event.target.value))}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            >
              {BAND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.value}: {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>역할</span>
            <select
              value={values.role}
              onChange={(event) => updateField("role", Number(event.target.value))}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            >
              <option value={0}>0: admin</option>
              <option value={1}>1: user</option>
              <option value={5}>5: 보류</option>
            </select>
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
