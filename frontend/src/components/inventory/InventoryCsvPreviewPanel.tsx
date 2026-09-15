import { useCallback, useEffect, useRef, useState } from "react";

import type { InventoryCsvPreview } from "../../types/inventory";

interface InventoryCsvPreviewPanelProps {
  filename: string | null;
  /** Initial preview payload (e.g. right after upload). */
  initialPreview?: InventoryCsvPreview | null;
  className?: string;
}

const PAGE_SIZE = 50;

async function fetchPreview(
  filename: string,
  offset: number,
  limit: number,
): Promise<InventoryCsvPreview> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  const response = await fetch(
    `/api/inventories/csv/${encodeURIComponent(filename)}/preview?${params.toString()}`,
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(
      typeof detail?.detail === "string" ? detail.detail : "CSV 미리보기를 불러오지 못했습니다.",
    );
  }
  return (await response.json()) as InventoryCsvPreview;
}

export function InventoryCsvPreviewPanel({
  filename,
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef(false);

  const resetFromPreview = useCallback((preview: InventoryCsvPreview) => {
    setColumns(preview.columns);
    setLabels(preview.labels.length ? preview.labels : preview.columns);
    setRows(preview.rows);
    setTotalRows(preview.total_rows);
    setHasMore(preview.has_more);
    setError(null);
  }, []);

  useEffect(() => {
    if (!filename) {
      setColumns([]);
      setLabels([]);
      setRows([]);
      setTotalRows(0);
      setHasMore(false);
      setError(null);
      return;
    }
    if (initialPreview && initialPreview.filename === filename) {
      resetFromPreview(initialPreview);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void fetchPreview(filename, 0, PAGE_SIZE)
      .then((preview) => {
        if (!cancelled) {
          resetFromPreview(preview);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "CSV 미리보기 실패");
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
  }, [filename, initialPreview, resetFromPreview]);

  const loadMore = useCallback(async () => {
    if (!filename || !hasMore || loadingRef.current) {
      return;
    }
    loadingRef.current = true;
    setLoading(true);
    try {
      const preview = await fetchPreview(filename, rows.length, PAGE_SIZE);
      setRows((current) => [...current, ...preview.rows]);
      setTotalRows(preview.total_rows);
      setHasMore(preview.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : "추가 행 로드 실패");
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [filename, hasMore, rows.length]);

  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel || !filename) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadMore();
        }
      },
      { root, rootMargin: "80px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [filename, loadMore, rows.length, hasMore]);

  if (!filename) {
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
        <p className="truncate text-xs font-medium text-slate-300">CSV 미리보기</p>
        <p className="shrink-0 text-[11px] text-slate-500">
          {rows.length.toLocaleString()} / {totalRows.toLocaleString()} 행
          {loading ? " · 로딩…" : ""}
        </p>
      </div>
      {error ? (
        <p className="px-3 py-2 text-xs text-rose-300">{error}</p>
      ) : null}
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
