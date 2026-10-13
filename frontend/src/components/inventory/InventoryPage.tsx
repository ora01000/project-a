import { useEffect, useRef, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type {
  InventoryApiAuthType,
  InventoryCsvPreview,
  InventoryItem,
  InventoryOriginMode,
} from "../../types/inventory";
import { InventoryApiPanel } from "./InventoryApiPanel";
import { InventoryCsvPreviewPanel } from "./InventoryCsvPreviewPanel";
import { InventoryListPanel } from "./InventoryListPanel";
import {
  InventoryOriginApiTestModal,
  type InventoryOriginApiTestResult,
} from "./InventoryOriginApiTestModal";
import { InventoryStatsPanel } from "./InventoryStatsPanel";
import { WorkflowIcon } from "../workflow/WorkflowIcon";
import {
  DEFAULT_WORKFLOW_CRON_EXPR,
  WorkflowScheduleField,
} from "../workflow/WorkflowScheduleField";

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
  const [originMode, setOriginMode] = useState<InventoryOriginMode>("csv");
  const [originApiUrl, setOriginApiUrl] = useState("");
  const [originApiKey, setOriginApiKey] = useState("");
  const [originApiAuthType, setOriginApiAuthType] = useState<InventoryApiAuthType>(1);
  const [stagedResponseJson, setStagedResponseJson] = useState<unknown>(null);
  const [isScheduled, setIsScheduled] = useState(false);
  const [apiCrawlingCron, setApiCrawlingCron] = useState("");
  const [retrieving, setRetrieving] = useState(false);
  const [testingApi, setTestingApi] = useState(false);
  const [apiTestResult, setApiTestResult] = useState<InventoryOriginApiTestResult | null>(null);
  const [tempTableName, setTempTableName] = useState<string | null>(null);
  const [uploadPreview, setUploadPreview] = useState<InventoryCsvPreview | null>(null);
  const [csvMismatch, setCsvMismatch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showApiPanel, setShowApiPanel] = useState(false);
  const [statsRefreshKey, setStatsRefreshKey] = useState(0);
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
  const hasStagedData = isCreate
    ? Boolean(
        tempTableName &&
          (originMode === "csv" ? originCsv : stagedResponseJson != null),
      )
    : originMode === "csv"
      ? Boolean(originCsv)
      : Boolean(originApiUrl.trim());
  const apiFieldsReady =
    originMode !== "api" ||
    (Boolean(originApiUrl.trim()) &&
      (!isScheduled || Boolean(apiCrawlingCron.trim())));
  const saveDisabled =
    saving ||
    uploading ||
    retrieving ||
    csvMismatch ||
    !fieldsEditable ||
    !hasStagedData ||
    !displayName.trim() ||
    !apiFieldsReady ||
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

  const refreshListAndStats = async () => {
    await loadItems();
    setStatsRefreshKey((current) => current + 1);
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
    setOriginMode("csv");
    setOriginApiUrl("");
    setOriginApiKey("");
    setOriginApiAuthType(1);
    setStagedResponseJson(null);
    setIsScheduled(false);
    setApiCrawlingCron("");
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
    setOriginMode(item.origin_type === 2 ? "api" : "csv");
    setOriginApiUrl(item.origin_api_url || "");
    setOriginApiKey("");
    setOriginApiAuthType(item.origin_api_auth_type === 2 ? 2 : 1);
    setStagedResponseJson(null);
    setIsScheduled(Boolean(item.is_scheduled));
    setApiCrawlingCron(item.api_crawling_cron || "");
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

  const runApiRetrieve = async (): Promise<boolean> => {
    if (!fieldsEditable || originMode !== "api") {
      return false;
    }
    const resolvedTable = (isCreate ? tableName : selected?.table_name || tableName)
      .trim()
      .toLowerCase();
    if (isCreate) {
      const tableError = validateTableNameClient(resolvedTable);
      if (tableError) {
        setError(tableError);
        return false;
      }
    } else if (!resolvedTable) {
      setError("인벤토리 테이블 명이 없습니다.");
      return false;
    }
    const url = originApiUrl.trim();
    if (!url) {
      setError("API 경로를 입력하세요.");
      return false;
    }
    if (!/^https?:\/\//i.test(url)) {
      setError("API 경로는 http(s)로 시작해야 합니다.");
      return false;
    }

    setRetrieving(true);
    setError(null);
    try {
      await discardTemp();
      const response = await fetch("/api/inventories/apicall/retrieve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          table_name: resolvedTable,
          api_url: url,
          api_key: originApiKey.trim() || null,
          auth_type: originApiAuthType,
          display_name: displayName.trim() || null,
          description: description.trim() || null,
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "API 조회에 실패했습니다."));
      }
      const preview = (await response.json()) as InventoryCsvPreview;
      setOriginCsv(null);
      setStagedResponseJson(preview.response_json ?? null);
      setTempTableName(preview.temp_table_name || null);
      setUploadPreview(preview);
      setCsvMismatch(false);
      setStatusMessage(
        `임시 테이블·미리보기 준비 완료 → ${preview.temp_table_name || resolvedTable} (${preview.total_rows}행)`,
      );
      return true;
    } catch (err) {
      setStagedResponseJson(null);
      setUploadPreview(null);
      setTempTableName(null);
      setCsvMismatch(false);
      setError(err instanceof Error ? err.message : "API 조회 실패");
      return false;
    } finally {
      setRetrieving(false);
    }
  };

  const handleTestOriginApi = async () => {
    const url = originApiUrl.trim();
    if (!url) {
      setError("API 경로를 입력하세요.");
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      setError("API 경로는 http(s)로 시작해야 합니다.");
      return;
    }
    if (isCreate) {
      const tableError = validateTableNameClient(tableName.trim().toLowerCase());
      if (tableError) {
        setError(tableError);
        return;
      }
    }
    setTestingApi(true);
    setError(null);
    try {
      const response = await fetch("/api/inventories/apicall/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_url: url,
          api_key: originApiKey.trim() || null,
          auth_type: originApiAuthType,
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "API 테스트에 실패했습니다."));
      }
      const payload = (await response.json()) as InventoryOriginApiTestResult;
      setApiTestResult(payload);
      if (!payload.ok) {
        setStagedResponseJson(null);
        setUploadPreview(null);
        setTempTableName(null);
        setStatusMessage(null);
        setError(payload.error || payload.message || "API 테스트가 실패했습니다.");
        return;
      }
      // CSV 업로드와 동일하게: 테스트 성공 후 temp 테이블·미리보기 생성
      setStatusMessage("API 테스트 성공. 임시 테이블을 생성합니다…");
      setTestingApi(false);
      await runApiRetrieve();
    } catch (err) {
      setError(err instanceof Error ? err.message : "API 테스트 실패");
    } finally {
      setTestingApi(false);
    }
  };

  const handleRetrieve = async () => {
    await runApiRetrieve();
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
    if (originMode === "csv" && !originCsv) {
      setError("CSV 파일을 업로드하세요.");
      return;
    }
    if (originMode === "api") {
      if (!originApiUrl.trim()) {
        setError("API 경로를 입력하세요.");
        return;
      }
      if (isScheduled && !apiCrawlingCron.trim()) {
        setError("스케줄링 cron 표현식을 입력하세요.");
        return;
      }
      if (stagedResponseJson == null && isCreate) {
        setError("API 조회를 먼저 수행하세요.");
        return;
      }
      if (originApiAuthType === 2 && originApiKey.trim()) {
        const parts = originApiKey.trim().split(":");
        if (parts.length < 2 || !parts[0].trim() || !parts.slice(1).join(":").trim()) {
          setError("header 인증은 key:value 형식으로 입력하세요.");
          return;
        }
      }
    }
    if (isCreate) {
      const tableError = validateTableNameClient(tableName);
      if (tableError) {
        setError(tableError);
        return;
      }
      if (!tempTableName) {
        setError(
          originMode === "api"
            ? "임시 테이블이 없습니다. API 조회를 다시 수행하세요."
            : "임시 테이블이 없습니다. CSV를 다시 업로드하세요.",
        );
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
            origin_csv: originMode === "csv" ? originCsv : null,
            table_name: tableName.trim().toLowerCase(),
            temp_table_name: tempTableName,
            origin_type: originMode === "api" ? 2 : 1,
            origin_api_url: originMode === "api" ? originApiUrl.trim() : null,
            origin_api_key: originMode === "api" ? originApiKey.trim() || null : null,
            origin_api_auth_type: originMode === "api" ? originApiAuthType : 1,
            is_scheduled: originMode === "api" ? isScheduled : false,
            api_crawling_cron:
              originMode === "api" && isScheduled ? apiCrawlingCron.trim() : null,
            transfer_filename: originMode === "csv" ? originCsv : null,
            response_json: originMode === "api" ? stagedResponseJson : null,
          }),
        });
        if (!response.ok) {
          throw new Error(await readErrorDetail(response, "인벤토리 저장에 실패했습니다."));
        }
        const created = (await response.json()) as InventoryItem;
        setTempTableName(null);
        await refreshListAndStats();
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
          origin_csv: originMode === "csv" ? originCsv : null,
          temp_table_name: tempTableName,
          origin_type: originMode === "api" ? 2 : 1,
          origin_api_url: originMode === "api" ? originApiUrl.trim() : null,
          origin_api_key: originMode === "api" ? originApiKey.trim() || null : null,
          origin_api_auth_type: originMode === "api" ? originApiAuthType : 1,
          is_scheduled: originMode === "api" ? isScheduled : false,
          api_crawling_cron:
            originMode === "api" && isScheduled ? apiCrawlingCron.trim() : null,
          transfer_filename: originMode === "csv" ? originCsv : null,
          response_json: originMode === "api" ? stagedResponseJson : null,
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "인벤토리 수정에 실패했습니다."));
      }
      const updated = (await response.json()) as InventoryItem;
      setTempTableName(null);
      await refreshListAndStats();
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
      await refreshListAndStats();
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
              const isApiOrigin = item.origin_type === 2;
              const originLabel = isApiOrigin ? "API 호출" : "CSV 업로드";
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
                  <div className="flex min-w-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => beginView(item)}
                      className="min-w-0 flex-1 truncate text-left text-[11px] text-slate-400 hover:text-slate-300"
                    >
                      작성자 : {author}
                    </button>
                    <span className="inline-flex shrink-0 items-center gap-1">
                      <span
                        className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                          isApiOrigin
                            ? "border-violet-700/70 bg-violet-950/40 text-violet-200"
                            : "border-sky-700/70 bg-sky-950/40 text-sky-200"
                        }`}
                        title={originLabel}
                      >
                        {isApiOrigin ? "API" : "CSV"}
                      </span>
                      {item.is_scheduled ? (
                        <span
                          title={
                            item.api_crawling_cron
                              ? `스케줄 ${item.api_crawling_cron}`
                              : "스케줄"
                          }
                        >
                          <WorkflowIcon name="schedule" size="xs" label="스케줄" />
                        </span>
                      ) : null}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </InventoryListPanel>

        <section className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/40">
          {!showEditor ? (
            <InventoryStatsPanel
              refreshKey={statsRefreshKey}
              onSelectRow={(row) => {
                const existing = items.find((entry) => entry.table_name === row.table_name);
                beginView(
                  existing ?? {
                    idx: 0,
                    table_name: row.table_name,
                    display_name: row.display_name || row.table_name,
                    description: row.description || "",
                    created_by: row.created_by,
                    created_by_username: row.created_by_username,
                    origin_csv: row.origin_csv,
                    created_at: row.created_at,
                  },
                );
              }}
              onSelectApiRow={(row) => {
                const existing = items.find((entry) => entry.table_name === row.table_name);
                beginView(
                  existing ?? {
                    idx: 0,
                    table_name: row.table_name,
                    display_name: row.table_name,
                    description: "",
                    created_by: row.created_by,
                    created_by_username: row.created_by_username,
                    origin_csv: "",
                  },
                );
                setShowApiPanel(true);
              }}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col p-4">
              <header className="mb-3 flex shrink-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <h1 className="inline-flex items-center gap-1.5 text-base font-semibold text-slate-100">
                    <WorkflowIcon name="inventory" size="sm" />
                    {isCreate ? "새로운 인벤토리" : "인벤토리 구성"}
                  </h1>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {isCreate
                      ? "CSV 업로드 또는 API 호출로 임시 테이블을 미리본 뒤 저장합니다."
                      : "이름·설명을 수정하거나 데이터 출처를 동일 컬럼으로 교체할 수 있습니다."}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {isView && selected ? (
                    <button
                      type="button"
                      onClick={() => setShowApiPanel((current) => !current)}
                      className={`inline-flex items-center gap-1.5 rounded-md border px-4 py-2 text-sm font-medium ${
                        showApiPanel
                          ? "border-sky-500 bg-sky-900/60 text-sky-100"
                          : "border-slate-600 bg-slate-800/70 text-slate-100 hover:bg-slate-800"
                      }`}
                    >
                      <WorkflowIcon name="api" size="sm" label="API" />
                      API
                    </button>
                  ) : null}
                  {fieldsEditable ? (
                    <button
                      type="button"
                      disabled={saveDisabled}
                      onClick={() => void handleSave()}
                      className="inline-flex items-center gap-1.5 rounded-md border border-sky-700 bg-sky-950/50 px-4 py-2 text-sm font-medium text-sky-100 hover:bg-sky-900/60 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <WorkflowIcon name="save" size="sm" label="저장" />
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
                    {isCreate ? (
                      <div className="flex flex-col gap-2">
                        <span className="text-xs font-medium text-slate-300">데이터 출처</span>
                        <div className="flex flex-wrap gap-2">
                          {(
                            [
                              { id: "csv" as const, label: "CSV 파일 업로드" },
                              { id: "api" as const, label: "API 호출" },
                            ] as const
                          ).map((option) => (
                            <button
                              key={option.id}
                              type="button"
                              disabled={!fieldsEditable}
                              onClick={() => {
                                if (originMode === option.id) {
                                  return;
                                }
                                void discardTemp();
                                setOriginMode(option.id);
                                setOriginCsv(null);
                                                            setStagedResponseJson(null);
                                setUploadPreview(null);
                                setCsvMismatch(false);
                                setStatusMessage(null);
                                resetFileInput();
                              }}
                              className={`rounded-md border px-3 py-1.5 text-sm ${
                                originMode === option.id
                                  ? "border-sky-500 bg-sky-950/50 text-sky-100"
                                  : "border-slate-600 bg-slate-800/70 text-slate-200 hover:bg-slate-800"
                              }`}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {originMode === "csv" ? (
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
                              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-slate-600 bg-slate-800/70 px-3 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                            >
                              <WorkflowIcon
                                name="upload"
                                size="sm"
                                label={isCreate ? "CSV 업로드" : "CSV 교체"}
                              />
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
                    ) : (
                      <div className="flex flex-col gap-3">
                        <label className="flex flex-col gap-1">
                          <span className="text-xs font-medium text-slate-300">API 경로</span>
                          <input
                            type="url"
                            value={originApiUrl}
                            onChange={(event) => setOriginApiUrl(event.target.value)}
                            disabled={!fieldsEditable}
                            maxLength={500}
                            className="rounded-md border border-slate-700 bg-slate-950/80 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                            placeholder="https://example.internal/api/assets"
                          />
                        </label>
                        <div className="flex flex-col gap-2">
                          <span className="text-xs font-medium text-slate-300">API 인증 방식</span>
                          <div className="flex flex-wrap gap-2">
                            {(
                              [
                                { id: 1 as const, label: "Bearer" },
                                { id: 2 as const, label: "Header" },
                              ] as const
                            ).map((option) => (
                              <button
                                key={option.id}
                                type="button"
                                disabled={!fieldsEditable}
                                onClick={() => setOriginApiAuthType(option.id)}
                                className={`rounded-md border px-3 py-1.5 text-sm ${
                                  originApiAuthType === option.id
                                    ? "border-sky-500 bg-sky-950/50 text-sky-100"
                                    : "border-slate-600 bg-slate-800/70 text-slate-200 hover:bg-slate-800"
                                }`}
                              >
                                {option.label}
                              </button>
                            ))}
                          </div>
                        </div>
                        <label className="flex flex-col gap-1">
                          <span className="text-xs font-medium text-slate-300">API KEY</span>
                          <input
                            type="password"
                            value={originApiKey}
                            onChange={(event) => setOriginApiKey(event.target.value)}
                            disabled={!fieldsEditable}
                            maxLength={500}
                            autoComplete="off"
                            className="rounded-md border border-slate-700 bg-slate-950/80 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                            placeholder={
                              originApiAuthType === 2
                                ? "Header-Name:value"
                                : isView && selected?.has_api_key
                                  ? "변경 시에만 입력 (비우면 저장 시 키가 삭제될 수 있음)"
                                  : "Bearer 토큰 (선택)"
                            }
                          />
                          {originApiAuthType === 2 ? (
                            <span className="text-[11px] text-slate-500">
                              header 방식은 <span className="font-mono">key:value</span> 형식으로 입력합니다.
                            </span>
                          ) : null}
                        </label>
                        <WorkflowScheduleField
                          enabled={isScheduled}
                          cronExpr={apiCrawlingCron || DEFAULT_WORKFLOW_CRON_EXPR}
                          readOnly={!fieldsEditable}
                          onChange={({ enabled, cronExpr }) => {
                            setIsScheduled(enabled);
                            setApiCrawlingCron(
                              enabled
                                ? (cronExpr || DEFAULT_WORKFLOW_CRON_EXPR).slice(0, 100)
                                : apiCrawlingCron,
                            );
                          }}
                        />
                        {fieldsEditable ? (
                          <div className="flex flex-wrap items-center gap-3">
                            <button
                              type="button"
                              disabled={testingApi || retrieving || !originApiUrl.trim()}
                              onClick={() => void handleTestOriginApi()}
                              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-slate-600 bg-slate-800/70 px-3 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                            >
                              <WorkflowIcon name="validate" size="sm" label="API 테스트" />
                              {testingApi || retrieving
                                ? "테스트·미리보기 중…"
                                : "API 테스트"}
                            </button>
                            <button
                              type="button"
                              disabled={retrieving || testingApi || !originApiUrl.trim()}
                              onClick={() => void handleRetrieve()}
                              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-slate-600 bg-slate-800/70 px-3 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                            >
                              <WorkflowIcon name="refresh" size="sm" label="API 조회" />
                              {retrieving && !testingApi ? "조회 중…" : "미리보기 다시 조회"}
                            </button>
                            {tempTableName || stagedResponseJson != null ? (
                              <span className="truncate text-xs text-slate-400">
                                {stagedResponseJson != null ? "조회 완료" : ""}
                                {tempTableName ? ` · ${tempTableName}` : ""}
                              </span>
                            ) : null}
                          </div>
                        ) : selected?.origin_api_url ? (
                          <p className="truncate text-xs text-slate-400" title={selected.origin_api_url}>
                            {selected.origin_api_url}
                            {selected.is_scheduled && selected.api_crawling_cron
                              ? ` · cron ${selected.api_crawling_cron}`
                              : ""}
                          </p>
                        ) : null}
                      </div>
                    )}
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
      {apiTestResult ? (
        <InventoryOriginApiTestModal
          result={apiTestResult}
          onClose={() => setApiTestResult(null)}
        />
      ) : null}
    </div>
  );
}
