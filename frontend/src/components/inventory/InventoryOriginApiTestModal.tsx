interface InventoryOriginApiTestResult {
  url: string;
  ok: boolean;
  status_code: number | null;
  elapsed_ms: number | null;
  content_type: string | null;
  size_bytes: number | null;
  is_json: boolean | null;
  row_count: number | null;
  columns: string[];
  error: string | null;
  message: string | null;
}

interface InventoryOriginApiTestModalProps {
  result: InventoryOriginApiTestResult;
  onClose: () => void;
}

function formatBytes(value: number | null): string {
  if (value == null || !Number.isFinite(value)) {
    return "-";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

export function InventoryOriginApiTestModal({
  result,
  onClose,
}: InventoryOriginApiTestModalProps) {
  const columnsText =
    result.columns.length > 0 ? result.columns.join(", ") : "-";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="inventory-origin-api-test-title"
        className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2
              id="inventory-origin-api-test-title"
              className="text-lg font-semibold text-slate-100"
            >
              API 테스트 결과
            </h2>
            <p className="mt-1 break-all font-mono text-xs text-slate-400" title={result.url}>
              {result.url || "-"}
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
            <dd className="truncate font-mono text-slate-100" title={result.content_type ?? undefined}>
              {result.content_type || "-"}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">응답 크기</dt>
            <dd className="font-mono text-slate-100">{formatBytes(result.size_bytes)}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">JSON</dt>
            <dd className="font-mono text-slate-100">
              {result.is_json == null ? "-" : result.is_json ? "yes" : "no"}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] text-slate-500">행 수</dt>
            <dd className="font-mono text-slate-100">
              {result.row_count == null ? "-" : result.row_count}
            </dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[11px] text-slate-500">컬럼</dt>
            <dd className="break-words font-mono text-xs text-slate-200">{columnsText}</dd>
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

export type { InventoryOriginApiTestResult };
