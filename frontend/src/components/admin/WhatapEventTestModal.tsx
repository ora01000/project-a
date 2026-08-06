import { useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface WhatapEventTestModalProps {
  viewerRole: number;
  onClose: () => void;
}

const EXAMPLE_JSON = `{
  "projectName": "dprv6-k8s",
  "time": 1722900000000,
  "eventType": "alert",
  "serverName": "node-1",
  "level": "warning"
}`;

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function WhatapEventTestModal({ viewerRole, onClose }: WhatapEventTestModalProps) {
  const [jsonText, setJsonText] = useState(EXAMPLE_JSON);
  const [result, setResult] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);

  const handleSend = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 실행할 수 있습니다.");
      return;
    }

    const trimmed = jsonText.trim();
    if (!trimmed) {
      setError("JSON을 입력해 주세요.");
      return;
    }

    let payload: unknown;
    try {
      payload = JSON.parse(trimmed);
    } catch {
      setError("JSON 형식이 올바르지 않습니다.");
      return;
    }

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      setError("JSON은 객체(object) 형식이어야 합니다.");
      return;
    }

    setIsSending(true);
    setError(null);
    setResult("");
    try {
      const response = await fetch("/api/admin/whatap-event-test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "Whatap 이벤트 전송에 실패했습니다."));
      }
      const data = await response.json();
      setResult(JSON.stringify(data, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Whatap 이벤트 전송에 실패했습니다.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="whatap-event-test-dialog-title"
        className="flex max-h-[90vh] w-full max-w-5xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="whatap-event-test-dialog-title" className="text-lg font-semibold text-slate-100">
            Whatap 이벤트 테스트
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
          Whatap Webhook으로 수신되는 JSON을 입력하고 전송하면 작업(job_type=2)이 자동 제출됩니다.
        </p>

        <label className="mt-4 block text-sm font-medium text-slate-200" htmlFor="whatap-event-json">
          JSON
        </label>
        <textarea
          id="whatap-event-json"
          value={jsonText}
          onChange={(event) => setJsonText(event.target.value)}
          placeholder={EXAMPLE_JSON}
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

        <label className="mt-5 block text-sm font-medium text-slate-200" htmlFor="whatap-event-result">
          결과
        </label>
        <textarea
          id="whatap-event-result"
          value={result}
          readOnly
          rows={10}
          placeholder={isSending ? "처리 중…" : "전송 후 응답이 여기에 표시됩니다."}
          className="mt-2 w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none"
        />
      </div>
    </div>
  );
}
