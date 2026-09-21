export interface InventoryItem {
  idx: number;
  table_name: string;
  display_name: string;
  description: string;
  created_by: number;
  created_by_username: string;
  origin_csv: string;
  created_at?: string;
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
}

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
