import { useEffect, useMemo, useState } from "react";

import type { InventoryApiItem } from "../../types/inventory";

interface InventoryApiTestModalProps {
  api: InventoryApiItem;
  onClose: () => void;
}

interface TestResultPayload {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
}

async function readErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") {
      return payload.detail;
    }
  } catch {
    // ignore
  }
  return fallback;
}

function parseParamList(raw: string): string[] {
  return (raw || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function normalizeTestPayload(payload: unknown): TestResultPayload {
  if (Array.isArray(payload)) {
    return {
      columns: [],
      rows: payload as Record<string, unknown>[],
      row_count: payload.length,
    };
  }
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (Array.isArray(record.rows)) {
      const columns = Array.isArray(record.columns)
        ? (record.columns as string[])
        : [];
      const rows = record.rows as Record<string, unknown>[];
      return {
        columns,
        rows,
        row_count: Number(record.row_count ?? rows.length) || rows.length,
      };
    }
    return { columns: [], rows: [record], row_count: 1 };
  }
  return { columns: [], rows: [], row_count: 0 };
}

export function InventoryApiTestModal({ api, onClose }: InventoryApiTestModalProps) {
  const paramNames = useMemo(() => parseParamList(api.param_columns), [api.param_columns]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResultPayload | null>(null);

  useEffect(() => {
    const initial: Record<string, string> = {};
    for (const name of paramNames) {
      initial[name] = "";
    }
    setValues(initial);
    setError(null);
    setResult(null);
  }, [api.api_name, api.table_name, paramNames]);

  const handleRun = async () => {
    const missing = paramNames.filter((name) => !(values[name] || "").trim());
    if (missing.length > 0) {
      setError(`필수 입력값이 비어 있습니다: ${missing.join(", ")}`);
      return;
    }

    const params = new URLSearchParams();
    for (const name of paramNames) {
      params.set(name, (values[name] || "").trim());
    }

    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(
        `/api/inventories/${encodeURIComponent(api.table_name)}/apis/${encodeURIComponent(api.api_name)}/test?${params.toString()}`,
      );
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "API 테스트에 실패했습니다."));
      }
      const payload = await response.json();
      setResult(normalizeTestPayload(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : "API 테스트 실패");
    } finally {
      setRunning(false);
    }
  };

  const displayColumns =
    result && result.columns.length > 0
      ? result.columns
      : result && result.rows[0]
        ? Object.keys(result.rows[0])
        : [];

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="inventory-api-test-title"
        className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-xl"
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-700 px-5 py-4">
          <div className="min-w-0">
            <h2
              id="inventory-api-test-title"
              className="truncate text-base font-semibold text-slate-100"
            >
              API 테스트 · {api.display_name}
            </h2>
            <p className="mt-1 truncate font-mono text-xs text-slate-400" title={api.api_fullpath}>
              GET {api.api_fullpath}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <section className="flex flex-col gap-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">입력</h3>
            {paramNames.length === 0 ? (
              <p className="text-sm text-slate-500">정의된 매개변수가 없습니다.</p>
            ) : (
              paramNames.map((name) => (
                <label key={name} className="flex flex-col gap-1">
                  <span className="font-mono text-xs font-medium text-slate-300">{name}</span>
                  <input
                    type="text"
                    value={values[name] ?? ""}
                    onChange={(event) =>
                      setValues((current) => ({ ...current, [name]: event.target.value }))
                    }
                    className="rounded-md border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-600"
                    placeholder={`${name} 값`}
                  />
                </label>
              ))
            )}
            <div className="flex justify-end">
              <button
                type="button"
                disabled={running || paramNames.length === 0}
                onClick={() => void handleRun()}
                className="rounded-md border border-sky-700 bg-sky-950/50 px-4 py-2 text-sm font-medium text-sky-100 hover:bg-sky-900/60 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running ? "실행 중…" : "실행"}
              </button>
            </div>
          </section>

          {error ? (
            <p className="mt-4 text-sm text-rose-300" role="alert">
              {error}
            </p>
          ) : null}

          {result != null ? (
            <section className="mt-5 flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  출력
                </h3>
                <span className="text-[11px] text-slate-500">
                  {result.row_count.toLocaleString()}건
                </span>
              </div>
              {result.rows.length === 0 ? (
                <p className="rounded-md border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-slate-400">
                  결과가 없습니다.
                </p>
              ) : (
                <div className="max-h-[40vh] overflow-auto rounded-md border border-slate-700 bg-slate-950/80">
                  <table className="min-w-full border-collapse text-left text-xs">
                    <thead className="sticky top-0 bg-slate-900">
                      <tr>
                        {displayColumns.map((col) => (
                          <th
                            key={col}
                            className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, rowIndex) => (
                        <tr key={rowIndex} className="odd:bg-slate-900/40">
                          {displayColumns.map((col) => (
                            <td
                              key={`${rowIndex}-${col}`}
                              className="max-w-[240px] truncate whitespace-nowrap border-b border-slate-800/80 px-3 py-1.5 text-slate-300"
                              title={String(row[col] ?? "")}
                            >
                              {row[col] == null ? "" : String(row[col])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
