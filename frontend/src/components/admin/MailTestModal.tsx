import { useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface MailTestModalProps {
  viewerRole: number;
  onClose: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

export function MailTestModal({ viewerRole, onClose }: MailTestModalProps) {
  const [toAddress, setToAddress] = useState("");
  const [subject, setSubject] = useState("AX 인프라 운영 콘솔 테스트 메일");
  const [body, setBody] = useState("메일 서버 설정 테스트입니다.");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);

  const handleSend = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 실행할 수 있습니다.");
      return;
    }
    const trimmed = toAddress.trim();
    if (!trimmed || !trimmed.includes("@")) {
      setError("수신 이메일 주소를 입력해 주세요.");
      return;
    }

    setIsSending(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/admin/mailserver-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_address: trimmed,
          subject: subject.trim(),
          body: body.trim(),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "테스트 메일 전송에 실패했습니다."));
      }
      const data = (await response.json()) as { message?: string };
      setResult(data.message ?? "전송 완료");
    } catch (err) {
      setError(err instanceof Error ? err.message : "테스트 메일 전송에 실패했습니다.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="mail-test-dialog-title"
        className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 id="mail-test-dialog-title" className="text-sm font-semibold text-slate-100">
              테스트 메일 발송
            </h2>
            <p className="mt-1 text-[11px] text-slate-400">
              저장된 메일 서버 설정으로 즉시 전송합니다. (활성화 여부와 무관)
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <label className="block space-y-1">
            <span className="text-slate-400">수신 주소</span>
            <input
              type="email"
              value={toAddress}
              onChange={(event) => setToAddress(event.target.value)}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-slate-100"
              placeholder="you@lguplus.co.kr"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-slate-400">제목</span>
            <input
              type="text"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-slate-400">본문</span>
            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={5}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
            />
          </label>
        </div>

        {error ? (
          <p className="mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-2 py-1.5 text-[11px] text-rose-200">
            {error}
          </p>
        ) : null}
        {result ? (
          <p className="mt-3 rounded-md border border-emerald-800 bg-emerald-950/40 px-2 py-1.5 text-[11px] text-emerald-200">
            {result}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            닫기
          </button>
          <button
            type="button"
            disabled={isSending}
            onClick={() => void handleSend()}
            className="rounded-md bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:opacity-50"
          >
            {isSending ? "전송 중..." : "보내기"}
          </button>
        </div>
      </div>
    </div>
  );
}
