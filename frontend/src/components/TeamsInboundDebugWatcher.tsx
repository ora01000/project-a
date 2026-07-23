import { useCallback, useEffect, useRef, useState } from "react";

interface TeamsInboundDebugMessage {
  id: number;
  received_at: string;
  content_type: string;
  headers: Record<string, string>;
  body_text: string;
  dismissed: boolean;
}

const POLL_INTERVAL_MS = 3000;

export function TeamsInboundDebugWatcher() {
  const [activeMessage, setActiveMessage] = useState<TeamsInboundDebugMessage | null>(null);
  const shownIdsRef = useRef<Set<number>>(new Set());

  const pollPending = useCallback(async () => {
    try {
      const response = await fetch("/api/debug/teams-power-automate/pending");
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as { messages: TeamsInboundDebugMessage[] };
      const next = data.messages.find((message) => !shownIdsRef.current.has(message.id));
      if (next) {
        setActiveMessage(next);
      }
    } catch {
      // ignore polling errors
    }
  }, []);

  useEffect(() => {
    void pollPending();
    const interval = window.setInterval(() => {
      void pollPending();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [pollPending]);

  const handleDismiss = useCallback(async () => {
    if (!activeMessage) {
      return;
    }
    const messageId = activeMessage.id;
    shownIdsRef.current.add(messageId);
    setActiveMessage(null);
    try {
      await fetch(`/api/debug/teams-power-automate/${messageId}/dismiss`, {
        method: "POST",
      });
    } catch {
      // popup already closed locally
    }
  }, [activeMessage]);

  if (!activeMessage) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/75 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="teams-inbound-debug-title"
        className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl border border-amber-700/50 bg-slate-900 shadow-xl"
      >
        <header className="shrink-0 border-b border-slate-700 px-5 py-4">
          <h2 id="teams-inbound-debug-title" className="text-base font-semibold text-amber-100">
            Teams / Power Automate 수신 메시지
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            #{activeMessage.id} · {activeMessage.received_at} · {activeMessage.content_type}
          </p>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-auto px-5 py-4">
          <div>
            <div className="mb-1 text-xs font-medium text-slate-400">Headers</div>
            <pre className="max-h-32 overflow-auto rounded-md border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-300">
              {JSON.stringify(activeMessage.headers, null, 2)}
            </pre>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-slate-400">Body</div>
            <pre className="overflow-auto rounded-md border border-slate-800 bg-slate-950/80 p-3 text-xs whitespace-pre-wrap text-slate-100">
              {activeMessage.body_text || "(empty body)"}
            </pre>
          </div>
        </div>

        <footer className="flex shrink-0 justify-end border-t border-slate-700 px-5 py-4">
          <button
            type="button"
            onClick={() => void handleDismiss()}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
          >
            닫기
          </button>
        </footer>
      </div>
    </div>
  );
}
