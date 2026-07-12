import { useEffect, useRef, useState } from "react";

import type { InventoryFormValues, InventoryRecord } from "../../types/inventory";
import {
  CHUNK_TYPE_CUSTOM,
  CHUNK_TYPE_ROW,
  EMPTY_INVENTORY_FORM,
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

  useEffect(() => {
    if (mode === "edit" && record) {
      setValues({
        inventory_name: record.inventory_name,
        inventory_file: record.inventory_file,
        chunk_type: record.chunk_type,
        chunk_size: record.chunk_size,
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
    setSelectedFile(file);
    setValues((current) => ({
      ...current,
      inventory_file: file?.name ?? current.inventory_file,
    }));
  };

  const validateForm = (): string | null => {
    if (!values.inventory_name.trim()) {
      return "인벤토리 이름을 입력해 주세요.";
    }
    if (mode === "create" && !selectedFile) {
      return "업로드할 파일을 선택해 주세요.";
    }
    if (values.chunk_type === CHUNK_TYPE_CUSTOM && values.chunk_size <= 0) {
      return "custom size를 선택한 경우 chunk size를 입력해 주세요.";
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
        chunk_type: uploadedRecord.chunk_type,
        chunk_size: uploadedRecord.chunk_size,
      });
      setSuccessMessage("업로드가 완료되었습니다. Embedding 버튼을 눌러 ChromaDB에 적재하세요.");
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

  const canEmbed = savedRecord?.modified === MODIFIED_NEEDS_EMBED;

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

        <div className="mt-4 space-y-3">
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
              accept=".csv,.txt,.json"
              onChange={handleFileChange}
              className="hidden"
            />
          </label>

          {values.inventory_file ? (
            <p className="text-xs text-slate-500">
              저장 확장자: <span className="text-slate-300">{values.inventory_file.split(".").pop() ?? "-"}</span>
            </p>
          ) : null}

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

          {values.chunk_type === CHUNK_TYPE_CUSTOM ? (
            <label className="block space-y-1 text-sm text-slate-300">
              <span>chunk size</span>
              <input
                type="number"
                min={1}
                value={values.chunk_size || ""}
                onChange={(event) => updateField("chunk_size", Number(event.target.value) || 0)}
                disabled={isUploading || isEmbedding}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
              />
            </label>
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
              disabled={isUploading || isEmbedding}
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
