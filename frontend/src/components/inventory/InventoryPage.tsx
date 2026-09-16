import { useEffect, useRef, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { InventoryCsvPreview, InventoryItem } from "../../types/inventory";
import { InventoryApiPanel } from "./InventoryApiPanel";
import { InventoryCsvPreviewPanel } from "./InventoryCsvPreviewPanel";
import { InventoryListPanel } from "./InventoryListPanel";
import { WorkflowIcon } from "../workflow/WorkflowIcon";

interface InventoryPageProps {
  user: AuthUser;
}

type EditorMode = "idle" | "create" | "view";

const TABLE_NAME_PREFIX = "inventory_";
const TABLE_NAME_MAX = 50;
const TABLE_NAME_PATTERN = /^[a-z][a-z0-9_]*$/;

async function readErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") {
      return payload.detail;
    }
  } catch {
    // ignore
  }
  return fallback;
}

function validateTableNameClient(raw: string): string | null {
  const text = raw.trim().toLowerCase();
  if (!text) {
    return "인벤토리 테이블 명을 입력하세요.";
  }
  if (text.length > TABLE_NAME_MAX) {
    return `인벤토리 테이블 명은 ${TABLE_NAME_MAX}자를 넘을 수 없습니다.`;
  }
  if (!text.startsWith(TABLE_NAME_PREFIX)) {
    return `테이블 명은 반드시 "${TABLE_NAME_PREFIX}"로 시작해야 합니다.`;
  }
  if (text === TABLE_NAME_PREFIX) {
    return `"${TABLE_NAME_PREFIX}" 뒤에 식별자를 추가하세요.`;
  }
  if (!TABLE_NAME_PATTERN.test(text)) {
    return "테이블 명은 소문자·숫자·밑줄만 사용할 수 있으며, 숫자로 시작할 수 없습니다.";
  }
  if (`temp_${text}`.length > TABLE_NAME_MAX) {
    return "임시 테이블명(temp_…)이 50자를 초과합니다. 더 짧게 입력하세요.";
  }
  return null;
}

async function cleanupTempTable(tablename: string | null | undefined): Promise<void> {
  const name = (tablename || "").trim();
  if (!name) {
    return;
  }
  try {
    await fetch(`/api/inventories/temp/cleanup?tablename=${encodeURIComponent(name)}`, {
      method: "POST",
    });
  } catch {
    // best-effort
  }
}

