import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "../ConfirmDialog";

interface TokenUsageRow {
  agent_id: string;
  agent_name: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  is_system: boolean;
}

interface TokenManagementPageProps {
  viewerRole: number;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function formatTokenCount(value: number): string {
  return value.toLocaleString("ko-KR");
}

export function TokenManagementPage({ viewerRole }: TokenManagementPageProps) {
  const [rows, setRows] = useState<TokenUsageRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [resetTarget, setResetTarget] = useState<TokenUsageRow | null>(null);
  const [isResetting, setIsResetting] = useState(false);

  const loadUsage = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/agents/token-usage?include_all=true");
      if (!response.ok) {
        throw new Error(await parseError(response, "토큰 사용량을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as { agents: TokenUsageRow[] };
      setRows(data.agents ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "토큰 사용량을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUsage();
    const interval = window.setInterval(() => {
      void loadUsage();
    }, 10_000);
    return () => window.clearInterval(interval);
  }, [loadUsage]);

  const handleReset = async () => {
    if (!resetTarget) {
      return;
    }
    setIsResetting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const response = await fetch(`/api/agents/token-usage/${encodeURIComponent(resetTarget.agent_id)}/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ viewer_role: viewerRole }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "토큰 초기화에 실패했습니다."));
      }
      setSuccessMessage(`"${resetTarget.agent_name}" 에이전트의 누적 토큰을 초기화했습니다.`);
      setResetTarget(null);
      await loadUsage();
    } catch (err) {
      setError(err instanceof Error ? err.message : "토큰 초기화에 실패했습니다.");
    } finally {
      setIsResetting(false);
    }
  };

  const totalInput = rows.reduce((sum, row) => sum + row.input_tokens, 0);
  const totalOutput = rows.reduce((sum, row) => sum + row.output_tokens, 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">토큰 관리</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            서버 기동 후 누적된 LLM 토큰 사용량입니다. 에이전트별로 초기화할 수 있습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadUsage()}
          className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
        >
          새로고침
        </button>
      </header>

      {error ? (
        <div className="mx-4 mt-4 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {successMessage ? (
        <div className="mx-4 mt-4 rounded-md border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-200">
          {successMessage}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">토큰 사용량을 불러오는 중...</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-500">등록된 에이전트가 없습니다.</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-slate-500">
              전체 합계 — 누적 입력 {formatTokenCount(totalInput)} / 누적 출력{" "}
              {formatTokenCount(totalOutput)} / 합계 {formatTokenCount(totalInput + totalOutput)}
            </p>
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-left text-slate-400">
                    <th className="px-3 py-2">에이전트 이름</th>
                    <th className="px-3 py-2">에이전트 ID</th>
                    <th className="px-3 py-2">구분</th>
                    <th className="px-3 py-2">누적 입력</th>
                    <th className="px-3 py-2">누적 출력</th>
                    <th className="px-3 py-2">합계</th>
                    <th className="px-3 py-2">초기화</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.agent_id} className="border-b border-slate-800 text-slate-200">
                      <td className="px-3 py-2">{row.agent_name}</td>
                      <td className="px-3 py-2 font-mono text-xs text-sky-200">{row.agent_id}</td>
                      <td className="px-3 py-2 text-xs text-slate-400">
                        {row.is_system ? "시스템" : "일반"}
                      </td>
                      <td className="px-3 py-2 font-mono">{formatTokenCount(row.input_tokens)}</td>
                      <td className="px-3 py-2 font-mono">{formatTokenCount(row.output_tokens)}</td>
                      <td className="px-3 py-2 font-mono">{formatTokenCount(row.total_tokens)}</td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => setResetTarget(row)}
                          disabled={row.total_tokens === 0}
                          className="rounded-md border border-amber-700 px-2 py-1 text-xs text-amber-100 hover:bg-amber-950/50 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          Reset
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {resetTarget ? (
        <ConfirmDialog
          title="토큰 사용량 초기화"
          message={`"${resetTarget.agent_name}" (${resetTarget.agent_id})의 누적 토큰을 초기화하시겠습니까?`}
          confirmLabel={isResetting ? "초기화 중…" : "초기화"}
          cancelLabel="취소"
          onCancel={() => {
            if (!isResetting) {
              setResetTarget(null);
            }
          }}
          onConfirm={() => void handleReset()}
        />
      ) : null}
    </div>
  );
}
