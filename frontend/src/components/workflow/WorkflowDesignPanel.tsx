import { useMemo, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { WorkNodeItem, WorkflowItem } from "../../types/workflow";
import { WorkflowDiagram } from "./WorkflowDiagram";
import { WorkflowEditor } from "./WorkflowEditor";
import { isRunInProgress } from "./workflowModel";

interface WorkflowDesignPanelProps {
  mode: "idle" | "create" | "edit";
  selected: WorkflowItem | null;
  workNodes: WorkNodeItem[];
  user: AuthUser;
  editorKey: string;
  onSaved: (item: WorkflowItem) => Promise<void> | void;
  onWorkNodesChanged: () => Promise<void> | void;
  onDistributed: (item: WorkflowItem) => Promise<void> | void;
  onCloned: (item: WorkflowItem) => Promise<void> | void;
  aiImportRequest?: { nonce: number; assistantText: string } | null;
  onAiImportHandled?: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

export function WorkflowDesignPanel({
  mode,
  selected,
  workNodes,
  user,
  editorKey,
  onSaved,
  onWorkNodesChanged,
  onDistributed,
  onCloned,
  aiImportRequest = null,
  onAiImportHandled,
}: WorkflowDesignPanelProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const workRunDates = useMemo(() => {
    const map: Record<string, { last_start_date?: string; last_end_date?: string }> = {};
    for (const node of workNodes) {
      map[node.uuid] = {
        last_start_date: node.last_start_date,
        last_end_date: node.last_end_date,
      };
    }
    return map;
  }, [workNodes]);

  const diagramHasRunning = useMemo(
    () =>
      Boolean(selected?.awaiting_approval) ||
      Boolean(
        selected?.graph?.nodes.some((node) => {
          if (!node.work_uuid) {
            return false;
          }
          const dates = workRunDates[node.work_uuid];
          return isRunInProgress(dates?.last_start_date, dates?.last_end_date);
        }),
      ),
    [selected?.awaiting_approval, selected?.graph, workRunDates],
  );

  if (mode === "idle") {
    return (
      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner">
        <div className="flex h-full items-center justify-center text-sm text-slate-500">
          작업 워크플로우를 선택하거나 새로 만드세요.
        </div>
      </section>
    );
  }

  if (mode === "create" || (mode === "edit" && selected)) {
    const canEdit = mode === "create" || Boolean(selected?.can_edit);
    const isOwner = mode === "edit" && (selected?.owner ?? 0) === user.idx;
    const isDistributed = Boolean(selected?.distribute);
    const ownerLabel = (selected?.owner_username || "").trim() || "소유자";

    const handleDistribute = async (next: boolean) => {
      if (!selected) {
        return;
      }
      const confirmed = window.confirm(
        next
          ? `"${selected.workflow_name}" 작업 워크플로우를 배포하시겠습니까?\n다른 사용자가 조회·실행·복제할 수 있습니다.`
          : `"${selected.workflow_name}" 배포를 취소하시겠습니까?`,
      );
      if (!confirmed) {
        return;
      }
      setIsBusy(true);
      setActionError(null);
      try {
        const response = await fetch(`/api/workflows/${selected.uuid}/distribute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ distribute: next }),
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "배포 상태 변경에 실패했습니다."));
        }
        const item = (await response.json()) as WorkflowItem;
        await onDistributed(item);
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "배포 상태 변경에 실패했습니다.");
      } finally {
        setIsBusy(false);
      }
    };

    const handleClone = async () => {
      if (!selected) {
        return;
      }
      const confirmed = window.confirm(
        `"${selected.workflow_name}" 작업 워크플로우를 복제하시겠습니까?\n하위 작업노드도 함께 복제됩니다.`,
      );
      if (!confirmed) {
        return;
      }
      setIsBusy(true);
      setActionError(null);
      try {
        const response = await fetch(`/api/workflows/${selected.uuid}/clone`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "복제에 실패했습니다."));
        }
        const item = (await response.json()) as WorkflowItem;
        await onCloned(item);
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "복제에 실패했습니다.");
      } finally {
        setIsBusy(false);
      }
    };

    return (
      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-700/80 px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-slate-200">
              {mode === "create" ? "새로운 작업 워크플로우" : selected?.workflow_name ?? "작업 워크플로우 편집"}
            </h2>
            {mode === "edit" ? (
              <p className="mt-0.5 text-[11px] text-slate-500">
                {canEdit
                  ? `소유자 · ${ownerLabel}${isDistributed ? " · 배포됨" : " · 미배포"}`
                  : `읽기 모드 · ${ownerLabel} 소유${isDistributed ? " · 배포됨" : ""}`}
              </p>
            ) : null}
            {actionError ? <p className="mt-0.5 text-[11px] text-rose-300">{actionError}</p> : null}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {mode === "edit" && isOwner ? (
              <button
                type="button"
                disabled={isBusy}
                onClick={() => {
                  void handleDistribute(!isDistributed);
                }}
                className={`rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${
                  isDistributed
                    ? "border-amber-700/80 bg-amber-950/40 text-amber-100 hover:bg-amber-900/50"
                    : "border-sky-700 bg-sky-950/50 text-sky-100 hover:bg-sky-900/60"
                }`}
              >
                {isBusy ? "처리 중…" : isDistributed ? "배포 취소" : "배포"}
              </button>
            ) : null}
            {mode === "edit" && selected ? (
              <button
                type="button"
                disabled={isBusy}
                onClick={() => {
                  void handleClone();
                }}
                className="rounded-md border border-slate-600 bg-slate-900/70 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50"
              >
                복제
              </button>
            ) : null}
          </div>
        </header>
        {mode === "edit" && selected?.graph && selected.graph.nodes.length > 0 ? (
          <div
            className={`shrink-0 border-b border-slate-700/80 px-3 py-2 ${
              diagramHasRunning ? "bg-rose-950/20" : "bg-slate-950/40"
            }`}
            style={{ height: 148 }}
          >
            <WorkflowDiagram
              graph={selected.graph}
              workRunDates={workRunDates}
              awaitingHitlNodeId={selected.awaiting_hitl_node_id || null}
            />
          </div>
        ) : null}
        <WorkflowEditor
          key={editorKey}
          user={user}
          workNodes={workNodes}
          awaitingHitlUserid={selected?.awaiting_hitl_userid || ""}
          initialName={mode === "edit" ? selected?.workflow_name ?? "" : ""}
          initialExpression={mode === "edit" ? selected?.workflow ?? "" : ""}
          initialDescription={mode === "edit" ? selected?.workflow_description ?? "" : ""}
          workflowUuid={mode === "edit" ? selected?.uuid : undefined}
          saveLabel="저장"
          readOnly={!canEdit}
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
        작업 워크플로우를 선택하거나 새로 만드세요.
      </div>
    </section>
  );
}
