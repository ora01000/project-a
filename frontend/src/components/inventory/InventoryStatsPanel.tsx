import { useCallback, useEffect, useState } from "react";

import type { InventoryApiStatsRow, InventoryStatsRow } from "../../types/inventory";
import { WorkflowIcon } from "../workflow/WorkflowIcon";

interface InventoryStatsPanelProps {
  className?: string;
  /** Bump to force reload (e.g. after create/delete). */
  refreshKey?: number;
  onSelectRow?: (row: InventoryStatsRow) => void;
  onSelectApiRow?: (row: InventoryApiStatsRow) => void;
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

function formatCount(value: number): string {
  return value.toLocaleString();
}

export function InventoryStatsPanel({
  className = "",
  refreshKey = 0,
  onSelectRow,
  onSelectApiRow,
}: InventoryStatsPanelProps) {
  const [rows, setRows] = useState<InventoryStatsRow[]>([]);
  const [apiRows, setApiRows] = useState<InventoryApiStatsRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [inventoryResponse, apiResponse] = await Promise.all([
        fetch("/api/inventories/stats"),
        fetch("/api/inventories/api-stats"),
      ]);
      if (!inventoryResponse.ok) {
        throw new Error(
          await readErrorDetail(inventoryResponse, "인벤토리 통계를 불러오지 못했습니다."),
        );
      }
      if (!apiResponse.ok) {
        throw new Error(await readErrorDetail(apiResponse, "사용자 정의 API 목록을 불러오지 못했습니다."));
      }
      setRows((await inventoryResponse.json()) as InventoryStatsRow[]);
      setApiRows((await apiResponse.json()) as InventoryApiStatsRow[]);
    } catch (err) {
      setRows([]);
      setApiRows([]);
      setError(err instanceof Error ? err.message : "통계 로드 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats, refreshKey]);

  return (
    <div className={`flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 ${className}`.trim()}>
      <header className="flex shrink-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="inline-flex items-center gap-1.5 text-base font-semibold text-slate-100">
            <WorkflowIcon name="inventory" size="sm" />
            인벤토리 대시보드
          </h1>
          <p className="mt-0.5 text-xs text-slate-500">
            등록된 인벤토리 통계와 사용자 정의 API 목록을 요약합니다. 행을 클릭하면 해당 인벤토리 구성으로 이동합니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadStats()}
          disabled={loading}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-600 bg-slate-800/70 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 disabled:opacity-50"
        >
          <WorkflowIcon name="refresh" size="xs" label="새로고침" />
          {loading ? "로딩…" : "새로고침"}
        </button>
      </header>

      {error ? (
        <p className="shrink-0 rounded-md border border-rose-800/60 bg-rose-950/40 px-3 py-2 text-xs text-rose-200">
          {error}
        </p>
      ) : null}

      <section className="flex min-h-[220px] shrink-0 flex-col">
        <h2 className="mb-2 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-200">
          <WorkflowIcon name="list" size="xs" />
          인벤토리 통계
        </h2>
        <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-slate-700 bg-slate-950/60">
          {loading && rows.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">통계를 불러오는 중…</p>
          ) : rows.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">
              등록된 인벤토리가 없습니다. 왼쪽에서 「새로운 인벤토리」를 시작하세요.
            </p>
          ) : (
            <table className="min-w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 bg-slate-900">
                <tr>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    이름
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    원본CSV
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    등록일자
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    등록자
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 text-right font-semibold text-slate-200">
                    레코드 개수
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 text-right font-semibold text-slate-200">
                    컬럼 개수
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    설명
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const selectable = Boolean(row.table_name) && !row.error;
                  return (
                    <tr
                      key={row.table_name || row.display_name}
                      className={`odd:bg-slate-900/40 even:bg-slate-950/20 ${
                        selectable ? "cursor-pointer hover:bg-sky-950/40" : "opacity-80"
                      }`}
                      onClick={() => {
                        if (selectable && onSelectRow) {
                          onSelectRow(row);
                        }
                      }}
                      title={row.error || row.description || row.table_name}
                    >
                      <td className="max-w-[200px] truncate border-b border-slate-800/80 px-3 py-2 font-medium text-slate-100">
                        {row.display_name || row.table_name || "-"}
                        {row.error ? (
                          <span className="ml-1 text-[10px] font-normal text-rose-300">
                            (조회 실패)
                          </span>
                        ) : null}
                      </td>
                      <td
                        className="max-w-[180px] truncate border-b border-slate-800/80 px-3 py-2 font-mono text-slate-300"
                        title={row.origin_csv}
                      >
                        {row.origin_csv || "-"}
                      </td>
                      <td className="whitespace-nowrap border-b border-slate-800/80 px-3 py-2 text-slate-300">
                        {row.created_at || "-"}
                      </td>
                      <td className="whitespace-nowrap border-b border-slate-800/80 px-3 py-2 text-slate-300">
                        {row.created_by_username ||
                          (row.created_by ? `#${row.created_by}` : "-")}
                      </td>
                      <td className="whitespace-nowrap border-b border-slate-800/80 px-3 py-2 text-right tabular-nums text-slate-200">
                        {row.error ? "-" : formatCount(row.row_count)}
                      </td>
                      <td className="whitespace-nowrap border-b border-slate-800/80 px-3 py-2 text-right tabular-nums text-slate-200">
                        {row.error ? "-" : formatCount(row.column_count)}
                      </td>
                      <td
                        className="max-w-[280px] truncate border-b border-slate-800/80 px-3 py-2 text-slate-300"
                        title={row.description}
                      >
                        {row.description || "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="flex min-h-[220px] shrink-0 flex-col pb-2">
        <h2 className="mb-2 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-200">
          <WorkflowIcon name="api" size="xs" />
          사용자 정의 API 목록
        </h2>
        <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-slate-700 bg-slate-950/60">
          {loading && apiRows.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">사용자 정의 API 목록을 불러오는 중…</p>
          ) : apiRows.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">
              등록된 사용자 정의 API가 없습니다.
            </p>
          ) : (
            <table className="min-w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 bg-slate-900">
                <tr>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    이름
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    인벤토리 테이블
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    호출명
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    표시명
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    API전체 경로
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    등록자
                  </th>
                  <th className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200">
                    설명
                  </th>
                </tr>
              </thead>
              <tbody>
                {apiRows.map((row, index) => {
                  const selectable = Boolean(row.table_name) && !row.error;
                  const key = `${row.table_name}:${row.api_name || index}`;
                  return (
                    <tr
                      key={key}
                      className={`odd:bg-slate-900/40 even:bg-slate-950/20 ${
                        selectable ? "cursor-pointer hover:bg-sky-950/40" : "opacity-80"
                      }`}
                      onClick={() => {
                        if (selectable && onSelectApiRow) {
                          onSelectApiRow(row);
                        }
                      }}
                      title={row.error || row.api_fullpath || row.description}
                    >
                      <td className="max-w-[140px] truncate border-b border-slate-800/80 px-3 py-2 font-mono text-slate-100">
                        {row.api_name || "-"}
                        {row.error ? (
                          <span className="ml-1 text-[10px] font-normal text-rose-300">
                            (조회 실패)
                          </span>
                        ) : null}
                      </td>
                      <td
                        className="max-w-[160px] truncate border-b border-slate-800/80 px-3 py-2 font-mono text-slate-300"
                        title={row.table_name}
                      >
                        {row.table_name || "-"}
                      </td>
                      <td className="max-w-[140px] truncate border-b border-slate-800/80 px-3 py-2 font-mono text-slate-300">
                        {row.api_name || "-"}
                      </td>
                      <td className="max-w-[160px] truncate border-b border-slate-800/80 px-3 py-2 text-slate-200">
                        {row.display_name || "-"}
                      </td>
                      <td
                        className="max-w-[240px] truncate border-b border-slate-800/80 px-3 py-2 font-mono text-sky-300/90"
                        title={row.api_fullpath}
                      >
                        {row.api_fullpath || "-"}
                      </td>
                      <td className="whitespace-nowrap border-b border-slate-800/80 px-3 py-2 text-slate-300">
                        {row.created_by_username ||
                          (row.created_by ? `#${row.created_by}` : "-")}
                      </td>
                      <td
                        className="max-w-[240px] truncate border-b border-slate-800/80 px-3 py-2 text-slate-300"
                        title={row.description}
                      >
                        {row.description || "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
