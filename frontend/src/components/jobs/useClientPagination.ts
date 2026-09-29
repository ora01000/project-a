import { useEffect, useMemo, useState } from "react";

export const LIST_PAGE_SIZE_OPTIONS = [10, 20, 30, 50] as const;
export type ListPageSize = (typeof LIST_PAGE_SIZE_OPTIONS)[number];
export const DEFAULT_LIST_PAGE_SIZE: ListPageSize = 10;

export function useClientPagination<T>(items: T[], defaultPageSize: ListPageSize = DEFAULT_LIST_PAGE_SIZE) {
  const [pageSize, setPageSizeState] = useState<ListPageSize>(defaultPageSize);
  const [page, setPage] = useState(1);

  const totalItems = items.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize) || 1);

  useEffect(() => {
    setPage((current) => Math.min(Math.max(1, current), totalPages));
  }, [totalPages]);

  const setPageSize = (nextSize: ListPageSize) => {
    setPageSizeState(nextSize);
    setPage(1);
  };

  const pageItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize]);

  return {
    page,
    pageSize,
    totalPages,
    totalItems,
    pageItems,
    setPage,
    setPageSize,
  };
}
