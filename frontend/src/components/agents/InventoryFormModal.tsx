import { useEffect, useRef, useState } from "react";

import type { InventoryFormValues, InventoryRecord } from "../../types/inventory";
import {
  CHUNK_TYPE_CUSTOM,
  CHUNK_TYPE_ROW,
  DB_TYPE_TABLE,
  DB_TYPE_VECTOR,
  DEFAULT_CHUNK_OVERLAP,
  DEFAULT_N_RESULTS,
  EMPTY_INVENTORY_FORM,
  MAX_INVENTORY_UPLOAD_BYTES,
  MAX_INVENTORY_UPLOAD_LABEL,
  MODIFIED_NEEDS_EMBED,
} from "../../types/inventory";

interface InventoryFormModalProps {
  mode: "create" | "edit";
  record?: InventoryRecord;
  onClose: () => void;
  onUpload: (values: InventoryFormValues, file: File | null) => Promise<InventoryRecord>;
  onEmbed: (recordIdx: number) => Promise<void>;
}

export function InventoryFormModal({
  mode,
  record,
  onClose,
  onUpload,
  onEmbed,
}: InventoryFormModalProps) {
  const [values, setValues] = useState<InventoryFormValues>(EMPTY_INVENTORY_FORM);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [savedRecord, setSavedRecord] = useState<InventoryRecord | null>(record ?? null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isEmbedding, setIsEmbedding] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isTableMode = values.db_type === DB_TYPE_TABLE;

  useEffect(() => {
    if (mode === "edit" && record) {
      setValues({
        inventory_name: record.inventory_name,
        inventory_file: record.inventory_file,
        db_type: record.db_type || DB_TYPE_VECTOR,
        chunk_type: record.chunk_type,
        chunk_size: record.chunk_size,
        chunk_overlap: record.chunk_overlap ?? DEFAULT_CHUNK_OVERLAP,
        n_results: record.n_results ?? DEFAULT_N_RESULTS,
      });
      setSavedRecord(record);
      setSelectedFile(null);
      return;
    }

    setValues(EMPTY_INVENTORY_FORM);
    setSavedRecord(null);
    setSelectedFile(null);
  }, [mode, record]);

  const updateField = <K extends keyof InventoryFormValues>(key: K, value: InventoryFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      setSelectedFile(null);
      return;
    }

    if (file.size > MAX_INVENTORY_UPLOAD_BYTES) {
      const message = `업로드 가능한 최대 파일 크기(${MAX_INVENTORY_UPLOAD_LABEL})를 초과했습니다. ${MAX_INVENTORY_UPLOAD_LABEL} 이하 파일을 선택해 주세요.`;
      window.alert(message);
      setSelectedFile(file);
      setError(message);
      setValues((current) => ({
        ...current,
        inventory_file: file.name,
      }));
      return;
    }

    setSelectedFile(file);
    setError(null);
    setValues((current) => ({
      ...current,
      inventory_file: file?.name ?? current.inventory_file,
    }));
  };

  const isFileOversized = selectedFile !== null && selectedFile.size > MAX_INVENTORY_UPLOAD_BYTES;
  const fileSizeError = isFileOversized
    ? `업로드 가능한 최대 파일 크기(${MAX_INVENTORY_UPLOAD_LABEL})를 초과했습니다.`
    : null;

  const validateForm = (): string | null => {
    if (!values.inventory_name.trim()) {
      return "인벤토리 이름을 입력해 주세요.";
    }
    if (mode === "create" && !selectedFile) {
      return "업로드할 파일을 선택해 주세요.";
    }
    if (fileSizeError) {
      return fileSizeError;
    }
    if (isTableMode) {
      const fileName = selectedFile?.name || values.inventory_file;
      if (fileName && !fileName.toLowerCase().endsWith(".csv")) {
        return "table 방식은 CSV 파일만 업로드할 수 있습니다.";
      }
      return null;
    }
    if (values.chunk_type === CHUNK_TYPE_CUSTOM && values.chunk_size <= 0) {
      return "custom size를 선택한 경우 chunk size를 입력해 주세요.";
    }
    if (values.chunk_type === CHUNK_TYPE_CUSTOM && values.chunk_overlap < 0) {
      return "chunk overlap은 0 이상이어야 합니다.";
    }
    if (values.chunk_type === CHUNK_TYPE_CUSTOM && values.chunk_overlap >= values.chunk_size) {
      return "chunk overlap은 chunk size보다 작아야 합니다.";
    }
    if (values.n_results <= 0) {
      return "n_results는 1 이상이어야 합니다.";
    }
    return null;
  };

  const handleUpload = async () => {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsUploading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const uploadedRecord = await onUpload(values, selectedFile);
      setSavedRecord(uploadedRecord);
      setValues({
        inventory_name: uploadedRecord.inventory_name,
        inventory_file: uploadedRecord.inventory_file,
        db_type: uploadedRecord.db_type || DB_TYPE_VECTOR,
        chunk_type: uploadedRecord.chunk_type,
        chunk_size: uploadedRecord.chunk_size,
        chunk_overlap: uploadedRecord.chunk_overlap ?? DEFAULT_CHUNK_OVERLAP,
        n_results: uploadedRecord.n_results ?? DEFAULT_N_RESULTS,
      });
      if ((uploadedRecord.db_type || DB_TYPE_VECTOR) === DB_TYPE_TABLE) {
        setSuccessMessage("업로드가 완료되었습니다. CSV 데이터가 SQLite 테이블로 적재되었습니다.");
      } else {
        setSuccessMessage("업로드가 완료되었습니다. Embedding 버튼을 눌러 ChromaDB에 적재하세요.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "업로드에 실패했습니다.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleEmbed = async () => {
    if (!savedRecord) {
      setError("먼저 업로드를 완료해 주세요.");
      return;
    }

    setIsEmbedding(true);
    setError(null);
    try {
      await onEmbed(savedRecord.idx);
      setSuccessMessage("Embedding이 성공적으로 완료되었습니다.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Embedding에 실패했습니다.");
    } finally {
      setIsEmbedding(false);
    }
  };

  const canEmbed =
    !isTableMode &&
    (savedRecord?.db_type || DB_TYPE_VECTOR) !== DB_TYPE_TABLE &&
    savedRecord?.modified === MODIFIED_NEEDS_EMBED;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-slate-100">
          {mode === "create" ? "인벤토리 추가" : "인벤토리 수정"}
        </h2>
        {mode === "create" ? (
          <p className="mt-1 text-xs text-slate-500">
            인벤토리 파일은 최대 <span className="text-slate-300">{MAX_INVENTORY_UPLOAD_LABEL}</span>까지 업로드할 수
            있습니다.
          </p>
        ) : null}

        <div className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>db_type</span>
            <select
              value={values.db_type}
              onChange={(event) => updateField("db_type", event.target.value)}
              disabled={isUploading || isEmbedding || mode === "edit"}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            >
              <option value={DB_TYPE_VECTOR}>vector</option>
              <option value={DB_TYPE_TABLE}>table</option>
            </select>
            <p className="text-xs text-slate-500">
              vector: ChromaDB 임베딩 / table: SQLite 테이블 적재 (CSV)
            </p>
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>인벤토리 이름</span>
            <input
              value={values.inventory_name}
              onChange={(event) => updateField("inventory_name", event.target.value)}
              disabled={isUploading || isEmbedding}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>인벤토리 파일</span>
            <div className="flex gap-2">
              <input
                value={values.inventory_file}
                readOnly
                placeholder="파일을 선택하세요"
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || isEmbedding}
                className="shrink-0 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
              >
                찾기
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept={isTableMode ? ".csv" : ".csv,.txt,.json"}
              onChange={handleFileChange}
              className="hidden"
            />
            <p className="text-xs text-slate-500">
              최대 업로드 크기: <span className="text-slate-300">{MAX_INVENTORY_UPLOAD_LABEL}</span>
              {isTableMode ? " · table 방식은 CSV만 지원" : null}
            </p>
          </label>

          {values.inventory_file ? (
            <p className="text-xs text-slate-500">
              저장 확장자: <span className="text-slate-300">{values.inventory_file.split(".").pop() ?? "-"}</span>
            </p>
          ) : null}

          {!isTableMode ? (
            <>
              <label className="block space-y-1 text-sm text-slate-300">
                <span>chunk type</span>
                <select
                  value={values.chunk_type}
                  onChange={(event) => updateField("chunk_type", Number(event.target.value))}
                  disabled={isUploading || isEmbedding}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                >
                  <option value={CHUNK_TYPE_ROW}>1 : row</option>
                  <option value={CHUNK_TYPE_CUSTOM}>2 : custom size</option>
                </select>
              </label>

              <label className="block space-y-1 text-sm text-slate-300">
                <span>n_results</span>
                <input
                  type="number"
                  min={1}
                  value={values.n_results}
                  onChange={(event) => updateField("n_results", Number(event.target.value) || 0)}
                  disabled={isUploading || isEmbedding}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
                <p className="text-xs text-slate-500">
                  ChromaDB 조회 시 반환할 최대 문서 수. 기본값 {DEFAULT_N_RESULTS}.
                </p>
              </label>

              {values.chunk_type === CHUNK_TYPE_CUSTOM ? (
                <>
                  <label className="block space-y-1 text-sm text-slate-300">
                    <span>chunk size (문자)</span>
                    <input
                      type="number"
                      min={1}
                      value={values.chunk_size || ""}
                      onChange={(event) => updateField("chunk_size", Number(event.target.value) || 0)}
                      disabled={isUploading || isEmbedding}
                      className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                    />
                  </label>
                  <label className="block space-y-1 text-sm text-slate-300">
                    <span>chunk overlap (문자)</span>
                    <input
                      type="number"
                      min={0}
                      value={values.chunk_overlap}
                      onChange={(event) =>
                        updateField("chunk_overlap", Number(event.target.value) || 0)
                      }
                      disabled={isUploading || isEmbedding}
                      className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                    />
                    <p className="text-xs text-slate-500">
                      기본값 {DEFAULT_CHUNK_OVERLAP}. chunk size보다 작아야 합니다.
                    </p>
                  </label>
                </>
              ) : null}
            </>
          ) : null}

          {error ? (
            <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
              {error}
            </div>
          ) : null}

          {successMessage ? (
            <div className="rounded-md border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-200">
              {successMessage}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isUploading || isEmbedding}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              닫기
            </button>
            <button
              type="button"
              onClick={() => void handleUpload()}
              disabled={Boolean(validateForm()) || isUploading || isEmbedding}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:bg-slate-700"
            >
              {isUploading ? "업로드 중..." : "업로드"}
            </button>
            <button
              type="button"
              onClick={() => void handleEmbed()}
              disabled={!canEmbed || isUploading || isEmbedding}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:bg-slate-700"
            >
              {isEmbedding ? "Embedding 중..." : "Embedding"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
