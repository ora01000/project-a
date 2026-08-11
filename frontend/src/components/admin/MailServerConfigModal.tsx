import { useEffect, useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface MailServerConfigModalProps {
  viewerRole: number;
  onClose: () => void;
}

interface MailserverConfig {
  enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  from_address: string;
  smtp_auth: boolean;
  use_tls: boolean;
  use_ssl: boolean;
  timeout_seconds: number;
  updated_at: string;
  has_password: boolean;
  suggested_profile: string;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

export function MailServerConfigModal({ viewerRole, onClose }: MailServerConfigModalProps) {
  const [enabled, setEnabled] = useState(false);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState(587);
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [hasPassword, setHasPassword] = useState(false);
  const [fromAddress, setFromAddress] = useState("");
  const [smtpAuth, setSmtpAuth] = useState(true);
  const [useTls, setUseTls] = useState(true);
  const [useSsl, setUseSsl] = useState(false);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [updatedAt, setUpdatedAt] = useState("");
  const [suggestedProfile, setSuggestedProfile] = useState("gmail");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 열람할 수 있습니다.");
      setIsLoading(false);
      return;
    }
    void (async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/admin/mailserver-config");
        if (!response.ok) {
          throw new Error(await parseError(response, "메일 서버 설정을 불러오지 못했습니다."));
        }
        const data = (await response.json()) as MailserverConfig;
        setEnabled(data.enabled);
        setSmtpHost(data.smtp_host);
        setSmtpPort(data.smtp_port);
        setSmtpUsername(data.smtp_username);
        setFromAddress(data.from_address);
        setSmtpAuth(data.smtp_auth);
        setUseTls(data.use_tls);
        setUseSsl(data.use_ssl);
        setTimeoutSeconds(data.timeout_seconds);
        setUpdatedAt(data.updated_at);
        setHasPassword(data.has_password);
        setSuggestedProfile(data.suggested_profile);
        setSmtpPassword("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "메일 서버 설정을 불러오지 못했습니다.");
      } finally {
        setIsLoading(false);
      }
    })();
  }, [viewerRole]);

  const handleSave = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 저장할 수 있습니다.");
      return;
    }
    setIsSaving(true);
    setError(null);
    setInfo(null);
    try {
      const response = await fetch("/api/admin/mailserver-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled,
          smtp_host: smtpHost,
          smtp_port: smtpPort,
          smtp_username: smtpUsername,
          smtp_password: smtpPassword || null,
          from_address: fromAddress,
          smtp_auth: smtpAuth,
          use_tls: useTls,
          use_ssl: useSsl,
          timeout_seconds: timeoutSeconds,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "메일 서버 설정 저장에 실패했습니다."));
      }
      const data = (await response.json()) as MailserverConfig;
      setUpdatedAt(data.updated_at);
      setHasPassword(data.has_password);
      setSmtpPassword("");
      setInfo("저장되었습니다.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "메일 서버 설정 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  const profileHint =
    suggestedProfile === "gmail"
      ? "목업/로컬: Gmail SMTP(smtp.gmail.com:587, TLS) 사용을 권장합니다. 앱 비밀번호가 필요할 수 있습니다."
      : "배포(http): 내부 SMTP 호스트를 입력하세요.";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="mailserver-config-dialog-title"
        className="flex max-h-[90vh] w-full max-w-xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 id="mailserver-config-dialog-title" className="text-sm font-semibold text-slate-100">
              메일 서버 설정
            </h2>
            <p className="mt-1 text-[11px] text-slate-400">{profileHint}</p>
            {updatedAt ? (
              <p className="mt-0.5 text-[10px] text-slate-500">마지막 저장: {updatedAt}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        {isLoading ? (
          <p className="text-xs text-slate-500">불러오는 중...</p>
        ) : (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto text-xs">
            <label className="flex items-center gap-2 text-slate-200">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              메일 발송 활성화
            </label>

            <label className="block space-y-1">
              <span className="text-slate-400">SMTP 호스트</span>
              <input
                type="text"
                value={smtpHost}
                onChange={(event) => setSmtpHost(event.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-slate-100"
                placeholder="smtp.gmail.com"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-slate-400">포트</span>
              <input
                type="number"
                value={smtpPort}
                onChange={(event) => setSmtpPort(Number(event.target.value) || 587)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-slate-100"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-slate-400">사용자명</span>
              <input
                type="text"
                value={smtpUsername}
                onChange={(event) => setSmtpUsername(event.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-slate-100"
                autoComplete="off"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-slate-400">
                비밀번호{hasPassword ? " (저장됨 — 비우면 유지)" : ""}
              </span>
              <div className="flex gap-2">
                <input
                  type={showPassword ? "text" : "password"}
                  value={smtpPassword}
                  onChange={(event) => setSmtpPassword(event.target.value)}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-slate-100"
                  placeholder={hasPassword ? "변경 시에만 입력" : ""}
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  className="shrink-0 rounded-md border border-slate-700 px-2 text-slate-300 hover:bg-slate-800"
                >
                  {showPassword ? "숨김" : "표시"}
                </button>
              </div>
            </label>

            <label className="block space-y-1">
              <span className="text-slate-400">발신 주소 (From)</span>
              <input
                type="email"
                value={fromAddress}
                onChange={(event) => setFromAddress(event.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-slate-100"
              />
            </label>

            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-slate-200">
                <input
                  type="checkbox"
                  checked={smtpAuth}
                  onChange={(event) => setSmtpAuth(event.target.checked)}
                />
                SMTP Auth
              </label>
              <label className="flex items-center gap-2 text-slate-200">
                <input
                  type="checkbox"
                  checked={useTls}
                  onChange={(event) => setUseTls(event.target.checked)}
                />
                STARTTLS
              </label>
              <label className="flex items-center gap-2 text-slate-200">
                <input
                  type="checkbox"
                  checked={useSsl}
                  onChange={(event) => setUseSsl(event.target.checked)}
                />
                SSL (SMTP_SSL)
              </label>
            </div>

            <label className="block space-y-1">
              <span className="text-slate-400">타임아웃(초)</span>
              <input
                type="number"
                value={timeoutSeconds}
                onChange={(event) => setTimeoutSeconds(Number(event.target.value) || 30)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-slate-100"
              />
            </label>
          </div>
        )}

        {error ? (
          <p className="mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-2 py-1.5 text-[11px] text-rose-200">
            {error}
          </p>
        ) : null}
        {info ? (
          <p className="mt-3 rounded-md border border-emerald-800 bg-emerald-950/40 px-2 py-1.5 text-[11px] text-emerald-200">
            {info}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            disabled={isLoading || isSaving}
            onClick={() => void handleSave()}
            className="rounded-md bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:opacity-50"
          >
            {isSaving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
