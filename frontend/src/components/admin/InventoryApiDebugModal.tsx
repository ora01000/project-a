import { useEffect, useRef, useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface InventoryApiDebugModalProps {
  viewerRole: number;
  onClose: () => void;
}

type EndpointId =
  | "uploadCSV"
  | "transferCSV2Table"
  | "retrieve"
  | "testAPI"
  | "transferJSON2Table"
  | "addInventory"
  | "getInventoryList"
  | "getInventorySchema"
  | "getRecordsWithRows"
  | "getCount"
  | "getAllDataInColumn"
  | "sql"
  | "removeInventory"
  | "removeTempTable"
  | "getInventoryAPIList"
  | "addInventoryAPI"
  | "updateInventoryAPI"
  | "removeInventoryAPI"
  | "reloadAPI";

const ENDPOINTS: Array<{ id: EndpointId; method: string; path: string; label: string }> = [
  { id: "uploadCSV", method: "POST", path: "/uploadCSV", label: "CSV 업로드" },
  { id: "transferCSV2Table", method: "POST", path: "/transferCSV2Table", label: "CSV→테이블" },
  { id: "retrieve", method: "POST", path: "/retrieve", label: "API retrieve" },
  { id: "testAPI", method: "POST", path: "/testAPI", label: "API 테스트" },
  { id: "transferJSON2Table", method: "POST", path: "/transferJSON2Table", label: "JSON→테이블" },
  { id: "addInventory", method: "POST", path: "/addInventory", label: "인벤토리 등록" },
  { id: "getInventoryList", method: "GET", path: "/getInventoryList", label: "인벤토리 목록" },
  { id: "getInventorySchema", method: "GET", path: "/getInventorySchema", label: "스키마 조회" },
  { id: "getRecordsWithRows", method: "GET", path: "/getRecordsWithRows", label: "행 조회" },
  { id: "getCount", method: "GET", path: "/getCount", label: "건수 조회" },
  { id: "getAllDataInColumn", method: "GET", path: "/getAllDataInColumn", label: "컬럼 전체" },
  { id: "sql", method: "POST", path: "/sql", label: "SQL 실행" },
  { id: "removeInventory", method: "POST", path: "/removeInventory", label: "인벤토리 삭제" },
  { id: "removeTempTable", method: "POST", path: "/removeTempTable", label: "임시테이블 삭제" },
  { id: "getInventoryAPIList", method: "GET", path: "/getInventoryAPIList", label: "정의 API 목록" },
  { id: "addInventoryAPI", method: "POST", path: "/addInventoryAPI", label: "정의 API 추가" },
  { id: "updateInventoryAPI", method: "POST", path: "/updateInventoryAPI", label: "정의 API 수정" },
  { id: "removeInventoryAPI", method: "POST", path: "/removeInventoryAPI", label: "정의 API 삭제" },
  { id: "reloadAPI", method: "POST", path: "/reloadAPI", label: "정의 API reload" },
];

const MOCK_BASE_URL = "http://inventory-api.ora01000.pe.kr:32716";
const HTTP_BASE_URL = "http://inventory-api.mcps.svc.cluster.local:9000";
const FALLBACK_BASE_URL = MOCK_BASE_URL;

const DEFAULT_TRANSFER_JSON = `{
  "response_json": [{"col1": "a", "col2": "b"}],
  "tablename": "temp_assets"
}`;

const DEFAULT_ADD_INVENTORY = `{
  "table_name": "inventory_servers",
  "display_name": "servers",
  "description": "",
  "origin_type": 1,
  "origin_csv": "servers.csv"
}`;

const DEFAULT_ADD_API = `{
  "api_name": "search_by_ip",
  "display_name": "IP 검색",
  "description": "",
  "table_name": "inventory_servers",
  "where_exp": "ip_address like '%{ip}%'",
  "select_exp": "*",
  "param_columns": "ip"
}`;

const DEFAULT_UPDATE_API = `{
  "api_name": "search_by_ip",
  "table_name": "inventory_servers",
  "display_name": "IP 검색",
  "where_exp": "ip_address like '%{ip}%'",
  "select_exp": "*",
  "param_columns": "ip"
}`;

const INPUT =
  "mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 focus:border-sky-600 focus:outline-none";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function formatResult(payload: unknown): string {
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function parseJsonObject(raw: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(`${label} JSON 형식이 올바르지 않습니다.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label}은 객체 JSON이어야 합니다.`);
  }
  return parsed as Record<string, unknown>;
}

export function InventoryApiDebugModal({ viewerRole, onClose }: InventoryApiDebugModalProps) {
  const [baseUrl, setBaseUrl] = useState(FALLBACK_BASE_URL);
  const [endpointId, setEndpointId] = useState<EndpointId>("getInventoryList");
  const [filename, setFilename] = useState("");
  const [tablename, setTablename] = useState("");
  const [inventory, setInventory] = useState("");
  const [table, setTable] = useState("");
  const [columnname, setColumnname] = useState("");
  const [apiName, setApiName] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [authType, setAuthType] = useState("1");
  const [startrow, setStartrow] = useState("1");
  const [endrow, setEndrow] = useState("20");
  const [sql, setSql] = useState("SELECT 1");
  const [jsonBody, setJsonBody] = useState(DEFAULT_ADD_INVENTORY);
  const [result, setResult] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    void fetch("/api/debug/inventory-api/config")
      .then(async (response) => {
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as { base_url?: string };
        if (!cancelled && data.base_url) {
          setBaseUrl(data.base_url);
        }
      })
      .catch(() => {
        // keep default
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (endpointId === "transferJSON2Table") {
      setJsonBody(DEFAULT_TRANSFER_JSON);
    } else if (endpointId === "addInventory") {
      setJsonBody(DEFAULT_ADD_INVENTORY);
    } else if (endpointId === "addInventoryAPI") {
      setJsonBody(DEFAULT_ADD_API);
    } else if (endpointId === "updateInventoryAPI") {
      setJsonBody(DEFAULT_UPDATE_API);
    }
  }, [endpointId]);

  const selected = ENDPOINTS.find((item) => item.id === endpointId) ?? ENDPOINTS[0];

  const handleSend = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 실행할 수 있습니다.");
      return;
    }

    const trimmedBase = baseUrl.trim().replace(/\/+$/, "");
    if (!trimmedBase) {
      setError("Base URL을 입력하세요.");
      return;
    }

    setIsSending(true);
    setError(null);
    setResult("");

    try {
      let response: Response;
      if (endpointId === "uploadCSV") {
        const file = fileInputRef.current?.files?.[0];
        if (!file) {
          throw new Error("업로드할 CSV 파일을 선택하세요.");
        }
        const form = new FormData();
        form.append("file", file);
        const params = new URLSearchParams({ base_url: trimmedBase });
        response = await fetch(`/api/debug/inventory-api/uploadCSV?${params.toString()}`, {
          method: "POST",
          body: form,
        });
      } else if (endpointId === "transferCSV2Table") {
        if (!filename.trim() || !tablename.trim()) {
          throw new Error("filename과 tablename을 입력하세요.");
        }
        response = await fetch("/api/debug/inventory-api/transferCSV2Table", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: filename.trim(),
            tablename: tablename.trim(),
            base_url: trimmedBase,
          }),
        });
      } else if (endpointId === "retrieve") {
        if (!apiUrl.trim()) {
          throw new Error("api_url을 입력하세요.");
        }
        response = await fetch("/api/debug/inventory-api/retrieve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_url: apiUrl.trim(),
            api_key: apiKey.trim() || null,
            auth_type: Number(authType) || 1,
            base_url: trimmedBase,
          }),
        });
      } else if (endpointId === "testAPI") {
        if (!apiUrl.trim()) {
          throw new Error("url을 입력하세요.");
        }
        response = await fetch("/api/debug/inventory-api/testAPI", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: apiUrl.trim(),
            token: apiKey.trim() || null,
            auth_type: Number(authType) || 1,
            base_url: trimmedBase,
          }),
        });
      } else if (endpointId === "transferJSON2Table") {
        const body = parseJsonObject(jsonBody, "transferJSON2Table body");
        response = await fetch("/api/debug/inventory-api/transferJSON2Table", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, base_url: trimmedBase }),
        });
      } else if (endpointId === "addInventory") {
        const body = parseJsonObject(jsonBody, "addInventory body");
        response = await fetch("/api/debug/inventory-api/addInventory", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, base_url: trimmedBase }),
        });
      } else if (endpointId === "getInventoryList") {
        const params = new URLSearchParams({ base_url: trimmedBase });
        response = await fetch(`/api/debug/inventory-api/getInventoryList?${params.toString()}`);
      } else if (endpointId === "getInventorySchema") {
        if (!inventory.trim()) {
          throw new Error("inventory를 입력하세요.");
        }
        const params = new URLSearchParams({
          inventory: inventory.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/getInventorySchema?${params.toString()}`);
      } else if (endpointId === "getRecordsWithRows") {
        if (!table.trim()) {
          throw new Error("table을 입력하세요.");
        }
        const params = new URLSearchParams({
          table: table.trim(),
          startrow: String(Number(startrow) || 1),
          endrow: String(Number(endrow) || 1),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/getRecordsWithRows?${params.toString()}`);
      } else if (endpointId === "getCount") {
        if (!table.trim()) {
          throw new Error("table을 입력하세요.");
        }
        const params = new URLSearchParams({
          table: table.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/getCount?${params.toString()}`);
      } else if (endpointId === "getAllDataInColumn") {
        if (!tablename.trim() || !columnname.trim()) {
          throw new Error("tablename과 columnname을 입력하세요.");
        }
        const params = new URLSearchParams({
          tablename: tablename.trim(),
          columnname: columnname.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/getAllDataInColumn?${params.toString()}`);
      } else if (endpointId === "removeInventory") {
        if (!table.trim()) {
          throw new Error("table을 입력하세요.");
        }
        const params = new URLSearchParams({
          table: table.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/removeInventory?${params.toString()}`, {
          method: "POST",
        });
      } else if (endpointId === "removeTempTable") {
        if (!tablename.trim()) {
          throw new Error("tablename을 입력하세요.");
        }
        const params = new URLSearchParams({
          tablename: tablename.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/removeTempTable?${params.toString()}`, {
          method: "POST",
        });
      } else if (endpointId === "getInventoryAPIList") {
        if (!tablename.trim()) {
          throw new Error("tablename을 입력하세요.");
        }
        const params = new URLSearchParams({
          tablename: tablename.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/getInventoryAPIList?${params.toString()}`);
      } else if (endpointId === "addInventoryAPI") {
        const body = parseJsonObject(jsonBody, "addInventoryAPI body");
        response = await fetch("/api/debug/inventory-api/addInventoryAPI", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, base_url: trimmedBase }),
        });
      } else if (endpointId === "updateInventoryAPI") {
        const body = parseJsonObject(jsonBody, "updateInventoryAPI body");
        response = await fetch("/api/debug/inventory-api/updateInventoryAPI", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, base_url: trimmedBase }),
        });
      } else if (endpointId === "removeInventoryAPI") {
        if (!tablename.trim() || !apiName.trim()) {
          throw new Error("tablename과 api_name을 입력하세요.");
        }
        const params = new URLSearchParams({
          tablename: tablename.trim(),
          api_name: apiName.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/removeInventoryAPI?${params.toString()}`, {
          method: "POST",
        });
      } else if (endpointId === "reloadAPI") {
        if (!tablename.trim()) {
          throw new Error("tablename을 입력하세요.");
        }
        const params = new URLSearchParams({
          tablename: tablename.trim(),
          base_url: trimmedBase,
        });
        response = await fetch(`/api/debug/inventory-api/reloadAPI?${params.toString()}`, {
          method: "POST",
        });
      } else {
        if (!sql.trim()) {
          throw new Error("sql을 입력하세요.");
        }
        response = await fetch("/api/debug/inventory-api/sql", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sql: sql.trim(), base_url: trimmedBase }),
        });
      }

      if (!response.ok) {
        throw new Error(await parseError(response, "인벤토리 API 호출에 실패했습니다."));
      }
      const data = await response.json();
      setResult(formatResult(data));
      if (data && typeof data === "object" && "ok" in data && data.ok === false) {
        setError(typeof data.error === "string" ? data.error : "원격 API가 오류를 반환했습니다.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "인벤토리 API 호출에 실패했습니다.");
    } finally {
      setIsSending(false);
    }
  };

  const showJsonBody =
    endpointId === "transferJSON2Table" ||
    endpointId === "addInventory" ||
    endpointId === "addInventoryAPI" ||
    endpointId === "updateInventoryAPI";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="inventory-api-debug-title"
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 id="inventory-api-debug-title" className="text-lg font-semibold text-slate-100">
              인벤토리 정보조회(디버깅)
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              project-e inventory-api 엔드포인트를 선택해 요청을 보내고 응답을 확인합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <label className="mt-4 block text-sm font-medium text-slate-200" htmlFor="inventory-api-base-url">
          Base URL
        </label>
        <div className="mt-1 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setBaseUrl(MOCK_BASE_URL)}
            className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            목업
          </button>
          <button
            type="button"
            onClick={() => setBaseUrl(HTTP_BASE_URL)}
            className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            http 모드
          </button>
        </div>
        <input
          id="inventory-api-base-url"
          type="text"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          className={INPUT}
          placeholder={FALLBACK_BASE_URL}
        />

        <div className="mt-4 max-h-28 overflow-y-auto">
          <div className="flex flex-wrap gap-2">
            {ENDPOINTS.map((item) => {
              const active = item.id === endpointId;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setEndpointId(item.id)}
                  title={item.label}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                    active
                      ? "border-sky-500 bg-sky-950/50 text-sky-100"
                      : "border-slate-700 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {item.method} {item.path}
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950/40 p-4">
          <p className="mb-3 font-mono text-xs text-slate-400">
            {selected.method} {baseUrl.replace(/\/+$/, "")}
            {selected.path}
            <span className="ml-2 text-slate-500">({selected.label})</span>
          </p>

          {endpointId === "uploadCSV" ? (
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border file:border-slate-600 file:bg-slate-800 file:px-3 file:py-1.5 file:text-slate-100"
            />
          ) : null}

          {endpointId === "transferCSV2Table" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-sm text-slate-300">
                filename
                <input
                  type="text"
                  value={filename}
                  onChange={(event) => setFilename(event.target.value)}
                  className={INPUT}
                  placeholder="servers_abc123.csv"
                />
              </label>
              <label className="block text-sm text-slate-300">
                tablename
                <input
                  type="text"
                  value={tablename}
                  onChange={(event) => setTablename(event.target.value)}
                  className={INPUT}
                  placeholder="inventory_servers"
                />
              </label>
            </div>
          ) : null}

          {endpointId === "retrieve" || endpointId === "testAPI" ? (
            <div className="grid gap-3 md:grid-cols-3">
              <label className="block text-sm text-slate-300 md:col-span-2">
                {endpointId === "retrieve" ? "api_url" : "url"}
                <input
                  type="text"
                  value={apiUrl}
                  onChange={(event) => setApiUrl(event.target.value)}
                  className={INPUT}
                  placeholder="https://example.com/api/data"
                />
              </label>
              <label className="block text-sm text-slate-300">
                auth_type
                <select
                  value={authType}
                  onChange={(event) => setAuthType(event.target.value)}
                  className={INPUT}
                >
                  <option value="1">1 bearer</option>
                  <option value="2">2 header</option>
                </select>
              </label>
              <label className="block text-sm text-slate-300 md:col-span-3">
                {endpointId === "retrieve" ? "api_key (optional)" : "token (optional)"}
                <input
                  type="text"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  className={INPUT}
                />
              </label>
            </div>
          ) : null}

          {showJsonBody ? (
            <label className="block text-sm text-slate-300">
              JSON body
              <textarea
                value={jsonBody}
                onChange={(event) => setJsonBody(event.target.value)}
                rows={8}
                className={`${INPUT} resize-y`}
              />
            </label>
          ) : null}

          {endpointId === "getInventorySchema" ? (
            <label className="block text-sm text-slate-300">
              inventory
              <input
                type="text"
                value={inventory}
                onChange={(event) => setInventory(event.target.value)}
                className={INPUT}
                placeholder="inventory_servers"
              />
            </label>
          ) : null}

          {endpointId === "getRecordsWithRows" ? (
            <div className="grid gap-3 md:grid-cols-3">
              <label className="block text-sm text-slate-300">
                table
                <input
                  type="text"
                  value={table}
                  onChange={(event) => setTable(event.target.value)}
                  className={INPUT}
                />
              </label>
              <label className="block text-sm text-slate-300">
                startrow (1부터)
                <input
                  type="number"
                  min={1}
                  value={startrow}
                  onChange={(event) => setStartrow(event.target.value)}
                  className={INPUT}
                />
              </label>
              <label className="block text-sm text-slate-300">
                endrow (포함)
                <input
                  type="number"
                  min={1}
                  value={endrow}
                  onChange={(event) => setEndrow(event.target.value)}
                  className={INPUT}
                />
              </label>
            </div>
          ) : null}

          {endpointId === "getCount" || endpointId === "removeInventory" ? (
            <label className="block text-sm text-slate-300">
              table
              <input
                type="text"
                value={table}
                onChange={(event) => setTable(event.target.value)}
                className={INPUT}
                placeholder="inventory_servers"
              />
            </label>
          ) : null}

          {endpointId === "getAllDataInColumn" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-sm text-slate-300">
                tablename
                <input
                  type="text"
                  value={tablename}
                  onChange={(event) => setTablename(event.target.value)}
                  className={INPUT}
                />
              </label>
              <label className="block text-sm text-slate-300">
                columnname
                <input
                  type="text"
                  value={columnname}
                  onChange={(event) => setColumnname(event.target.value)}
                  className={INPUT}
                />
              </label>
            </div>
          ) : null}

          {endpointId === "removeTempTable" ||
          endpointId === "getInventoryAPIList" ||
          endpointId === "reloadAPI" ? (
            <label className="block text-sm text-slate-300">
              tablename
              <input
                type="text"
                value={tablename}
                onChange={(event) => setTablename(event.target.value)}
                className={INPUT}
                placeholder="inventory_servers"
              />
            </label>
          ) : null}

          {endpointId === "removeInventoryAPI" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-sm text-slate-300">
                tablename
                <input
                  type="text"
                  value={tablename}
                  onChange={(event) => setTablename(event.target.value)}
                  className={INPUT}
                />
              </label>
              <label className="block text-sm text-slate-300">
                api_name
                <input
                  type="text"
                  value={apiName}
                  onChange={(event) => setApiName(event.target.value)}
                  className={INPUT}
                />
              </label>
            </div>
          ) : null}

          {endpointId === "sql" ? (
            <label className="block text-sm text-slate-300">
              sql
              <textarea
                value={sql}
                onChange={(event) => setSql(event.target.value)}
                rows={4}
                className={`${INPUT} resize-y`}
              />
            </label>
          ) : null}

          {endpointId === "getInventoryList" ? (
            <p className="text-sm text-slate-500">추가 파라미터가 없습니다. 실행을 누르면 목록을 조회합니다.</p>
          ) : null}

          <div className="mt-4">
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={isSending}
              className="rounded-md border border-sky-700 bg-sky-950/40 px-4 py-2 text-sm text-sky-100 hover:bg-sky-900/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSending ? "실행 중…" : "실행"}
            </button>
          </div>
        </div>

        {error ? (
          <p className="mt-3 text-sm text-rose-300" role="alert">
            {error}
          </p>
        ) : null}

        <label className="mt-3 block text-sm font-medium text-slate-200" htmlFor="inventory-api-debug-result">
          응답
        </label>
        <textarea
          id="inventory-api-debug-result"
          readOnly
          value={result}
          rows={14}
          className="mt-1 min-h-0 w-full flex-1 resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs leading-relaxed text-slate-200"
          placeholder="실행 결과가 여기에 표시됩니다."
        />
      </div>
    </div>
  );
}
