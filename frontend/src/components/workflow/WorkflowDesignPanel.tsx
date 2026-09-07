import { useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { WorkNodeItem, WorkflowItem } from "../../types/workflow";
import { WorkflowEditor } from "./WorkflowEditor";

interface WorkflowDesignPanelProps {
  mode: "idle" | "create" | "edit";
  selected: WorkflowItem | null;
  workNodes: WorkNodeItem[];
  user: AuthUser;
  editorKey: string;
  onSaved: (item: WorkflowItem) => Promise<void> | void;
  onWorkNodesChanged: () => Promise<void> | void;
  onCheckedIn: (item: WorkflowItem) => Promise<void> | void;
  onCheckedOut: (item: WorkflowItem) => Promise<void> | void;
  onRestored: (item: WorkflowItem) => Promise<void> | void;
  aiImportRequest?: { nonce: number; assistantText: string } | null;
  onAiImportHandled?: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function hasActiveCheckin(item: WorkflowItem | null): boolean {
  return Boolean(item && (item.checkin_user ?? 0) > 0);
}

function isMyCheckin(item: WorkflowItem | null, user: AuthUser): boolean {
  return Boolean(item && (item.checkin_user ?? 0) === user.idx);
}

export function WorkflowDesignPanel({
  mode,
  selected,
  workNodes,
  user,
  editorKey,
  onSaved,
  onWorkNodesChanged,
  onCheckedIn,
  onCheckedOut,
  onRestored,
  aiImportRequest = null,
  onAiImportHandled,
}: WorkflowDesignPanelProps) {
  const [lockError, setLockError] = useState<string | null>(null);
  const [isLockBusy, setIsLockBusy] = useState(false);

  if (mode === "idle") {
    return (
      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner">
        <div className="flex h-full items-center justify-center text-sm text-slate-500">
          워크플로우를 선택하거나 새로 만드세요.
        </div>
      </section>
    );
  }

  if (mode === "create" || (mode === "edit" && selected)) {
    const checkedIn = hasActiveCheckin(selected);
    const mine = isMyCheckin(selected, user);
    const readOnly = mode === "edit" ? !(checkedIn && mine) : false;
    const showCheckinButton = mode === "edit" && !checkedIn;
    const showCheckoutButton = mode === "edit" && checkedIn && mine;
    const checkedInByOther = mode === "edit" && checkedIn && !mine;
    const draftHint =
      mode === "edit" && checkedIn && mine
        ? selected?.draft_dirty
          ? "드래프트 저장됨 · 체크아웃 시 DB 반영"
          : "체크인됨 · 저장은 Redis 드래프트에만 기록"
        : null;

    const runLockAction = async (
      path: "checkin" | "checkout" | "restore",
      onDone: (item: WorkflowItem) => Promise<void> | void,
      failMessage: string,
    ) => {
      if (!selected) {
        return;
      }
      setIsLockBusy(true);
      setLockError(null);
      try {
        const response = await fetch(`/api/workflows/${selected.uuid}/${path}`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(await parseError(response, failMessage));
        }
        const item = (await response.json()) as WorkflowItem;
        await onDone(item);
      } catch (err) {
        setLockError(err instanceof Error ? err.message : failMessage);
      } finally {
        setIsLockBusy(false);
      }
    };

    return (
      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-700/80 px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-slate-200">
              {mode === "create" ? "새로운 워크플로우" : selected?.workflow_name ?? "워크플로우 편집"}
            </h2>
            {mode === "edit" && readOnly ? (
              <p className="mt-0.5 text-[11px] text-slate-500">
                {checkedInByOther
                  ? `읽기 모드 · ${(selected?.checkin_username || "다른 사용자").trim()} 체크인 중`
                  : "읽기 모드 · 편집하려면 체크인하세요"}
              </p>
            ) : null}
            {draftHint ? <p className="mt-0.5 text-[11px] text-amber-200/90">{draftHint}</p> : null}
            {lockError ? <p className="mt-0.5 text-[11px] text-rose-300">{lockError}</p> : null}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {showCheckinButton ? (
              <button
                type="button"
                disabled={isLockBusy}
                onClick={() => {
                  void runLockAction("checkin", onCheckedIn, "체크인에 실패했습니다.");
                }}
                className="rounded-md border border-sky-700 bg-sky-950/50 px-3 py-1.5 text-sm font-medium text-sky-100 hover:bg-sky-900/60 disabled:opacity-50"
              >
                {isLockBusy ? "처리 중…" : "체크인"}
              </button>
            ) : null}
            {showCheckoutButton ? (
              <>
                <button
                  type="button"
                  disabled={isLockBusy}
                  onClick={() => {
                    void runLockAction("restore", onRestored, "원복에 실패했습니다.");
                  }}
                  className="rounded-md border border-amber-700/80 bg-amber-950/40 px-3 py-1.5 text-sm font-medium text-amber-100 hover:bg-amber-900/50 disabled:opacity-50"
                >
                  원복
                </button>
                <button
                  type="button"
                  disabled={isLockBusy}
                  onClick={() => {
                    void runLockAction("checkout", onCheckedOut, "체크아웃에 실패했습니다.");
                  }}
                  className="rounded-md border border-slate-600 bg-slate-900/70 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                >
                  체크아웃
                </button>
              </>
            ) : null}
          </div>
        </header>
        <WorkflowEditor
          key={editorKey}
          user={user}
          workNodes={workNodes}
          initialName={mode === "edit" ? selected?.workflow_name ?? "" : ""}
          initialExpression={mode === "edit" ? selected?.workflow ?? "" : ""}
          initialDescription={mode === "edit" ? selected?.workflow_description ?? "" : ""}
          workflowUuid={mode === "edit" ? selected?.uuid : undefined}
          saveLabel="저장"
          readOnly={readOnly}
          onSaved={onSaved}
          onWorkNodesChanged={onWorkNodesChanged}
          aiImportRequest={aiImportRequest}
          onAiImportHandled={onAiImportHandled}
        />
      </section>
    );
  }

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner">
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        워크플로우를 선택하거나 새로 만드세요.
      </div>
    </section>
  );
}
