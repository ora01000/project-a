import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "../ConfirmDialog";
import { InventoryFormModal } from "./InventoryFormModal";
import type { InventoryFormValues, InventoryRecord } from "../../types/inventory";
import { chunkTypeLabel, modifiedLabel } from "../../types/inventory";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function InventoryCsvPage() {
  const [records, setRecords] = useState<InventoryRecord[]>([]);
  const [selectedIdxSet, setSelectedIdxSet] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const selectedRecords = useMemo(
    () => records.filter((record) => selectedIdxSet.has(record.idx)),
    [records, selectedIdxSet],
  );

  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/inventory/records");
      if (!response.ok) {
        throw new Error(await parseError(response, "인벤토리 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as InventoryRecord[];
      setRecords(data);
      setSelectedIdxSet((current) => {
        const valid = new Set(data.map((record) => record.idx));
        return new Set([...current].filter((idx) => valid.has(idx)));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "인벤토리 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  const toggleRow = (idx: number) => {
    setSelectedIdxSet((current) => {
      const next = new Set(current);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIdxSet.size === records.length) {
      setSelectedIdxSet(new Set());
      return;
    }
    setSelectedIdxSet(new Set(records.map((record) => record.idx)));
  };

  const buildUploadFormData = (values: InventoryFormValues, file: File | null): FormData => {
    const formData = new FormData();
    formData.append("inventory_name", values.inventory_name.trim());
    formData.append("chunk_type", String(values.chunk_type));
    formData.append("chunk_size", String(values.chunk_size || 0));
    if (file) {
      formData.append("file", file);
    }
    return formData;
  };

  const handleCreateUpload = async (values: InventoryFormValues, file: File | null): Promise<InventoryRecord> => {
    if (!file) {
      throw new Error("업로드할 파일을 선택해 주세요.");
    }

    const response = await fetch("/api/inventory/records", {
      method: "POST",
      body: buildUploadFormData(values, file),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "인벤토리 업로드에 실패했습니다."));
    }

    const record = (await response.json()) as InventoryRecord;
    await loadRecords();
    return record;
  };

  const handleEditUpload = async (values: InventoryFormValues, file: File | null): Promise<InventoryRecord> => {
    const target = selectedRecords[0];
    if (!target) {
      throw new Error("수정할 인벤토리를 선택해 주세요.");
    }

    const response = await fetch(`/api/inventory/records/${target.idx}/upload`, {
      method: "POST",
      body: buildUploadFormData(values, file),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "인벤토리 수정에 실패했습니다."));
    }

    const record = (await response.json()) as InventoryRecord;
    await loadRecords();
    return record;
  };

  const handleEmbed = async (recordIdx: number) => {
    const response = await fetch(`/api/inventory/records/${recordIdx}/embed`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "Embedding에 실패했습니다."));
    }
    await loadRecords();
  };

  const handleDelete = async () => {
    if (selectedIdxSet.size === 0) {
      return;
    }

    const response = await fetch("/api/inventory/records", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idx_list: [...selectedIdxSet] }),
    });
    if (!response.ok) {
      setError(await parseError(response, "인벤토리 삭제에 실패했습니다."));
      setShowDeleteConfirm(false);
      return;
    }

    setShowDeleteConfirm(false);
    setSelectedIdxSet(new Set());
    setSuccessMessage("선택한 인벤토리와 ChromaDB 임베딩 정보가 삭제되었습니다.");
    await loadRecords();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">인벤토리 CSV</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            inventory 테이블 데이터를 조회하고 파일 업로드 및 ChromaDB 임베딩을 관리합니다.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={selectedIdxSet.size === 0}
            className="rounded-md border border-rose-800 px-3 py-1.5 text-sm text-rose-200 hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            삭제
          </button>
          <button
            type="button"
            onClick={() => {
              if (selectedRecords.length !== 1) {
                setError("수정할 인벤토리 1개를 선택해 주세요.");
                return;
              }
              setError(null);
              setFormMode("edit");
            }}
            disabled={selectedRecords.length !== 1}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
          >
            수정
          </button>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setFormMode("create");
            }}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            추가
          </button>
        </div>
      </header>

      {error ? (
        <div className="mx-4 mt-4 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">인벤토리 목록을 불러오는 중...</p>
        ) : records.length === 0 ? (
          <p className="text-sm text-slate-500">등록된 인벤토리가 없습니다.</p>
        ) : (
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                <th className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={records.length > 0 && selectedIdxSet.size === records.length}
                    onChange={toggleAll}
                    aria-label="전체 선택"
                  />
                </th>
                <th className="px-3 py-2">idx</th>
                <th className="px-3 py-2">인벤토리 이름</th>
                <th className="px-3 py-2">파일명</th>
                <th className="px-3 py-2">확장자</th>
                <th className="px-3 py-2">chunk type</th>
                <th className="px-3 py-2">chunk size</th>
                <th className="px-3 py-2">modified</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.idx} className="border-b border-slate-800 text-slate-200">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selectedIdxSet.has(record.idx)}
                      onChange={() => toggleRow(record.idx)}
                      aria-label={`${record.inventory_name} 선택`}
                    />
                  </td>
                  <td className="px-3 py-2">{record.idx}</td>
                  <td className="px-3 py-2">{record.inventory_name}</td>
                  <td className="px-3 py-2">{record.inventory_file}</td>
                  <td className="px-3 py-2">{record.file_ext}</td>
                  <td className="px-3 py-2">{chunkTypeLabel(record.chunk_type)}</td>
                  <td className="px-3 py-2">{record.chunk_type === 2 ? record.chunk_size : "-"}</td>
                  <td className="px-3 py-2">{modifiedLabel(record.modified)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {formMode ? (
        <InventoryFormModal
          mode={formMode}
          record={formMode === "edit" ? selectedRecords[0] : undefined}
          onClose={() => {
            setFormMode(null);
            void loadRecords();
          }}
          onUpload={formMode === "create" ? handleCreateUpload : handleEditUpload}
          onEmbed={handleEmbed}
        />
      ) : null}

      {showDeleteConfirm ? (
        <ConfirmDialog
          title="인벤토리 삭제"
          message={`선택한 ${selectedIdxSet.size}개의 인벤토리를 정말 삭제하시겠습니까?`}
          confirmLabel="삭제"
          cancelLabel="취소"
          onCancel={() => setShowDeleteConfirm(false)}
          onConfirm={() => void handleDelete()}
        />
      ) : null}

      {successMessage ? (
        <ConfirmDialog
          title="완료"
          message={successMessage}
          confirmLabel="확인"
          cancelLabel="닫기"
          onCancel={() => setSuccessMessage(null)}
          onConfirm={() => setSuccessMessage(null)}
        />
      ) : null}
    </div>
  );
}
