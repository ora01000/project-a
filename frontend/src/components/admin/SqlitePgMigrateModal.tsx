import { useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface SqlitePgMigrateModalProps {
  viewerRole: number;
  onClose: () => void;
}

interface MigrateResponse {
  ok: boolean;
  dry_run: boolean;
  migratable_rows: number;
  migrated_rows: number;
  mynote_files: number;
  log: string;
  error?: string | null;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string | { msg?: string }[] } | null;
  if (!payload?.detail) {
    return fallback;
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => item.msg ?? JSON.stringify(item)).join(", ");
  }
  return fallback;
}

export function SqlitePgMigrateModal({ viewerRole, onClose }: SqlitePgMigrateModalProps) {
  const [databaseUrl, setDatabaseUrl] = useState("");
  const [execute, setExecute] = useState(false);
  const [truncateTarget, setTruncateTarget] = useState(true);
  const [applySchema, setApplySchema] = useState(true);
  const [importMynoteFiles, setImportMynoteFiles] = useState(true);
  const [includeInventory, setIncludeInventory] = useState(true);
  const [result, setResult] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const handleRun = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자(role 0|100)만 실행할 수 있습니다.");
      return;
    }

    const trimmed = databaseUrl.trim();
    if (!trimmed) {
      setError("PostgreSQL 접속 문자열을 입력해 주세요.");
      return;
    }

    if (execute) {
      const confirmed = window.confirm(
        "대상 PostgreSQL에 실제로 데이터를 기록합니다.\n계속하시겠습니까?",
      );
      if (!confirmed) {
        return;
      }
    }

    setIsRunning(true);
    setError(null);
    setResult("");
    try {
      const response = await fetch("/api/admin/migrate-sqlite-to-postgres", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          database_url: trimmed,
          execute,
          truncate_target: truncateTarget,
          apply_schema: applySchema,
          import_mynote_files: importMynoteFiles,
          include_inventory: includeInventory,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "마이그레이션에 실패했습니다."));
      }
      const data = (await response.json()) as MigrateResponse;
      const summary = [
        data.ok ? (data.dry_run ? "[dry-run]" : "[execute]") : "[failed]",
        data.error ? `error=${data.error}` : null,
        `migratable_rows=${data.migratable_rows}`,
        `migrated_rows=${data.migrated_rows}`,
        `mynote_files=${data.mynote_files}`,
        "",
        data.log,
      ]
        .filter((line) => line != null)
        .join("\n");
      setResult(summary);
      if (!data.ok) {
        setError(data.error || "마이그레이션에 실패했습니다.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "마이그레이션에 실패했습니다.");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sqlite-pg-migrate-dialog-title"
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="sqlite-pg-migrate-dialog-title" className="text-lg font-semibold text-slate-100">
            SQLite → PostgreSQL 마이그레이션
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <p className="mt-2 text-sm text-slate-400">
          로컬 SQLite(<code className="text-slate-300">data/app.db</code>) 데이터를 입력한 PostgreSQL로
          이관합니다. 기본은 계획만 조회(dry-run)이며, 실제 기록은 &quot;실행(쓰기)&quot;을 켜야 합니다.
        </p>

        <label className="mt-4 block text-sm font-medium text-slate-200" htmlFor="pg-database-url">
          PostgreSQL 접속 문자열
        </label>
        <input
          id="pg-database-url"
          type="text"
          value={databaseUrl}
          onChange={(event) => setDatabaseUrl(event.target.value)}
          placeholder="postgresql://user:pass@host:port/dbname"
          className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-600 focus:outline-none"
        />

        <div className="mt-4 grid gap-2 text-sm text-slate-200 sm:grid-cols-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={execute}
              onChange={(event) => setExecute(event.target.checked)}
            />
            실행(쓰기) — 미체크 시 dry-run
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={truncateTarget}
              onChange={(event) => setTruncateTarget(event.target.checked)}
            />
            대상 테이블 TRUNCATE
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={applySchema}
              onChange={(event) => setApplySchema(event.target.checked)}
            />
            코어 스키마 적용
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={importMynoteFiles}
              onChange={(event) => setImportMynoteFiles(event.target.checked)}
            />
            mynote 파일 → mynote_contents
          </label>
          <label className="flex items-center gap-2 sm:col-span-2">
            <input
              type="checkbox"
              checked={includeInventory}
              onChange={(event) => setIncludeInventory(event.target.checked)}
            />
            inventory 테이블 포함 (k8s / kubevirt)
          </label>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={isRunning}
            className="rounded-md border border-sky-700 bg-sky-950/40 px-4 py-2 text-sm text-sky-100 hover:bg-sky-900/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRunning ? "실행 중…" : execute ? "마이그레이션 실행" : "계획 조회 (dry-run)"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

        <label className="mt-5 block text-sm font-medium text-slate-200" htmlFor="migrate-result">
          결과
        </label>
        <textarea
          id="migrate-result"
          value={result}
          readOnly
          rows={14}
          placeholder={isRunning ? "처리 중…" : "실행 후 로그가 여기에 표시됩니다."}
          className="mt-2 w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none"
        />
      </div>
    </div>
  );
}
