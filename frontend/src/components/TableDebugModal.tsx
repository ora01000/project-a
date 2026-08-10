import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { TableDebugEditModal, type TableDebugSnapshot } from "./TableDebugEditModal";

interface TableDebugModalProps {
  onClose: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function rowIdx(row: Record<string, unknown>): number | null {
  const value = row.idx;
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "" && Number.isInteger(Number(value))) {
    return Number(value);
  }
  return null;
}

export function TableDebugModal({ onClose }: TableDebugModalProps) {
  const [tables, setTables] = useState<TableDebugSnapshot[]>([]);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [selectedIdxSet, setSelectedIdxSet] = useState<Set<number>>(new Set());
  const [editingRow, setEditingRow] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDropping, setIsDropping] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showDropConfirm, setShowDropConfirm] = useState(false);
  const [dropConfirmName, setDropConfirmName] = useState("");

  const loadTables = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/debug/tables");
      if (!response.ok) {
        throw new Error(await parseError(response, "테이블을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as { tables: TableDebugSnapshot[] };
      setTables(data.tables);
      setSelectedName((current) => {
        if (current && data.tables.some((table) => table.name === current)) {
          return current;
        }
        return data.tables[0]?.name ?? null;
      });
      setSelectedIdxSet(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "테이블을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTables();
  }, [loadTables]);

  const selected = tables.find((table) => table.name === selectedName) ?? null;

  const rowIndexes = useMemo(() => {
    if (!selected) {
      return [] as number[];
    }
    return selected.rows
      .map((row) => rowIdx(row))
      .filter((value): value is number => value !== null);
  }, [selected]);

  const dropNameMatches =
    selected != null && dropConfirmName.trim() === selected.name;

  const selectTable = (name: string) => {
    setSelectedName(name);
    setSelectedIdxSet(new Set());
    setEditingRow(null);
    setError(null);
    setShowDropConfirm(false);
    setDropConfirmName("");
  };

  const toggleRow = (idx: number) => {
    setSelectedIdxSet((current) => {
      const next = new Set(current);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (rowIndexes.length === 0) {
      return;
    }
    if (selectedIdxSet.size === rowIndexes.length) {
      setSelectedIdxSet(new Set());
      return;
    }
    setSelectedIdxSet(new Set(rowIndexes));
  };

  const handleDelete = async () => {
    if (!selected || selectedIdxSet.size === 0) {
      return;
    }

    setIsDeleting(true);
    setError(null);
    try {
      const response = await fetch(`/api/debug/tables/${encodeURIComponent(selected.name)}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idx_list: [...selectedIdxSet] }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "레코드 삭제에 실패했습니다."));
      }
      setShowDeleteConfirm(false);
      await loadTables();
    } catch (err) {
      setShowDeleteConfirm(false);
      setError(err instanceof Error ? err.message : "레코드 삭제에 실패했습니다.");
    } finally {
      setIsDeleting(false);
    }
  };

  const openDropConfirm = () => {
    if (!selected) {
      return;
    }
    setDropConfirmName("");
    setShowDropConfirm(true);
    setError(null);
  };

  const handleDropTable = async () => {
    if (!selected || !dropNameMatches) {
      return;
    }

    setIsDropping(true);
    setError(null);
    const droppedName = selected.name;
    try {
      const response = await fetch(`/api/debug/tables/${encodeURIComponent(droppedName)}/drop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm_name: dropConfirmName.trim() }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "테이블 삭제에 실패했습니다."));
      }
      setShowDropConfirm(false);
      setDropConfirmName("");
      setSelectedName(null);
      await loadTables();
    } catch (err) {
      setError(err instanceof Error ? err.message : "테이블 삭제에 실패했습니다.");
    } finally {
      setIsDropping(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="table-debug-dialog-title"
        className="flex max-h-[90vh] w-full max-w-[min(100%,108rem)] flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="table-debug-dialog-title" className="text-lg font-semibold text-slate-100">
            테이블 조회 (디버깅)
          </h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={openDropConfirm}
              disabled={!selected || isDropping || isLoading || isDeleting}
              className="rounded-md border border-rose-800 bg-rose-950/30 px-3 py-1.5 text-sm font-medium text-rose-100 hover:bg-rose-950/60 disabled:cursor-not-allowed disabled:opacity-50"
            >
              테이블 삭제
            </button>
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={selectedIdxSet.size === 0 || isDeleting || isLoading || isDropping}
              className="rounded-md border border-rose-800 px-3 py-1.5 text-sm text-rose-200 hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              삭제{selectedIdxSet.size > 0 ? ` (${selectedIdxSet.size})` : ""}
            </button>
            <button
              type="button"
              onClick={() => void loadTables()}
              disabled={isLoading || isDeleting || isDropping}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            >
              새로고침
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              닫기
            </button>
          </div>
        </div>

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

        {isLoading ? (
          <p className="mt-4 text-sm text-slate-400">불러오는 중…</p>
        ) : tables.length === 0 ? (
          <p className="mt-4 text-sm text-slate-400">조회할 테이블이 없습니다.</p>
        ) : (
          <div className="mt-4 flex min-h-0 flex-1 flex-col gap-3 md:flex-row">
            <aside className="max-h-40 shrink-0 overflow-y-auto rounded-md border border-slate-700 md:max-h-none md:w-[19.5rem]">
              <ul className="py-1 text-sm">
                {tables.map((table) => (
                  <li key={table.name}>
                    <button
                      type="button"
                      title={table.name}
                      onClick={() => selectTable(table.name)}
                      className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left ${
                        selectedName === table.name
                          ? "bg-slate-800 text-sky-200"
                          : "text-slate-200 hover:bg-slate-800"
                      }`}
                    >
                      <span className="truncate font-mono" title={table.name}>
                        {table.name}
                      </span>
                      <span className="shrink-0 text-xs text-slate-400">{table.row_count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </aside>

            <div className="min-h-0 min-w-0 flex-1 overflow-auto rounded-md border border-slate-700">
              {selected ? (
                selected.rows.length === 0 ? (
                  <p className="p-4 text-sm text-slate-400">
                    <span className="font-mono text-slate-200">{selected.name}</span> — 데이터 없음
                  </p>
                ) : (
                  <table className="min-w-full border-collapse text-left text-xs text-slate-200">
                    <thead className="sticky top-0 bg-slate-800">
                      <tr>
                        <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2">
                          <input
                            type="checkbox"
                            checked={rowIndexes.length > 0 && selectedIdxSet.size === rowIndexes.length}
                            onChange={toggleAll}
                            aria-label="전체 선택"
                          />
                        </th>
                        <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300">
                          수정
                        </th>
                        {selected.columns.map((column) => (
                          <th
                            key={column}
                            className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-medium text-slate-300"
                          >
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selected.rows.map((row, rowIndex) => {
                        const idx = rowIdx(row);
                        return (
                          <tr key={idx ?? rowIndex} className="odd:bg-slate-900/40 even:bg-slate-900/80">
                            <td className="border-b border-slate-800 px-3 py-1.5">
                              {idx === null ? null : (
                                <input
                                  type="checkbox"
                                  checked={selectedIdxSet.has(idx)}
                                  onChange={() => toggleRow(idx)}
                                  aria-label={`레코드 ${idx} 선택`}
                                />
                              )}
                            </td>
                            <td className="border-b border-slate-800 px-3 py-1.5">
                              {idx === null ? null : (
                                <button
                                  type="button"
                                  onClick={() => setEditingRow(row)}
                                  className="rounded border border-sky-800 px-2 py-0.5 text-[11px] text-sky-200 hover:bg-sky-950/50"
                                >
                                  수정
                                </button>
                              )}
                            </td>
                            {selected.columns.map((column) => (
                              <td
                                key={column}
                                className="max-w-xs truncate whitespace-nowrap border-b border-slate-800 px-3 py-1.5 font-mono"
                                title={formatCell(row[column])}
                              >
                                {formatCell(row[column])}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )
              ) : null}
            </div>
          </div>
        )}
      </div>

      {showDeleteConfirm ? (
        <ConfirmDialog
          title="레코드 삭제"
          message={`${selected?.name ?? "테이블"}에서 선택한 ${selectedIdxSet.size}건을 삭제하시겠습니까?`}
          confirmLabel={isDeleting ? "삭제 중…" : "삭제"}
          cancelLabel="취소"
          onCancel={() => {
            if (!isDeleting) {
              setShowDeleteConfirm(false);
            }
          }}
          onConfirm={() => {
            if (!isDeleting) {
              void handleDelete();
            }
          }}
        />
      ) : null}

      {showDropConfirm && selected ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/70 px-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="drop-table-dialog-title"
            className="w-full max-w-md rounded-xl border border-rose-900/60 bg-slate-900 p-5 shadow-xl"
          >
            <h2 id="drop-table-dialog-title" className="text-base font-semibold text-rose-100">
              테이블 삭제
            </h2>
            <p className="mt-2 text-sm text-slate-300">
              선택한 테이블을 영구 삭제합니다. 확인을 위해 아래 테이블 이름을 정확히 입력하세요.
            </p>
            <p className="mt-3 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-sky-200">
              {selected.name}
            </p>
            <label className="mt-3 block text-xs text-slate-400">
              테이블 이름 입력
              <input
                type="text"
                value={dropConfirmName}
                autoComplete="off"
                spellCheck={false}
                disabled={isDropping}
                placeholder={selected.name}
                onChange={(event) => setDropConfirmName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && dropNameMatches && !isDropping) {
                    void handleDropTable();
                  }
                }}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 focus:border-rose-600 focus:outline-none disabled:opacity-50"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={isDropping}
                onClick={() => {
                  if (!isDropping) {
                    setShowDropConfirm(false);
                    setDropConfirmName("");
                  }
                }}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="button"
                disabled={!dropNameMatches || isDropping}
                onClick={() => void handleDropTable()}
                className="rounded-md bg-rose-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isDropping ? "삭제 중…" : "테이블 삭제"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {selected && editingRow ? (
        <TableDebugEditModal
          table={selected}
          row={editingRow}
          onClose={() => setEditingRow(null)}
          onUpdated={loadTables}
        />
      ) : null}
    </div>
  );
}
