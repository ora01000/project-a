export interface InventoryItem {
  idx: number;
  table_name: string;
  display_name: string;
  description: string;
  created_by: number;
  created_by_username: string;
  origin_csv: string;
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
  columns: string[];
  labels: string[];
  rows: Record<string, string>[];
  offset: number;
  limit: number;
  total_rows: number;
  has_more: boolean;
  columns_compatible?: boolean | null;
  compatibility_error?: string | null;
}
