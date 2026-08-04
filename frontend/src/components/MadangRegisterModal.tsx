import { useState } from "react";

import { BAND_OPTIONS } from "../types/user";

const EMAIL_DOMAINS = ["@lguplus.co.kr", "@lgupluspartners.co.kr"] as const;

interface MadangRegisterModalProps {
  userid: string;
  password: string;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

export function MadangRegisterModal({
  userid,
  password,
  onClose,
  onSuccess,
}: MadangRegisterModalProps) {
  const [emailLocal, setEmailLocal] = useState("");
  const [emailDomain, setEmailDomain] = useState<(typeof EMAIL_DOMAINS)[number]>(
    EMAIL_DOMAINS[0],
  );
  const [username, setUsername] = useState("");
  const [depart, setDepart] = useState("");
  const [requestReason, setRequestReason] = useState("");
  const [band, setBand] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!emailLocal.trim() || !username.trim() || !depart.trim() || !requestReason.trim()) {
      setError("필수 항목을 입력해 주세요.");
      return;
    }
    if (emailLocal.includes("@")) {
      setError("이메일은 @ 앞 아이디만 입력해 주세요.");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/madang/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userid,
          password,
          email_local: emailLocal.trim(),
          email_domain: emailDomain,
          username: username.trim(),
          depart: depart.trim(),
          request_reason: requestReason.trim(),
          band,
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
        <p className="mt-1 text-sm text-slate-400">
          마당 인증이 확인되었습니다. 추가 정보를 입력해 주세요.
        </p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>아이디</span>
            <input
              value={userid}
              disabled
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>이메일</span>
            <div className="flex gap-2">
              <input
                value={emailLocal}
                onChange={(event) => setEmailLocal(event.target.value)}
                disabled={isSaving}
                placeholder="아이디"
                className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
              />
              <select
                value={emailDomain}
                onChange={(event) =>
                  setEmailDomain(event.target.value as (typeof EMAIL_DOMAINS)[number])
                }
                disabled={isSaving}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
              >
                {EMAIL_DOMAINS.map((domain) => (
                  <option key={domain} value={domain}>
                    {domain}
                  </option>
                ))}
              </select>
            </div>
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
            <span>요청 사유</span>
            <textarea
              value={requestReason}
              onChange={(event) => setRequestReason(event.target.value)}
              disabled={isSaving}
              maxLength={200}
              rows={3}
              placeholder="접속 권한이 필요한 사유를 입력해 주세요."
              className="w-full resize-none rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>직급</span>
            <select
              value={band}
              onChange={(event) => setBand(Number(event.target.value))}
              disabled={isSaving}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            >
              {BAND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
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
              disabled={isSaving}
              onClick={onClose}
              className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:text-slate-500"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:bg-slate-700"
            >
              {isSaving ? "등록 중..." : "가입 신청"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