export function InventoryPage({ user }: InventoryPageProps) {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [mode, setMode] = useState<EditorMode>("idle");
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [isListCollapsed, setIsListCollapsed] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [tableName, setTableName] = useState(TABLE_NAME_PREFIX);
  const [baselineCsv, setBaselineCsv] = useState<string | null>(null);
  const [originCsv, setOriginCsv] = useState<string | null>(null);
  const [tempTableName, setTempTableName] = useState<string | null>(null);
  const [uploadPreview, setUploadPreview] = useState<InventoryCsvPreview | null>(null);
  const [csvMismatch, setCsvMismatch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showApiPanel, setShowApiPanel] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const tempTableRef = useRef<string | null>(null);

  const selected = items.find((item) => item.table_name === selectedTable) ?? null;
  const isCreate = mode === "create";
  const isView = mode === "view" && selected != null;
  const canEditSelected =
    selected != null &&
    (selected.created_by === user.idx ||
      selected.created_by === 0 ||
      user.role === 0 ||
      user.role === 100);
  const fieldsEditable = isCreate || (isView && canEditSelected);
  const tableNameError = isCreate ? validateTableNameClient(tableName) : null;
  const saveDisabled =
    saving ||
    uploading ||
    csvMismatch ||
    !fieldsEditable ||
    !originCsv ||
    !displayName.trim() ||
    (isCreate && (tableNameError != null || !tempTableName));

  const previewTableName =
    tempTableName ||
    (isView && selected?.table_name ? selected.table_name : null) ||
    (originCsv ? tableName.trim().toLowerCase() : null);

  const loadItems = async () => {
    const response = await fetch("/api/inventories");
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, "인벤토리 목록을 불러오지 못했습니다."));
    }
    const payload = (await response.json()) as InventoryItem[];
    setItems(payload);
  };

  useEffect(() => {
    let cancelled = false;
    void loadItems().catch((err: unknown) => {
      if (!cancelled) {
        setError(err instanceof Error ? err.message : "인벤토리 목록 로드 실패");
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    tempTableRef.current = tempTableName;
  }, [tempTableName]);

  useEffect(() => {
    const onLeave = () => {
      const name = tempTableRef.current;
      if (!name) {
        return;
      }
      void fetch(`/api/inventories/temp/cleanup?tablename=${encodeURIComponent(name)}`, {
        method: "POST",
        keepalive: true,
      });
    };
    window.addEventListener("beforeunload", onLeave);
    return () => {
      window.removeEventListener("beforeunload", onLeave);
      void cleanupTempTable(tempTableRef.current);
    };
  }, []);

  const resetFileInput = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const discardTemp = async () => {
    const current = tempTableName;
    setTempTableName(null);
    await cleanupTempTable(current);
  };

  const beginCreate = () => {
    void discardTemp();
    setMode("create");
    setSelectedTable(null);
    setDisplayName("");
    setDescription("");
    setTableName(TABLE_NAME_PREFIX);
    setBaselineCsv(null);
    setOriginCsv(null);
    setUploadPreview(null);
    setCsvMismatch(false);
    setError(null);
    setStatusMessage(null);
    setShowApiPanel(false);
    resetFileInput();
  };

  const beginView = (item: InventoryItem) => {
    void discardTemp();
    setMode("view");
    setSelectedTable(item.table_name);
    setDisplayName(item.display_name);
    setDescription(item.description || "");
    setTableName(item.table_name || TABLE_NAME_PREFIX);
    setBaselineCsv(item.origin_csv || null);
    setOriginCsv(item.origin_csv || null);
    setUploadPreview(null);
    setCsvMismatch(false);
    setError(null);
    setStatusMessage(null);
    setShowApiPanel(false);
    resetFileInput();
  };

  const handleUpload = async (file: File | null) => {
    if (!file || !fieldsEditable) {
      return;
    }
    const resolvedTable = (isCreate ? tableName : selected?.table_name || tableName)
      .trim()
      .toLowerCase();
    if (isCreate) {
      const tableError = validateTableNameClient(resolvedTable);
      if (tableError) {
        setError(tableError);
        return;
      }
    } else if (!resolvedTable) {
      setError("인벤토리 테이블 명이 없습니다.");
      return;
    }

    setUploading(true);
    setError(null);
    try {
      await discardTemp();
      const form = new FormData();
      form.append("file", file);
      const params = new URLSearchParams();
      params.set("table_name", resolvedTable);
      if (displayName.trim()) {
        params.set("display_name", displayName.trim());
      }
      if (description.trim()) {
        params.set("description", description.trim());
      }
      if (isView && selected?.table_name) {
        params.set("compare_to_table", selected.table_name);
      }
      const response = await fetch(`/api/inventories/csv/upload?${params.toString()}`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "CSV 업로드에 실패했습니다."));
      }
      const preview = (await response.json()) as InventoryCsvPreview;
      setOriginCsv(preview.filename);
      setTempTableName(preview.temp_table_name || null);
      setUploadPreview(preview);

      if (isView && preview.columns_compatible === false) {
        const message =
          preview.compatibility_error ||
          "CSV 컬럼 개수/정규화 컬럼명이 기존과 일치하지 않습니다.";
        window.alert(message);
        setCsvMismatch(true);
        setError(message);
        setStatusMessage(null);
        return;
      }

      setCsvMismatch(false);
      setStatusMessage(
        `CSV 업로드·임시 테이블 전환 완료: ${preview.filename} → ${preview.temp_table_name || resolvedTable} (${preview.total_rows}행)`,
      );
    } catch (err) {
      if (isCreate) {
        setOriginCsv(null);
        setUploadPreview(null);
        setTempTableName(null);
      } else {
        setOriginCsv(baselineCsv);
        setUploadPreview(null);
        setTempTableName(null);
      }
      setCsvMismatch(false);
      setError(err instanceof Error ? err.message : "CSV 업로드 실패");
    } finally {
      setUploading(false);
      resetFileInput();
    }
  };

  const handleSave = async () => {
    if (saveDisabled) {
      return;
    }
    const name = displayName.trim();
    if (!name) {
      setError("인벤토리 이름을 입력하세요.");
      return;
    }
    if (!originCsv) {
      setError("CSV 파일을 업로드하세요.");
      return;
    }
    if (isCreate) {
      const tableError = validateTableNameClient(tableName);
      if (tableError) {
        setError(tableError);
        return;
      }
      if (!tempTableName) {
        setError("임시 테이블이 없습니다. CSV를 다시 업로드하세요.");
        return;
      }
    }

    const confirmMessage = isCreate
      ? `「${name}」 인벤토리를 저장하고 테이블 「${tableName.trim().toLowerCase()}」을(를) 생성할까요?`
      : `「${name}」 인벤토리 구성을 저장할까요?`;
    if (!window.confirm(confirmMessage)) {
      return;
    }

    setSaving(true);
    setError(null);
    try {
      if (isCreate) {
        const response = await fetch("/api/inventories", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: name,
            description: description.trim(),
            origin_csv: originCsv,
            table_name: tableName.trim().toLowerCase(),
            temp_table_name: tempTableName,
          }),
        });
        if (!response.ok) {
          throw new Error(await readErrorDetail(response, "인벤토리 저장에 실패했습니다."));
        }
        const created = (await response.json()) as InventoryItem;
        setTempTableName(null);
        await loadItems();
        beginView(created);
        setStatusMessage("인벤토리가 저장되었습니다.");
        return;
      }

      if (!selected) {
        return;
      }
      const response = await fetch(`/api/inventories/${encodeURIComponent(selected.table_name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: name,
          description: description.trim(),
          origin_csv: originCsv,
          temp_table_name: tempTableName,
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "인벤토리 수정에 실패했습니다."));
      }
      const updated = (await response.json()) as InventoryItem;
      setTempTableName(null);
      await loadItems();
      beginView({ ...selected, ...updated, table_name: selected.table_name });
      setStatusMessage("인벤토리가 저장되었습니다.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "인벤토리 저장 실패");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item: InventoryItem) => {
    const confirmed = window.confirm(
      `「${item.display_name}」 인벤토리와 테이블 「${item.table_name}」을(를) 삭제할까요?`,
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      const response = await fetch(`/api/inventories/${encodeURIComponent(item.table_name)}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "인벤토리 삭제에 실패했습니다."));
      }
      if (selectedTable === item.table_name) {
        await discardTemp();
        setMode("idle");
        setSelectedTable(null);
        setBaselineCsv(null);
        setOriginCsv(null);
        setUploadPreview(null);
        setCsvMismatch(false);
        setTableName(TABLE_NAME_PREFIX);
        setShowApiPanel(false);
      }
      await loadItems();
      setStatusMessage("인벤토리가 삭제되었습니다.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "인벤토리 삭제 실패");
    }
  };

  const canDelete = (item: InventoryItem) =>
    item.created_by === user.idx ||
    item.created_by === 0 ||
    user.role === 0 ||
    user.role === 100;

  const showEditor = isCreate || isView;

  const handleTableNameChange = (value: string) => {
    const next = value.toLowerCase();
    if (!next.startsWith(TABLE_NAME_PREFIX) && TABLE_NAME_PREFIX.startsWith(next)) {
      setTableName(TABLE_NAME_PREFIX);
      return;
    }
    if (!next.startsWith(TABLE_NAME_PREFIX)) {
      setTableName(TABLE_NAME_PREFIX);
      return;
    }
    setTableName(next.slice(0, TABLE_NAME_MAX));
  };

  return (
    <div className="flex min-h-0 flex-1 items-stretch gap-4">
      <div className="flex min-h-0 min-w-0 flex-1 gap-4 self-stretch">
        <InventoryListPanel
          collapsed={isListCollapsed}
          onCollapsedChange={setIsListCollapsed}
          onCreate={beginCreate}
          statusMessage={error || statusMessage}
          statusTone={error ? "error" : statusMessage ? "success" : "neutral"}
        >
          <div className="flex w-full flex-col gap-3">
            {items.length === 0 ? (
              <p className="text-xs text-slate-500">등록된 인벤토리가 없습니다.</p>
            ) : null}
            {items.map((item) => {
              const isActive = selectedTable === item.table_name && mode === "view";
              const author =
                (item.created_by_username || "").trim() ||
                (item.created_by ? `user#${item.created_by}` : "-");
              return (
                <div
                  key={item.table_name || item.idx}
                  className={`flex min-h-[64px] w-full flex-col justify-center gap-1 overflow-hidden rounded-xl border bg-slate-900/90 px-3 py-2 text-left shadow-lg ${
                    isActive ? "border-sky-500" : "border-slate-700"
                  }`}
                >
                  <div className="flex min-w-0 items-start gap-1">
                    <button
                      type="button"
                      onClick={() => beginView(item)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <h2
                        className="min-w-0 truncate text-sm font-semibold text-slate-100"
                        title={item.display_name}
                      >
                        {item.display_name}
                      </h2>
                    </button>
                    {canDelete(item) ? (
                      <button
                        type="button"
                        title="인벤토리 삭제"
                        aria-label="인벤토리 삭제"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleDelete(item);
                        }}
                        className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-transparent text-slate-300 hover:bg-rose-950/60 hover:text-rose-200"
                      >
                        <WorkflowIcon name="delete" size="xs" label="삭제" />
                      </button>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => beginView(item)}
                    className="text-left text-[11px] text-slate-400 hover:text-slate-300"
                  >
                    작성자 : {author}
                  </button>
                </div>
              );
            })}
          </div>
        </InventoryListPanel>

        <section className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/40">
          {!showEditor ? (
            <div className="m-auto px-6 text-center text-sm text-slate-500">
              왼쪽에서 인벤토리를 선택하거나 「새로운 인벤토리」를 시작하세요.
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col p-4">
              <header className="mb-3 flex shrink-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <h1 className="text-base font-semibold text-slate-100">
                    {isCreate ? "새로운 인벤토리" : "인벤토리 구성"}
                  </h1>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {isCreate
                      ? "CSV를 업로드해 임시 테이블로 미리본 뒤 저장합니다."
                      : "이름·설명을 수정하거나 origin_csv를 동일 컬럼으로 교체할 수 있습니다."}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {isView && selected ? (
                    <button
                      type="button"
                      onClick={() => setShowApiPanel((current) => !current)}
                      className={`rounded-md border px-4 py-2 text-sm font-medium ${
                        showApiPanel
                          ? "border-sky-500 bg-sky-900/60 text-sky-100"
                          : "border-slate-600 bg-slate-800/70 text-slate-100 hover:bg-slate-800"
                      }`}
                    >
                      API
                    </button>
                  ) : null}
                  {fieldsEditable ? (
                    <button
                      type="button"
                      disabled={saveDisabled}
                      onClick={() => void handleSave()}
                      className="rounded-md border border-sky-700 bg-sky-950/50 px-4 py-2 text-sm font-medium text-sky-100 hover:bg-sky-900/60 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {saving ? "저장 중…" : "저장"}
                    </button>
                  ) : null}
                </div>
              </header>

              <div className="flex min-h-0 min-w-0 flex-1">
                <div
                  className={`flex min-h-0 min-w-0 flex-col ${
                    showApiPanel && isView ? "w-1/2 pr-3" : "w-full"
                  }`}
                >
                  <div className="flex shrink-0 flex-col gap-3">
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-slate-300">인벤토리 이름</span>
                      <input
                        type="text"
                        value={displayName}
                        onChange={(event) => setDisplayName(event.target.value)}
                        disabled={!fieldsEditable}
                        maxLength={100}
                        className="rounded-md border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                        placeholder="예: 서버 자산 목록"
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-slate-300">인벤토리 설명</span>
                      <textarea
                        value={description}
                        onChange={(event) => setDescription(event.target.value)}
                        disabled={!fieldsEditable}
                        maxLength={200}
                        rows={2}
                        className="resize-none rounded-md border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                        placeholder="용도나 데이터 출처를 적습니다."
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-slate-300">인벤토리 테이블 명</span>
                      <input
                        type="text"
                        value={tableName}
                        onChange={(event) => handleTableNameChange(event.target.value)}
                        disabled={!isCreate}
                        maxLength={TABLE_NAME_MAX}
                        className="rounded-md border border-slate-700 bg-slate-950/80 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                        placeholder={TABLE_NAME_PREFIX}
                      />
                      {isCreate && tableNameError ? (
                        <span className="text-[11px] text-rose-300">{tableNameError}</span>
                      ) : (
                        <span className="text-[11px] text-slate-500">
                          PostgreSQL 테이블명. 업로드 시 temp_ 접두 임시 테이블로 미리보고, 저장 시
                          확정됩니다.
                        </span>
                      )}
                    </label>
                    <div className="flex flex-wrap items-center gap-3">
                      {fieldsEditable ? (
                        <>
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept=".csv,text/csv"
                            className="hidden"
                            onChange={(event) => {
                              const file = event.target.files?.[0] ?? null;
                              void handleUpload(file);
                            }}
                          />
                          <button
                            type="button"
                            disabled={uploading}
                            onClick={() => fileInputRef.current?.click()}
                            className="inline-flex items-center justify-center rounded-md border border-slate-600 bg-slate-800/70 px-3 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                          >
                            {uploading
                              ? "업로드 중…"
                              : isCreate
                                ? "CSV 파일 업로드"
                                : "CSV 파일 교체"}
                          </button>
                        </>
                      ) : null}
                      {originCsv ? (
                        <span className="truncate text-xs text-slate-400" title={originCsv}>
                          {originCsv}
                          {tempTableName ? ` · ${tempTableName}` : ""}
                        </span>
                      ) : null}
                    </div>
                    {csvMismatch ? (
                      <p className="text-xs text-rose-300">
                        컬럼이 일치하지 않아 저장할 수 없습니다. 동일 컬럼의 CSV로 다시 업로드하세요.
                      </p>
                    ) : null}
                  </div>

                  <InventoryCsvPreviewPanel
                    tableName={previewTableName}
                    filename={originCsv}
                    initialPreview={uploadPreview}
                    className="mt-4 min-h-0 w-full flex-1"
                  />
                </div>
                {showApiPanel && isView && selected ? (
                  <InventoryApiPanel
                    tableName={selected.table_name}
                    user={user}
                    canEdit={canEditSelected}
                    onClose={() => setShowApiPanel(false)}
                    className="w-1/2"
                  />
                ) : null}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
