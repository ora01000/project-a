import { useCallback, useEffect, useRef, useState } from "react";

import type { InventoryCsvPreview, InventoryTablePreview } from "../../types/inventory";
import { WorkflowIcon } from "../workflow/WorkflowIcon";

interface InventoryCsvPreviewPanelProps {
  /** Remote inventory table name (after upload/transfer). */
  tableName: string | null;
  /** Optional CSV filename for header display. */
  filename?: string | null;
  /** Initial preview payload (e.g. right after upload). */
  initialPreview?: InventoryCsvPreview | null;
  className?: string;
}

const ROW_HEIGHT_PX = 30;
const HEADER_HEIGHT_PX = 36;
const MIN_PAGE_SIZE = 20;
const MAX_PAGE_SIZE = 200;
const DEFAULT_PAGE_SIZE = 50;

async function fetchTablePreview(
  tableName: string,
  startrow: number,
  endrow: number,
): Promise<InventoryTablePreview> {
  const params = new URLSearchParams({
    startrow: String(startrow),
    endrow: String(endrow),
  });
  const response = await fetch(
    `/api/inventories/tables/${encodeURIComponent(tableName)}/preview?${params.toString()}`,
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(
      typeof detail?.detail === "string"
        ? detail.detail
        : "테이블 미리보기를 불러오지 못했습니다.",
    );
  }
  return (await response.json()) as InventoryTablePreview;
}

function pageSizeForHeight(height: number): number {
  if (!Number.isFinite(height) || height <= 0) {
    return DEFAULT_PAGE_SIZE;
  }
  const visible = Math.ceil((height - HEADER_HEIGHT_PX) / ROW_HEIGHT_PX) + 8;
  return Math.min(MAX_PAGE_SIZE, Math.max(MIN_PAGE_SIZE, visible));
}

export function InventoryCsvPreviewPanel({
  tableName,
  filename = null,
  initialPreview = null,
  className = "",
}: InventoryCsvPreviewPanelProps) {
  const [columns, setColumns] = useState<string[]>([]);
  const [labels, setLabels] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef(false);
  const pageSizeRef = useRef(DEFAULT_PAGE_SIZE);

  const resetFromPreview = useCallback(
    (preview: InventoryTablePreview | InventoryCsvPreview) => {
      setColumns(preview.columns);
      setLabels(preview.labels.length ? preview.labels : preview.columns);
      setRows(preview.rows);
      setTotalRows(preview.total_rows);
      setHasMore(preview.has_more);
      setError(null);
    },
    [],
  );

  useEffect(() => {
    pageSizeRef.current = pageSize;
  }, [pageSize]);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      const next = pageSizeForHeight(entry.contentRect.height);
      setPageSize((current) => (current === next ? current : next));
    });
    observer.observe(root);
    setPageSize(pageSizeForHeight(root.clientHeight));
    return () => observer.disconnect();
  }, [tableName]);

  useEffect(() => {
    if (!tableName) {
      setColumns([]);
      setLabels([]);
      setRows([]);
      setTotalRows(0);
      setHasMore(false);
      setError(null);
      return;
    }
    if (
      initialPreview &&
      (initialPreview.temp_table_name === tableName ||
        initialPreview.table_name === tableName ||
        (!initialPreview.table_name &&
          !initialPreview.temp_table_name &&
          initialPreview.rows.length > 0))
    ) {
      resetFromPreview(initialPreview);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const size = pageSizeRef.current;
    void fetchTablePreview(tableName, 1, size)
      .then((preview) => {
        if (!cancelled) {
          resetFromPreview(preview);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "테이블 미리보기 실패");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tableName, initialPreview, resetFromPreview]);

  const loadMore = useCallback(async () => {
    if (!tableName || !hasMore || loadingRef.current) {
      return;
    }
    loadingRef.current = true;
    setLoading(true);
    try {
      const startrow = rows.length + 1;
      const endrow = rows.length + pageSizeRef.current;
      const preview = await fetchTablePreview(tableName, startrow, endrow);
      setRows((current) => [...current, ...preview.rows]);
      setTotalRows(preview.total_rows);
      setHasMore(preview.has_more);
      if (preview.columns.length && columns.length === 0) {
        setColumns(preview.columns);
        setLabels(preview.labels.length ? preview.labels : preview.columns);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "추가 행 로드 실패");
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [tableName, hasMore, rows.length, columns.length]);

  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel || !tableName) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadMore();
        }
      },
      { root, rootMargin: "120px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [tableName, loadMore, rows.length, hasMore]);

  if (!tableName) {
    return (
      <div
        className={`flex min-h-0 flex-col rounded-lg border border-dashed border-slate-700 bg-slate-950/40 ${className}`.trim()}
      >
        <p className="m-auto px-4 text-center text-sm text-slate-500">
          CSV를 업로드하면 여기에 미리보기가 표시됩니다.
        </p>
      </div>
    );
  }

  return (
    <div
      className={`flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-950/60 ${className}`.trim()}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <div className="min-w-0">
          <p className="inline-flex items-center gap-1.5 truncate text-xs font-medium text-slate-300">
            <WorkflowIcon name="list" size="xs" />
            테이블 미리보기
          </p>
          <p className="truncate text-[11px] text-slate-500" title={tableName}>
            {tableName}
            {filename ? ` · ${filename}` : ""}
          </p>
        </div>
        <p className="shrink-0 text-[11px] text-slate-500">
          {rows.length.toLocaleString()} / {totalRows.toLocaleString()} 행
          {loading ? " · 로딩…" : ""}
        </p>
      </div>
      {error ? <p className="px-3 py-2 text-xs text-rose-300">{error}</p> : null}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 z-10 bg-slate-900">
            <tr>
              {columns.map((col, index) => (
                <th
                  key={col}
                  className="whitespace-nowrap border-b border-slate-700 px-3 py-2 font-semibold text-slate-200"
                  title={col}
                >
                  {labels[index] || col}
                  {labels[index] && labels[index] !== col ? (
                    <span className="ml-1 font-normal text-slate-500">({col})</span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="odd:bg-slate-900/40 even:bg-slate-950/20">
                {columns.map((col) => (
                  <td
                    key={`${rowIndex}-${col}`}
                    className="max-w-[240px] truncate whitespace-nowrap border-b border-slate-800/80 px-3 py-1.5 text-slate-300"
                    title={row[col] ?? ""}
                  >
                    {row[col] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div ref={sentinelRef} className="h-4 w-full" aria-hidden />
      </div>
    </div>
  );
}
