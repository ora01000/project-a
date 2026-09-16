import { useCallback, useEffect, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { InventoryApiItem } from "../../types/inventory";
import { WorkflowIcon } from "../workflow/WorkflowIcon";
import { InventoryApiTestModal } from "./InventoryApiTestModal";

interface InventoryApiPanelProps {
  tableName: string;
  user: AuthUser;
  canEdit: boolean;
  onClose: () => void;
  className?: string;
}

type FormMode = "closed" | "create" | "edit";

const API_NAME_PATTERN = /^[a-z][a-z0-9_]*$/;

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

function parseParamList(raw: string): string[] {
  return (raw || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function InventoryApiPanel({
  tableName,
  user,
  canEdit,
  onClose,
  className = "",
}: InventoryApiPanelProps) {
  const [apis, setApis] = useState<InventoryApiItem[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [formMode, setFormMode] = useState<FormMode>("closed");
  const [editingName, setEditingName] = useState<string | null>(null);
  const [apiName, setApiName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [whereExp, setWhereExp] = useState("");
  const [selectExp, setSelectExp] = useState("*");
  const [selectedParams, setSelectedParams] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [testingApi, setTestingApi] = useState<InventoryApiItem | null>(null);

  const isCreate = formMode === "create";
  const isEdit = formMode === "edit";
  const formOpen = formMode !== "closed";
  const formEditable = isCreate || (isEdit && canEdit);
  const apiFullpathPreview = apiName.trim()
    ? `/inv/${tableName}/${apiName.trim().toLowerCase()}`
    : `/inv/${tableName}/{api_name}`;

  const loadApis = useCallback(async () => {
    const response = await fetch(`/api/inventories/${encodeURIComponent(tableName)}/apis`);
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, "API 목록을 불러오지 못했습니다."));
    }
    setApis((await response.json()) as InventoryApiItem[]);
  }, [tableName]);

  const loadColumns = useCallback(async () => {
    const response = await fetch(`/api/inventories/${encodeURIComponent(tableName)}/columns`);
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, "컬럼 목록을 불러오지 못했습니다."));
    }
    setColumns((await response.json()) as string[]);
  }, [tableName]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void Promise.all([loadApis(), loadColumns()])
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "API 패널 로드 실패");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadApis, loadColumns, tableName]);

  const resetForm = () => {
    setApiName("");
    setDisplayName("");
    setDescription("");
    setWhereExp("");
    setSelectExp("*");
    setSelectedParams([]);
    setEditingName(null);
    setFormMode("closed");
  };

  const beginCreate = () => {
    setError(null);
    setEditingName(null);
    setApiName("");
    setDisplayName("");
    setDescription("");
    setWhereExp("");
    setSelectExp("*");
    setSelectedParams([]);
    setFormMode("create");
  };

  const beginEdit = (item: InventoryApiItem) => {
    setError(null);
    setEditingName(item.api_name);
    setApiName(item.api_name);
    setDisplayName(item.display_name);
    setDescription(item.description || "");
    setWhereExp(item.where_exp || "");
    setSelectExp(item.select_exp || "*");
    setSelectedParams(parseParamList(item.param_columns));
    setFormMode("edit");
  };

  const handleSelectCard = (item: InventoryApiItem) => {
    if (formMode === "edit" && editingName === item.api_name) {
      resetForm();
      return;
    }
    beginEdit(item);
  };

  const toggleParam = (col: string) => {
    if (!formEditable) {
      return;
    }
    setSelectedParams((current) =>
      current.includes(col) ? current.filter((item) => item !== col) : [...current, col],
    );
  };

  const validateForm = (): string | null => {
    const name = apiName.trim().toLowerCase();
    if (!name || !API_NAME_PATTERN.test(name)) {
      return "API 이름은 영문 소문자·숫자·밑줄만 사용할 수 있습니다.";
    }
    if (!displayName.trim()) {
      return "디스플레이 명을 입력하세요.";
    }
    if (!whereExp.trim()) {
      return "조건절(where)을 입력하세요.";
    }
    if (!selectExp.trim()) {
      return "출력절(select)을 입력하세요.";
    }
    if (selectedParams.length === 0) {
      return "API 매개변수 컬럼을 1개 이상 선택하세요.";
    }
    return null;
  };

  const handleSave = async () => {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }
    if (isEdit && !canEdit) {
      setError("이 API를 수정할 권한이 없습니다.");
      return;
    }

    const payload = {
      api_name: apiName.trim().toLowerCase(),
      display_name: displayName.trim(),
      description: description.trim(),
      where_exp: whereExp.trim(),
      select_exp: selectExp.trim(),
      param_columns: selectedParams.join(","),
    };

    setSaving(true);
    setError(null);
    try {
      if (isCreate) {
        const response = await fetch(`/api/inventories/${encodeURIComponent(tableName)}/apis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error(await readErrorDetail(response, "API 생성에 실패했습니다."));
        }
        await loadApis();
        resetForm();
        return;
      }

      if (!editingName) {
        return;
      }
      const response = await fetch(
        `/api/inventories/${encodeURIComponent(tableName)}/apis/${encodeURIComponent(editingName)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "API 수정에 실패했습니다."));
      }
      await loadApis();
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "API 저장 실패");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item: InventoryApiItem) => {
    const confirmed = window.confirm(`「${item.display_name}」 API를 삭제할까요?`);
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      const response = await fetch(
        `/api/inventories/${encodeURIComponent(tableName)}/apis/${encodeURIComponent(item.api_name)}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        throw new Error(await readErrorDetail(response, "API 삭제에 실패했습니다."));
      }
      if (editingName === item.api_name) {
        resetForm();
      }
      await loadApis();
    } catch (err) {
      setError(err instanceof Error ? err.message : "API 삭제 실패");
    }
  };

  const canDeleteApi = (item: InventoryApiItem) =>
    item.created_by === user.idx ||
    item.created_by === 0 ||
    user.role === 0 ||
    user.role === 100;

  return (
    <aside
      className={`flex min-h-0 min-w-0 flex-col border-l border-slate-700 bg-slate-950/30 ${className}`.trim()}
    >
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-700/80 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-slate-200">API 목록</h2>
          <p className="mt-0.5 truncate text-[11px] text-slate-500">{tableName}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {canEdit ? (
            <button
              type="button"
              onClick={() => {
                if (formMode === "create") {
                  resetForm();
                } else {
                  beginCreate();
                }
              }}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                formMode === "create"
                  ? "border-sky-500 bg-sky-900/60 text-sky-100"
                  : "border-sky-700 bg-sky-950/50 text-sky-100 hover:bg-sky-900/60"
              }`}
            >
              API생성
            </button>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 bg-slate-800/70 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>
      </header>

      {error ? (
        <p className="shrink-0 px-4 py-2 text-xs text-rose-300">{error}</p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {formOpen ? (
          <section className="mb-4 rounded-lg border border-sky-800/60 bg-slate-900/70 p-3">
            <h3 className="mb-3 text-xs font-semibold text-sky-200">
              {isCreate ? "새 API" : "API 편집"}
            </h3>
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-slate-300">API 이름</span>
                <input
                  type="text"
                  value={apiName}
                  onChange={(event) => setApiName(event.target.value.toLowerCase())}
                  disabled={!formEditable}
                  maxLength={50}
                  className="rounded-md border border-slate-700 bg-slate-950/80 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                  placeholder="server_by_hostname"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-slate-300">디스플레이 명</span>
                <input
                  type="text"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  disabled={!formEditable}
                  maxLength={100}
                  className="rounded-md border border-slate-700 bg-slate-950/80 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-slate-300">설명</span>
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  disabled={!formEditable}
                  maxLength={200}
                  rows={2}
                  className="resize-none rounded-md border border-slate-700 bg-slate-950/80 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                />
              </label>
              <div className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-slate-300">api_fullpath</span>
                <p className="truncate font-mono text-[11px] text-slate-400" title={apiFullpathPreview}>
                  {apiFullpathPreview}
                </p>
              </div>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-slate-300">조건절 (WHERE 이후)</span>
                <input
                  type="text"
                  value={whereExp}
                  onChange={(event) => setWhereExp(event.target.value)}
                  disabled={!formEditable}
                  maxLength={500}
                  className="rounded-md border border-slate-700 bg-slate-950/80 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                  placeholder="hostname = {hostname} AND env = {env}"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-medium text-slate-300">출력절 (SELECT 이후)</span>
                <input
                  type="text"
                  value={selectExp}
                  onChange={(event) => setSelectExp(event.target.value)}
                  disabled={!formEditable}
                  maxLength={500}
                  className="rounded-md border border-slate-700 bg-slate-950/80 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
                  placeholder="hostname, ip, env"
                />
              </label>
              <p className="text-[11px] text-slate-500">
                조건절/출력절은 plain SQL입니다. 매개변수는 {"{column}"} 형식.
                예: asset_id like &apos;%{"{asset_id}"}%&apos;
              </p>
              <fieldset className="flex flex-col gap-1">
                <legend className="text-[11px] font-medium text-slate-300">API 매개변수</legend>
                <div className="flex flex-wrap gap-2">
                  {columns.map((col) => {
                    const checked = selectedParams.includes(col);
                    return (
                      <label
                        key={col}
                        className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] ${
                          formEditable ? "cursor-pointer" : "cursor-default opacity-80"
                        } ${
                          checked
                            ? "border-sky-600 bg-sky-950/50 text-sky-100"
                            : "border-slate-700 text-slate-300"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!formEditable}
                          onChange={() => toggleParam(col)}
                          className="h-3 w-3"
                        />
                        {col}
                      </label>
                    );
                  })}
                </div>
              </fieldset>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-md border border-slate-600 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
                >
                  취소
                </button>
                {formEditable ? (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void handleSave()}
                    className="rounded-md border border-sky-700 bg-sky-950/50 px-3 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-900/60 disabled:opacity-50"
                  >
                    {saving ? "저장 중…" : isCreate ? "생성" : "저장"}
                  </button>
                ) : null}
              </div>
            </div>
          </section>
        ) : null}

        {loading ? (
          <p className="text-xs text-slate-500">로딩 중…</p>
        ) : apis.length === 0 ? (
          <p className="text-xs text-slate-500">등록된 API가 없습니다.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {apis.map((item) => {
              const isActive = formMode === "edit" && editingName === item.api_name;
              return (
                <article
                  key={item.api_name}
                  className={`rounded-xl border bg-slate-900/90 px-3 py-2 shadow-lg ${
                    isActive ? "border-sky-500" : "border-slate-700"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <button
                      type="button"
                      onClick={() => handleSelectCard(item)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <h3
                        className="truncate text-sm font-semibold text-slate-100"
                        title={item.display_name}
                      >
                        {item.display_name}
                      </h3>
                      <p
                        className="truncate font-mono text-[11px] text-slate-400"
                        title={item.api_name}
                      >
                        {item.api_name}
                      </p>
                    </button>
                    {canDeleteApi(item) ? (
                      <button
                        type="button"
                        title="API 삭제"
                        aria-label="API 삭제"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleDelete(item);
                        }}
                        className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm text-slate-300 hover:bg-rose-950/60 hover:text-rose-200"
                      >
                        <WorkflowIcon name="delete" size="xs" label="삭제" />
                      </button>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleSelectCard(item)}
                    className="mt-1 w-full text-left"
                  >
                    <p
                      className="truncate font-mono text-[11px] text-sky-300/90"
                      title={item.api_fullpath}
                    >
                      {item.api_fullpath}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-400">
                      input: {item.param_columns || "-"}
                    </p>
                  </button>
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setTestingApi(item);
                      }}
                      className="inline-flex items-center gap-1 rounded-md border border-slate-600 bg-slate-800/70 px-2.5 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-800"
                    >
                      <WorkflowIcon name="run" size="xs" label="테스트" />
                      테스트
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
      {testingApi ? (
        <InventoryApiTestModal api={testingApi} onClose={() => setTestingApi(null)} />
      ) : null}
    </aside>
  );
}
