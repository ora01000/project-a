import { useEffect, useState } from "react";

import type { AuthUser } from "../types/auth";
import { ConfirmDialog } from "./ConfirmDialog";
import { PasswordInput } from "./PasswordInput";
import { ProfileCompleteModal } from "./ProfileCompleteModal";
import { WelcomeBackModal } from "./WelcomeBackModal";
import { RegisterUserModal } from "./users/RegisterUserModal";

interface LoginPageProps {
  onLoginSuccess: (user: AuthUser) => void;
}

interface AuthProviderInfo {
  provider_type: string;
  registration_enabled: boolean;
}

interface ApproverJobSummary {
  idx: number;
  job_title: string;
  request_date: string;
  requester: string;
  request_depart: string;
  state: number;
  state_label: string;
  completion_request_date: string;
}

interface LoginResponse extends AuthUser {
  profile_required?: boolean;
  welcome_back?: boolean;
  previous_last_login?: string | null;
  approver_jobs?: ApproverJobSummary[];
}

interface WelcomeBackState {
  user: AuthUser;
  previousLastLogin: string | null;
  jobs: ApproverJobSummary[];
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [userid, setUserid] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [registrationEnabled, setRegistrationEnabled] = useState(true);
  const [pendingProfileUser, setPendingProfileUser] = useState<AuthUser | null>(null);
  const [welcomeBack, setWelcomeBack] = useState<WelcomeBackState | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadProvider = async () => {
      try {
        const response = await fetch("/api/auth/provider");
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as AuthProviderInfo;
        if (!cancelled) {
          setRegistrationEnabled(Boolean(data.registration_enabled));
        }
      } catch {
        // default: keep registration enabled (db mode)
      }
    };
    void loadProvider();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedUserid = userid.trim();
    if (!trimmedUserid || !password) {
      setError("아이디와 비밀번호를 입력해 주세요.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userid: trimmedUserid, password }),
      });

      if (response.status === 403) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setPendingMessage(payload?.detail ?? "가입 승인 대기 중입니다. 관리자에게 문의해 주세요.");
        return;
      }

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "로그인에 실패했습니다.");
      }

      const payload = (await response.json()) as LoginResponse;
      const user: AuthUser = {
        idx: payload.idx,
        userid: payload.userid,
        email: payload.email,
        username: payload.username,
        depart: payload.depart,
        role: payload.role,
        agents: payload.agents ?? "",
        agent_ids: payload.agent_ids ?? [],
      };

      if (payload.profile_required) {
        setPendingProfileUser(user);
        return;
      }

      if (payload.welcome_back) {
        setWelcomeBack({
          user,
          previousLastLogin: payload.previous_last_login ?? null,
          jobs: payload.approver_jobs ?? [],
        });
        return;
      }

      onLoginSuccess(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <div className="flex min-h-screen items-center justify-center bg-slate-950 px-6 py-10">
        <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900/90 p-8 shadow-lg">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-slate-100">AX 인프라 운영 콘솔</h1>
            <p className="mt-2 text-sm text-slate-400">로그인 후 대시보드를 이용할 수 있습니다.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <label className="block space-y-1 text-sm text-slate-300">
              <span>아이디</span>
              <input
                value={userid}
                onChange={(event) => setUserid(event.target.value)}
                autoComplete="username"
                disabled={isLoading}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
              />
            </label>

            <label className="block space-y-1 text-sm text-slate-300">
              <span>패스워드</span>
              <PasswordInput
                value={password}
                onChange={setPassword}
                autoComplete="current-password"
                disabled={isLoading}
              />
            </label>

            {error ? (
              <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
                {error}
              </div>
            ) : null}

            {successMessage ? (
              <div className="rounded-md border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-200">
                {successMessage}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-md bg-sky-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {isLoading ? "로그인 중..." : "로그인"}
            </button>

            {registrationEnabled ? (
              <button
                type="button"
                disabled={isLoading}
                onClick={() => {
                  setError(null);
                  setSuccessMessage(null);
                  setShowRegisterModal(true);
                }}
                className="w-full rounded-md border border-slate-600 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
              >
                신규 등록
              </button>
            ) : null}
          </form>
        </div>
      </div>

      {showRegisterModal && registrationEnabled ? (
        <RegisterUserModal
          onClose={() => setShowRegisterModal(false)}
          onSuccess={(message) => setSuccessMessage(message)}
        />
      ) : null}

      {pendingProfileUser ? (
        <ProfileCompleteModal
          user={pendingProfileUser}
          onSaved={(updated) => {
            setPendingProfileUser(null);
            onLoginSuccess(updated);
          }}
        />
      ) : null}

      {welcomeBack ? (
        <WelcomeBackModal
          username={welcomeBack.user.username}
          previousLastLogin={welcomeBack.previousLastLogin}
          jobs={welcomeBack.jobs}
          onClose={() => {
            const user = welcomeBack.user;
            setWelcomeBack(null);
            onLoginSuccess(user);
          }}
        />
      ) : null}

      {pendingMessage ? (
        <ConfirmDialog
          title="로그인 불가"
          message={pendingMessage}
          confirmLabel="확인"
          cancelLabel="닫기"
          onCancel={() => setPendingMessage(null)}
          onConfirm={() => setPendingMessage(null)}
        />
      ) : null}
    </>
  );
}
