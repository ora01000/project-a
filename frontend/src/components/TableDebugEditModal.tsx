import { useEffect, useMemo, useState } from "react";

export interface TableDebugSnapshot {
  name: string;
  columns: string[];
  column_types?: Record<string, string>;
  rows: Record<string, unknown>[];
  row_count: number;
  primary_key: string | null;
}

interface TableDebugEditModalProps {
  table: TableDebugSnapshot;
  row: Record<string, unknown>;
  onClose: () => void;
  onUpdated: () => Promise<void> | void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function cellToFormValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function isIntegerType(sqliteType: string | undefined): boolean {
  return (sqliteType ?? "").toUpperCase().includes("INT");
}

function isLongTextColumn(column: string, sqliteType: string | undefined, value: string): boolean {
  const typeUpper = (sqliteType ?? "").toUpperCase();
  if (typeUpper.includes("TEXT")) {
    return true;
  }
  if (/(prompt|description|message|result|plan|content)/i.test(column)) {
    return true;
  }
  return value.includes("\n") || value.length > 120;
}

export function TableDebugEditModal({ table, row, onClose, onUpdated }: TableDebugEditModalProps) {
  const primaryKey = table.primary_key ?? "idx";
  const editableColumns = useMemo(
    () => table.columns.filter((column) => column !== primaryKey),
    [table.columns, primaryKey],
  );

  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const column of editableColumns) {
      next[column] = cellToFormValue(row[column]);
    }
    setValues(next);
    setError(null);
  }, [editableColumns, row]);

  const idx = row[primaryKey];

  const updateField = (column: string, value: string) => {
    setValues((current) => ({ ...current, [column]: value }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (typeof idx !== "number" && !(typeof idx === "string" && Number.isInteger(Number(idx)))) {
      setError("기본 키(idx)가 없어 수정할 수 없습니다.");
      return;
    }

    const payloadValues: Record<string, unknown> = {};
    for (const column of editableColumns) {
      const raw = values[column] ?? "";
      const sqliteType = table.column_types?.[column] ?? "";
      if (isIntegerType(sqliteType)) {
        if (raw === "") {
          payloadValues[column] = null;
        } else if (!Number.isFinite(Number(raw))) {
          setError(`컬럼 '${column}'에 올바른 숫자를 입력해 주세요.`);
          return;
        } else {
          payloadValues[column] = Number(raw);
        }
      } else {
        payloadValues[column] = raw;
      }
    }

    setIsUpdating(true);
    setError(null);
    try {
      const response = await fetch(`/api/debug/tables/${encodeURIComponent(table.name)}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idx: typeof idx === "number" ? idx : Number(idx),
          values: payloadValues,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "레코드 수정에 실패했습니다."));
      }
      await onUpdated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "레코드 수정에 실패했습니다.");
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="table-debug-edit-title"
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="table-debug-edit-title" className="text-lg font-semibold text-slate-100">
          {table.name} 레코드 수정
        </h2>
        <p className="mt-1 font-mono text-xs text-slate-400">
          {primaryKey}={cellToFormValue(idx)}
        </p>

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

        <form onSubmit={(event) => void handleSubmit(event)} className="mt-4 flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
            <label className="block space-y-1 text-sm text-slate-300">
              <span className="font-mono">{primaryKey}</span>
              <input
                type="text"
                value={cellToFormValue(idx)}
                disabled
                className="w-full rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2 font-mono text-sm text-slate-400 outline-none"
              />
            </label>

            {editableColumns.map((column) => {
              const sqliteType = table.column_types?.[column] ?? "";
              const value = values[column] ?? "";
              const useTextarea = isLongTextColumn(column, sqliteType, value);
              const useNumber = isIntegerType(sqliteType);

              return (
                <label key={column} className="block space-y-1 text-sm text-slate-300">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="font-mono">{column}</span>
                    {sqliteType ? <span className="text-[10px] text-slate-500">{sqliteType}</span> : null}
                  </span>
                  {useTextarea ? (
                    <textarea
                      value={value}
                      onChange={(event) => updateField(column, event.target.value)}
                      rows={Math.min(12, Math.max(4, value.split("\n").length + 1))}
                      className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-600"
                    />
                  ) : (
                    <input
                      type={useNumber ? "number" : "text"}
                      value={value}
                      onChange={(event) => updateField(column, event.target.value)}
                      className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-600"
                    />
                  )}
                </label>
              );
            })}
          </div>

          <div className="mt-5 flex justify-end gap-2 border-t border-slate-800 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={isUpdating}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            >
              닫기
            </button>
            <button
              type="submit"
              disabled={isUpdating}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {isUpdating ? "업데이트 중…" : "업데이트"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
