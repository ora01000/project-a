interface InventoryTokenIssueTestResult {
  token_api: string;
  token_api_method: string;
  ok: boolean;
  status_code: number | null;
  elapsed_ms: number | null;
  content_type: string | null;
  access_token_length: number | null;
  token_type: string | null;
  expires_in: string | null;
  error: string | null;
  message: string | null;
}

interface InventoryTokenIssueTestModalProps {
  result: InventoryTokenIssueTestResult;
  onClose: () => void;
}

export function InventoryTokenIssueTestModal({
  result,
  onClose,
}: InventoryTokenIssueTestModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="inventory-token-issue-test-title"
        className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2
              id="inventory-token-issue-test-title"
              className="text-lg font-semibold text-slate-100"
            >
              토큰 발급 테스트 결과
            </h2>
            <p
              className="mt-1 break-all font-mono text-xs text-slate-400"
              title={result.token_api}
            >
              {result.token_api_method || "POST"} {result.token_api || "-"}
            </p>
          </div>
          <span
            className={`shrink-0 rounded-md border px-2 py-0.5 text-xs font-medium ${
              result.ok
                ? "border-emerald-700 bg-emerald-950/50 text-emerald-200"
                : "border-rose-700 bg-rose-950/50 text-rose-200"
            }`}
          >
            {result.ok ? "성공" : "실패"}
          </span>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt className="text-[11px] text-slate-500">HTTP status</dt>
            <dd className="font-mono text-slate-100">
              {result.status_code == null ? "-" : result.status_code}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">소요 시간</dt>
            <dd className="font-mono text-slate-100">
              {result.elapsed_ms == null ? "-" : `${result.elapsed_ms} ms`}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">Content-Type</dt>
            <dd
              className="truncate font-mono text-slate-100"
              title={result.content_type ?? undefined}
            >
              {result.content_type || "-"}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">token_type</dt>
            <dd className="font-mono text-slate-100">{result.token_type || "-"}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">access_token_length</dt>
            <dd className="font-mono text-slate-100">
              {result.access_token_length == null ? "-" : result.access_token_length}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">expires_in</dt>
            <dd className="font-mono text-slate-100">{result.expires_in || "-"}</dd>
          </div>
          {result.error ? (
            <div className="col-span-2">
              <dt className="text-[11px] text-slate-500">error</dt>
              <dd className="font-mono text-xs text-rose-200">{result.error}</dd>
            </div>
          ) : null}
          {result.message ? (
            <div className="col-span-2">
              <dt className="text-[11px] text-slate-500">message</dt>
              <dd className="font-mono text-xs text-slate-300">{result.message}</dd>
            </div>
          ) : null}
        </dl>

        <p className="mt-3 text-[11px] text-slate-500">
          access_token 값은 반환되지 않습니다. 길이·타입·만료만 확인합니다.
        </p>

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 bg-slate-800/70 px-3 py-1.5 text-sm text-slate-100 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

export type { InventoryTokenIssueTestResult };
