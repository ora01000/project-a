import { useState } from "react";

import { PasswordInput } from "../PasswordInput";

export interface RegisterFormValues {
  userid: string;
  email: string;
  username: string;
  password: string;
  depart: string;
}

interface RegisterUserModalProps {
  onClose: () => void;
  onSuccess: (message: string) => void;
}

const EMPTY_FORM: RegisterFormValues = {
  userid: "",
  email: "",
  username: "",
  password: "",
  depart: "",
};

export function RegisterUserModal({ onClose, onSuccess }: RegisterUserModalProps) {
  const [values, setValues] = useState<RegisterFormValues>(EMPTY_FORM);
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const isPasswordMatched =
    values.password.length > 0 &&
    passwordConfirm.length > 0 &&
    values.password === passwordConfirm;

  const updateField = <K extends keyof RegisterFormValues>(key: K, value: RegisterFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!values.userid.trim() || !values.email.trim() || !values.username.trim() || !values.depart.trim()) {
      setError("필수 항목을 입력해 주세요.");
      return;
    }
    if (!values.password.trim()) {
      setError("패스워드를 입력해 주세요.");
      return;
    }
    if (values.password !== passwordConfirm) {
      setError("패스워드와 패스워드 확인이 일치하지 않습니다.");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userid: values.userid.trim(),
          email: values.email.trim(),
          username: values.username.trim(),
          password: values.password,
          depart: values.depart.trim(),
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "가입 신청에 실패했습니다.");
      }

      const payload = (await response.json()) as { message: string };
      onSuccess(payload.message);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "가입 신청에 실패했습니다.");
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
        <h2 className="text-lg font-semibold text-slate-100">신규 사용자 등록</h2>
        <p className="mt-1 text-sm text-slate-400">가입 신청 후 관리자 승인이 완료되면 로그인할 수 있습니다.</p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>아이디</span>
            <input
              value={values.userid}
              onChange={(event) => updateField("userid", event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
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
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>패스워드 확인</span>
            <PasswordInput
              value={passwordConfirm}
              onChange={setPasswordConfirm}
              disabled={isSaving}
            />
          </label>

          {passwordConfirm.length > 0 && !isPasswordMatched ? (
            <p className="text-sm text-rose-300">패스워드가 일치하지 않습니다.</p>
          ) : null}

          <label className="block space-y-1 text-sm text-slate-300">
            <span>조직</span>
            <input
              value={values.depart}
              onChange={(event) => updateField("depart", event.target.value)}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
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
              disabled={isSaving || !isPasswordMatched}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {isSaving ? "제출 중..." : "제출"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
