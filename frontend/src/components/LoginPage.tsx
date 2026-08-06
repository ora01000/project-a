import { useEffect, useState } from "react";

import type { AuthUser } from "../types/auth";
import { startAuthSession, userFromAuthResponse } from "../utils/authSession";
import { isWelcomeBackHiddenToday } from "../utils/welcomeBackHide";
import { AdminBypassPasskeyModal } from "./AdminBypassPasskeyModal";
import { MadangRegisterModal } from "./MadangRegisterModal";
import { PendingApprovalModal } from "./PendingApprovalModal";
import { ConfirmDialog } from "./ConfirmDialog";
import { PasswordInput } from "./PasswordInput";
import { ProfileCompleteModal } from "./ProfileCompleteModal";
import { WelcomeBackModal, type WelcomeNoticeItem } from "./WelcomeBackModal";
import { RegisterUserModal } from "./users/RegisterUserModal";

interface LoginPageProps {
  onLoginSuccess: (user: AuthUser, accessToken: string, expiresInSeconds: number) => void;
}

interface AuthProviderInfo {
  provider_type: string;
  registration_enabled: boolean;
  madang_auth?: boolean;
}

interface LoginResponse extends AuthUser {
  access_token?: string;
  expires_in?: number;
  profile_required?: boolean;
  registration_required?: boolean;
  welcome_back?: boolean;
  previous_last_login?: string | null;
  welcome_notices?: WelcomeNoticeItem[];
}

interface MadangRegistrationState {
  userid: string;
  password: string;
}

interface WelcomeBackState {
  user: AuthUser;
  accessToken: string;
  expiresInSeconds: number;
  previousLastLogin: string | null;
  notices: WelcomeNoticeItem[];
}

interface PendingProfileState {
  user: AuthUser;
  accessToken: string;
  expiresInSeconds: number;
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [userid, setUserid] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [showPendingApproval, setShowPendingApproval] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [registrationEnabled, setRegistrationEnabled] = useState(true);
  const [madangAuth, setMadangAuth] = useState(false);
  const [pendingProfile, setPendingProfile] = useState<PendingProfileState | null>(null);
  const [madangRegistration, setMadangRegistration] = useState<MadangRegistrationState | null>(null);
  const [welcomeBack, setWelcomeBack] = useState<WelcomeBackState | null>(null);
  const [showAdminBypassModal, setShowAdminBypassModal] = useState(false);
  const [adminBypassError, setAdminBypassError] = useState<string | null>(null);

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
          setMadangAuth(Boolean(data.madang_auth));
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

  const completeLogin = (payload: LoginResponse) => {
    const accessToken = payload.access_token;
    const expiresInSeconds = payload.expires_in ?? 3600;
    if (!accessToken) {
      throw new Error("로그인 토큰을 받지 못했습니다.");
    }

    const user = userFromAuthResponse(payload as unknown as Record<string, unknown>);

    if (payload.profile_required) {
      startAuthSession(user, accessToken, expiresInSeconds);
      setPendingProfile({ user, accessToken, expiresInSeconds });
      return;
    }

    if (payload.welcome_back) {
      if (isWelcomeBackHiddenToday()) {
        onLoginSuccess(user, accessToken, expiresInSeconds);
        return;
      }
      setWelcomeBack({
        user,
        accessToken,
        expiresInSeconds,
        previousLastLogin: payload.previous_last_login ?? null,
        notices: payload.welcome_notices ?? [],
      });
      return;
    }

    onLoginSuccess(user, accessToken, expiresInSeconds);
  };

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
        setPassword("");
        setShowPendingApproval(true);
        return;
      }

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "로그인에 실패했습니다.");
      }

      const payload = (await response.json()) as LoginResponse;

      if (payload.registration_required) {
        setMadangRegistration({ userid: trimmedUserid, password });
        return;
      }

      completeLogin(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleAdminBypassClick = () => {
    setError(null);
    setAdminBypassError(null);
    setShowAdminBypassModal(true);
  };

  const handleAdminBypassSubmit = async (passkey: string) => {
    setIsLoading(true);
    setAdminBypassError(null);

    try {
      const response = await fetch("/api/auth/madang/admin-bypass", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passkey }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "관리자 로그인에 실패했습니다.");
      }

      const payload = (await response.json()) as LoginResponse;
      setShowAdminBypassModal(false);
      setAdminBypassError(null);
      completeLogin(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "관리자 로그인에 실패했습니다.";
      setAdminBypassError(message);
      if (message.includes("지정 사용자를 찾을 수 없습니다")) {
        setShowAdminBypassModal(false);
        setError(message);
      }
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
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              {madangAuth
                ? "마당ID/마당PW 로 로그인하시기 바랍니다. * 마당ID는 이메일도메인(@lguplus.co.kr/@lgupluspartners.co.kr)를 포함하지 않습니다."
                : "로그인 후 대시보드를 이용할 수 있습니다."}
            </p>
            {madangAuth ? (
              <p className="mt-2 inline-block rounded-full border border-sky-700 bg-sky-950/50 px-3 py-1 text-xs font-medium text-sky-300">
                마당(Madang) 인증
              </p>
            ) : null}
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

            {madangAuth ? (
              <button
                type="button"
                disabled={isLoading}
                onClick={handleAdminBypassClick}
                className="w-full rounded-md border border-amber-700/80 bg-amber-950/30 px-4 py-2.5 text-sm font-medium text-amber-100 transition hover:bg-amber-950/50 disabled:cursor-not-allowed disabled:text-slate-500"
              >
                관리자 로그인
              </button>
            ) : null}

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

      {madangRegistration ? (
        <MadangRegisterModal
          userid={madangRegistration.userid}
          password={madangRegistration.password}
          onClose={() => setMadangRegistration(null)}
          onSuccess={(message) => {
            setMadangRegistration(null);
            setPassword("");
            setSuccessMessage(message);
          }}
        />
      ) : null}

      {pendingProfile ? (
        <ProfileCompleteModal
          user={pendingProfile.user}
          onSaved={(updated) => {
            const { accessToken, expiresInSeconds } = pendingProfile;
            setPendingProfile(null);
            onLoginSuccess(updated, accessToken, expiresInSeconds);
          }}
        />
      ) : null}

      {welcomeBack ? (
        <WelcomeBackModal
          username={welcomeBack.user.username}
          band={welcomeBack.user.band}
          previousLastLogin={welcomeBack.previousLastLogin}
          notices={welcomeBack.notices}
          onClose={() => {
            const { user, accessToken, expiresInSeconds } = welcomeBack;
            setWelcomeBack(null);
            onLoginSuccess(user, accessToken, expiresInSeconds);
          }}
        />
      ) : null}

      {showPendingApproval ? (
        <PendingApprovalModal
          onClose={() => {
            setShowPendingApproval(false);
            setPassword("");
          }}
        />
      ) : null}

      {showAdminBypassModal ? (
        <AdminBypassPasskeyModal
          onClose={() => {
            if (!isLoading) {
              setShowAdminBypassModal(false);
              setAdminBypassError(null);
            }
          }}
          onSubmit={(passkey) => void handleAdminBypassSubmit(passkey)}
          isLoading={isLoading}
          error={adminBypassError}
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
