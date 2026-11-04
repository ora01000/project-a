export interface InventoryItem {
  idx: number;
  table_name: string;
  display_name: string;
  description: string;
  created_by: number;
  created_by_username: string;
  origin_csv: string;
  created_at?: string;
  origin_type?: number;
  origin_api_url?: string;
  origin_api_url_method?: string;
  origin_api_url_params?: string;
  origin_api_url_headers?: string;
  /** 1 = bearer, 2 = header, 3 = token */
  origin_api_auth_type?: number;
  has_api_key?: boolean;
  origin_token_api?: string;
  origin_token_api_method?: string;
  has_token_api_params?: boolean;
  has_token_api_headers?: boolean;
  is_scheduled?: boolean;
  api_crawling_cron?: string;
}

export interface InventoryStatsRow {
  table_name: string;
  display_name: string;
  description: string;
  origin_csv: string;
  created_at: string;
  created_by: number;
  created_by_username: string;
  row_count: number;
  column_count: number;
  error?: string | null;
  origin_type?: number;
  origin_api_url?: string;
  origin_api_url_method?: string;
  origin_api_url_params?: string;
  origin_api_url_headers?: string;
  origin_api_auth_type?: number;
  has_api_key?: boolean;
  origin_token_api?: string;
  origin_token_api_method?: string;
  has_token_api_params?: boolean;
  has_token_api_headers?: boolean;
  is_scheduled?: boolean;
  api_crawling_cron?: string;
}

export interface InventoryApiStatsRow {
  api_name: string;
  table_name: string;
  display_name: string;
  api_fullpath: string;
  created_by: number;
  created_by_username: string;
  description: string;
  error?: string | null;
}

export interface InventoryApiItem {
  idx: number;
  api_name: string;
  display_name: string;
  description: string;
  api_fullpath: string;
  created_by: number;
  created_by_username: string;
  table_name: string;
  where_exp: string;
  select_exp: string;
  param_columns: string;
}

export interface InventoryCsvPreview {
  filename: string;
  table_name?: string;
  temp_table_name?: string;
  columns: string[];
  labels: string[];
  rows: Record<string, string>[];
  offset: number;
  limit: number;
  startrow?: number;
  endrow?: number;
  total_rows: number;
  has_more: boolean;
  columns_compatible?: boolean | null;
  compatibility_error?: string | null;
  transfer_ok?: boolean | null;
  transfer_result?: Record<string, unknown> | null;
  response_json?: unknown;
}

/** 1 = bearer, 2 = custom header (key:value), 3 = token API */
export type InventoryApiAuthType = 1 | 2 | 3;

export interface InventoryTablePreview {
  table_name: string;
  columns: string[];
  labels: string[];
  rows: Record<string, string>[];
  startrow: number;
  endrow: number;
  total_rows: number;
  has_more: boolean;
}

/** 1 = CSV upload, 2 = API crawl */
export type InventoryOriginMode = "csv" | "api";

export type InventoryHttpMethod = "GET" | "POST";

export interface InventoryKeyValueParam {
  key: string;
  value: string;
}

export function parseInventoryParams(raw: string | null | undefined): InventoryKeyValueParam[] {
  const text = (raw || "").trim();
  if (!text) {
    return [];
  }
  return text
    .split("&")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const idx = part.indexOf("=");
      if (idx < 0) {
        return { key: part, value: "" };
      }
      return {
        key: part.slice(0, idx),
        value: part.slice(idx + 1),
      };
    });
}

export function serializeInventoryParams(items: InventoryKeyValueParam[]): string {
  return items
    .map((item) => ({
      key: item.key.trim(),
      value: item.value.trim(),
    }))
    .filter((item) => item.key)
    .map((item) => `${item.key}=${item.value}`)
    .join("&");
}
