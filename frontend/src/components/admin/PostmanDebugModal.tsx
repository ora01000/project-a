import { useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface PostmanDebugModalProps {
  viewerRole: number;
  onClose: () => void;
}

const EXAMPLE_CALL_INFO = `POST https://example.com/portal/auths/v1/token HTTP/1.1
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials`;

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function PostmanDebugModal({ viewerRole, onClose }: PostmanDebugModalProps) {
  const [callInfo, setCallInfo] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);

  const handleSend = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 실행할 수 있습니다.");
      return;
    }
    if (!callInfo.trim()) {
      setError("호출정보를 입력해 주세요.");
      return;
    }

    setIsSending(true);
    setError(null);
    setResult("");
    try {
      const response = await fetch("/api/debug/postman", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          viewer_role: viewerRole,
          call_info: callInfo,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "HTTP 요청 전송에 실패했습니다."));
      }
      const data = (await response.json()) as { raw_response: string };
      setResult(data.raw_response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "HTTP 요청 전송에 실패했습니다.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="postman-debug-dialog-title"
        className="flex max-h-[90vh] w-full max-w-5xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="postman-debug-dialog-title" className="text-lg font-semibold text-slate-100">
            Postman 디버깅
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <p className="mt-2 text-sm text-slate-400">
          호출정보에 HTTP 요청 원문을 입력한 뒤 전송하면 백엔드에서 그대로 HTTP 호출합니다.
        </p>

        <label className="mt-4 block text-sm font-medium text-slate-200" htmlFor="postman-call-info">
          호출정보
        </label>
        <textarea
          id="postman-call-info"
          value={callInfo}
          onChange={(event) => setCallInfo(event.target.value)}
          placeholder={EXAMPLE_CALL_INFO}
          rows={12}
          className="mt-2 w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-600 focus:outline-none"
        />

        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={isSending}
            className="rounded-md border border-sky-700 bg-sky-950/40 px-4 py-2 text-sm text-sky-100 hover:bg-sky-900/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSending ? "전송 중…" : "전송"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

        <label className="mt-5 block text-sm font-medium text-slate-200" htmlFor="postman-result">
          결과
        </label>
        <textarea
          id="postman-result"
          value={result}
          readOnly
          rows={14}
          placeholder={isSending ? "응답을 기다리는 중…" : "전송 후 응답이 여기에 표시됩니다."}
          className="mt-2 w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none"
        />
      </div>
    </div>
  );
}
