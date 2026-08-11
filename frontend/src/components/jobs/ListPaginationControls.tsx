import { LIST_PAGE_SIZE_OPTIONS, type ListPageSize } from "./useClientPagination";

interface ListPaginationControlsProps {
  page: number;
  pageSize: ListPageSize;
  totalPages: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: ListPageSize) => void;
  layout?: "stack" | "bar";
}

export function ListPaginationControls({
  page,
  pageSize,
  totalPages,
  totalItems,
  onPageChange,
  onPageSizeChange,
  layout = "stack",
}: ListPaginationControlsProps) {
  if (totalItems === 0) {
    return null;
  }

  const pageSizeSelect = (
    <label className="flex items-center gap-1 text-[10px] text-slate-400">
      <span>표시</span>
      <select
        value={pageSize}
        onChange={(event) => onPageSizeChange(Number(event.target.value) as ListPageSize)}
        className="rounded border border-slate-700 bg-slate-950 px-1 py-0.5 text-[10px] text-slate-200 focus:border-sky-600 focus:outline-none"
        aria-label="페이지당 표시 개수"
      >
        {LIST_PAGE_SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size}개
          </option>
        ))}
      </select>
    </label>
  );

  const pageButtons = (
    <div className="flex items-center gap-1">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="이전 페이지"
      >
        ‹
      </button>
      <span className="min-w-[2.5rem] text-center text-[10px] tabular-nums text-slate-400">
        {page}/{totalPages}
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="다음 페이지"
      >
        ›
      </button>
    </div>
  );

  const rowClassName =
    layout === "bar"
      ? "mt-2 flex shrink-0 items-center justify-between gap-3 border-t border-slate-700/80 pt-2"
      : "mt-2 flex shrink-0 items-center justify-between gap-2 border-t border-slate-700/80 pt-2";

  return (
    <div className={rowClassName}>
      {pageButtons}
      {pageSizeSelect}
    </div>
  );
}
