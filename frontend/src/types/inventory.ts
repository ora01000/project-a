export const CHUNK_TYPE_ROW = 1;
export const CHUNK_TYPE_CUSTOM = 2;

export const MODIFIED_EMBEDDED = 0;
export const MODIFIED_NEEDS_EMBED = 1;

export interface InventoryRecord {
  idx: number;
  inventory_name: string;
  inventory_file: string;
  file_ext: string;
  chunk_type: number;
  chunk_size: number;
  modified: number;
}

export interface InventoryFormValues {
  inventory_name: string;
  inventory_file: string;
  chunk_type: number;
  chunk_size: number;
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
  chunk_type: CHUNK_TYPE_ROW,
  chunk_size: 0,
};

export function chunkTypeLabel(chunkType: number): string {
  return chunkType === CHUNK_TYPE_CUSTOM ? "custom size" : "row";
}

export function modifiedLabel(modified: number): string {
  return modified === MODIFIED_NEEDS_EMBED ? "임베딩 필요" : "임베딩 완료";
}
