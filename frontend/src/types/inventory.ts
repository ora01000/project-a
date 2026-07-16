export const CHUNK_TYPE_ROW = 1;
export const CHUNK_TYPE_CUSTOM = 2;

export const MAX_INVENTORY_UPLOAD_BYTES = 100 * 1024 * 1024;
export const MAX_INVENTORY_UPLOAD_LABEL = "100MB";
export const DEFAULT_CHUNK_OVERLAP = 50;
export const DEFAULT_N_RESULTS = 100;

export const DB_TYPE_TABLE = "table";
export const DB_TYPE_VECTOR = "vector";

export const MODIFIED_EMBEDDED = 0;
export const MODIFIED_NEEDS_EMBED = 1;

export interface InventoryRecord {
  idx: number;
  inventory_name: string;
  inventory_file: string;
  file_ext: string;
  chunk_type: number;
  chunk_size: number;
  chunk_overlap: number;
  n_results: number;
  db_type: string;
  modified: number;
}

export interface InventoryFormValues {
  inventory_name: string;
  inventory_file: string;
  db_type: string;
  chunk_type: number;
  chunk_size: number;
  chunk_overlap: number;
  n_results: number;
}

export interface InventoryStatus {
  agent_id: string;
  status: string;
  error: string | null;
  document_count: number;
  chroma_data_path: string;
  csv_path: string;
  upload_path: string;
}

export interface InventoryEmbedResult {
  status: string;
  embedded_rows: number;
  document_count: number;
  modified: number;
}

export const EMPTY_INVENTORY_FORM: InventoryFormValues = {
  inventory_name: "",
  inventory_file: "",
  db_type: DB_TYPE_VECTOR,
  chunk_type: CHUNK_TYPE_ROW,
  chunk_size: 0,
  chunk_overlap: DEFAULT_CHUNK_OVERLAP,
  n_results: DEFAULT_N_RESULTS,
};

export function chunkTypeLabel(chunkType: number): string {
  return chunkType === CHUNK_TYPE_CUSTOM ? "custom size" : "row";
}

export function dbTypeLabel(dbType: string | null | undefined): string {
  return (dbType || DB_TYPE_VECTOR) === DB_TYPE_TABLE ? "table" : "vector";
}

export function modifiedLabel(modified: number): string {
  return modified === MODIFIED_NEEDS_EMBED ? "임베딩 필요" : "임베딩 완료";
}
