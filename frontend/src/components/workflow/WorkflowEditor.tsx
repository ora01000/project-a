import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";

const DEFAULT_EDIT_PANEL_RATIO = 0.5;
const MIN_EDIT_PANEL_HEIGHT = 140;
const MIN_CANVAS_HEIGHT = 160;
const EDIT_RESIZE_HANDLE_HEIGHT = 8;

import type { AuthUser } from "../../types/auth";
import type { AgentRuntimeRecord } from "../../types/agentruntime";
import { assignableAgentId } from "../../types/agentruntime";
import type { WorkNodeItem, WorkflowApprover, WorkflowItem } from "../../types/workflow";
import { WorkNodeEditPanel } from "./WorkNodeEditPanel";
import { WorkflowHistoryPanel } from "./WorkflowHistoryPanel";
import {
  parseAiWorkflowDesignResponse,
} from "./aiWorkflowParse";
import {
  emptyEditorModel,
  hydrateEditor,
  insertAfter,
  nextClientId,
  removeNode,
  serializeEditor,
  setFailWork,
  terminateAfter,
  updateWork,
  validateEditor,
  workNodeFromItem,
  workFieldsFromItem,
  workNodeWriteBody,
  isRunInProgress,
  type EditorModel,
  type WorkEditorNode,
} from "./workflowModel";

interface WorkflowEditorProps {
  user: AuthUser;
  workNodes: WorkNodeItem[];
  initialName: string;
  initialExpression: string;
  initialDescription?: string;
  saveLabel: string;
  readOnly?: boolean;
  onSaved: (item: WorkflowItem) => Promise<void> | void;
  onWorkNodesChanged: () => Promise<void> | void;
  workflowUuid?: string;
  awaitingHitlUserid?: string;
  aiImportRequest?: { nonce: number; assistantText: string } | null;
  onAiImportHandled?: () => void;
}

type BalloonField = "approver";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function PlusCircle({
  onClick,
  label,
}: {
  onClick: (event: ReactMouseEvent<HTMLButtonElement>) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-sky-400 bg-slate-900 text-lg leading-none text-sky-200 hover:bg-sky-950"
    >
      +
    </button>
  );
}

function FlowArrow() {
  return (
    <svg viewBox="0 0 28 12" className="h-3 w-7 shrink-0 text-slate-400" aria-hidden="true">
      <path d="M1 6 H20" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M18 1.5 L26 6 L18 10.5 Z" fill="currentColor" />
    </svg>
  );
}

function FlowDownArrow({ tone = "fail" }: { tone?: "fail" | "report" }) {
  const colorClass = tone === "report" ? "text-emerald-400" : "text-rose-400";
  const dashed = tone === "fail";
  return (
    <svg viewBox="0 0 12 28" className={`h-7 w-3 shrink-0 ${colorClass}`} aria-hidden="true">
      <path
        d="M6 1 V20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray={dashed ? "3 2" : undefined}
      />
      <path d="M1.5 18 L6 26 L10.5 18 Z" fill="currentColor" />
    </svg>
  );
}

function MailReportBadge() {
  return (
    <div
      className="flex h-10 min-w-10 items-center justify-center rounded-full border border-emerald-400 bg-slate-950 px-2 text-[10px] font-semibold text-emerald-100"
      title="작업 완료 후 결과 메일 전송"
    >
      메일전송
    </div>
  );
}

function DeleteBox({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title="삭제"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="absolute right-1 top-1 z-10 flex h-5 w-5 items-center justify-center rounded-sm bg-transparent text-[11px] font-semibold leading-none text-slate-300 hover:bg-rose-950/60 hover:text-rose-200"
    >
      X
    </button>
  );
}

function HamburgerIcon() {
  return (
    <svg viewBox="0 0 14 14" className="h-3.5 w-3.5" aria-hidden="true" fill="currentColor">
      <rect x="2" y="3" width="10" height="1.5" rx="0.5" />
      <rect x="2" y="6.25" width="10" height="1.5" rx="0.5" />
      <rect x="2" y="9.5" width="10" height="1.5" rx="0.5" />
    </svg>
  );
}

function TextLabelChip({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span
      title={title || undefined}
      className="inline-block max-w-full truncate rounded-full border border-slate-600 bg-slate-900/80 px-2.5 py-1 text-left text-[11px] font-medium text-slate-200"
    >
      {children}
    </span>
  );
}

function Balloon({ children }: { children: ReactNode }) {
  return (
    <div className="absolute left-0 top-7 z-30 w-56 rounded-md border border-slate-600 bg-slate-800 p-2 shadow-xl">
      <div className="absolute -top-1.5 left-4 h-3 w-3 rotate-45 border-l border-t border-slate-600 bg-slate-800" />
      <div className="relative">{children}</div>
    </div>
  );
}

export function WorkflowEditor({
  user,
  workNodes,
  initialName,
  initialExpression,
  initialDescription = "",
  saveLabel,
  readOnly = false,
  onSaved,
  onWorkNodesChanged,
  workflowUuid,
  awaitingHitlUserid = "",
  aiImportRequest = null,
  onAiImportHandled,
}: WorkflowEditorProps) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const processedAiImportNonceRef = useRef<number | null>(null);
  const [model, setModel] = useState<EditorModel>(() => emptyEditorModel());
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [runtimes, setRuntimes] = useState<AgentRuntimeRecord[]>([]);
  const [approvers, setApprovers] = useState<WorkflowApprover[]>([]);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [openBalloon, setOpenBalloon] = useState<{ clientId: string; field: BalloonField } | null>(
    null,
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [bottomTab, setBottomTab] = useState<"edit" | "results">("results");
  const [editPanelHeight, setEditPanelHeight] = useState<number | null>(null);
  const workflowCanvasRef = useRef<HTMLDivElement>(null);
  const editPanelRef = useRef<HTMLElement>(null);
  const splitLayoutRef = useRef<HTMLDivElement>(null);
  const isResizingEditPanelRef = useRef(false);
  const resizeStartYRef = useRef(0);
  const resizeStartHeightRef = useRef(0);

  const selectedWorkNode = useMemo(() => {
    if (!selectedNodeId) {
      return null;
    }
    if (model.extras[selectedNodeId]) {
      return model.extras[selectedNodeId];
    }
    const step = model.main.find((item) => item.clientId === selectedNodeId);
    return step?.type === "work" ? step : null;
  }, [model, selectedNodeId]);

  const clampEditPanelHeight = useCallback((nextHeight: number) => {
    const containerHeight = splitLayoutRef.current?.clientHeight ?? 0;
    if (containerHeight <= 0) {
      return nextHeight;
    }
    const maxHeight = Math.max(
      MIN_EDIT_PANEL_HEIGHT,
      containerHeight - MIN_CANVAS_HEIGHT - EDIT_RESIZE_HANDLE_HEIGHT,
    );
    return Math.min(maxHeight, Math.max(MIN_EDIT_PANEL_HEIGHT, nextHeight));
  }, []);

  const resolveDefaultEditPanelHeight = useCallback(() => {
    const containerHeight = splitLayoutRef.current?.clientHeight ?? 0;
    if (containerHeight <= 0) {
      return MIN_EDIT_PANEL_HEIGHT;
    }
    return clampEditPanelHeight(Math.round(containerHeight * DEFAULT_EDIT_PANEL_RATIO));
  }, [clampEditPanelHeight]);

  useEffect(() => {
    if (!selectedWorkNode) {
      return;
    }
    setEditPanelHeight((current) =>
      current == null ? resolveDefaultEditPanelHeight() : clampEditPanelHeight(current),
    );
  }, [selectedWorkNode, clampEditPanelHeight, resolveDefaultEditPanelHeight]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isResizingEditPanelRef.current) {
        return;
      }
      const deltaY = resizeStartYRef.current - event.clientY;
      setEditPanelHeight(clampEditPanelHeight(resizeStartHeightRef.current + deltaY));
    };
    const handleMouseUp = () => {
      if (!isResizingEditPanelRef.current) {
        return;
      }
      isResizingEditPanelRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [clampEditPanelHeight]);

  useEffect(() => {
    const node = splitLayoutRef.current;
    if (!node || !selectedWorkNode) {
      return;
    }
    const onLayoutResize = () => {
      setEditPanelHeight((current) =>
        clampEditPanelHeight(current ?? resolveDefaultEditPanelHeight()),
      );
    };
    const observer = new ResizeObserver(() => {
      window.requestAnimationFrame(onLayoutResize);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [selectedWorkNode, clampEditPanelHeight, resolveDefaultEditPanelHeight]);

  const handleEditPanelResizeStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const currentHeight = editPanelHeight ?? resolveDefaultEditPanelHeight();
    isResizingEditPanelRef.current = true;
    resizeStartYRef.current = event.clientY;
    resizeStartHeightRef.current = currentHeight;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  };

  const assignedAgents = useMemo(() => {
    const assigned = new Set((user.agent_ids ?? []).map((id) => id.trim()).filter(Boolean));
    if (assigned.size === 0) {
      return [];
    }
    return runtimes.filter((record) => {
      const assignable = assignableAgentId(record);
      return (
        assigned.has(assignable) ||
        assigned.has(record.agent_id) ||
        assigned.has(record.local_agent_id) ||
        assigned.has(String(record.idx))
      );
    });
  }, [runtimes, user.agent_ids]);

  const userNames = useMemo(() => {
    const mapping: Record<string, string> = {};
    for (const item of approvers) {
      mapping[item.userid] = item.username || item.userid;
    }
    return mapping;
  }, [approvers]);

  useEffect(() => {
    try {
      setModel(hydrateEditor(initialExpression, workNodes, userNames));
      setSelectedNodeId(null);
      setError(null);
    } catch (err) {
      setModel(emptyEditorModel());
      setSelectedNodeId(null);
      setError(err instanceof Error ? err.message : "워크플로우 표현식을 읽지 못했습니다.");
    }
    // 노드 목록 갱신으로 편집중 그래프가 초기화되지 않도록 workNodes는 의존성에서 제외한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialExpression, workflowUuid]);

  useEffect(() => {
    setModel((current) => ({
      ...current,
      main: current.main.map((step) =>
        step.type === "hitl" && userNames[step.userid]
          ? { ...step, username: userNames[step.userid] }
          : step,
      ),
    }));
  }, [userNames]);

  useEffect(() => {
    setName(initialName);
  }, [initialName]);

  useEffect(() => {
    setDescription(initialDescription);
  }, [initialDescription]);

  useEffect(() => {
    if (readOnly) {
      setSelectedNodeId(null);
      setOpenMenuId(null);
      setOpenBalloon(null);
    }
  }, [readOnly]);

  const resolveTargetAgentIdx = useCallback(
    (raw: string): { idx: number; name: string } => {
      const value = raw.trim();
      if (!value) {
        return { idx: 0, name: "" };
      }
      if (/^\d+$/.test(value)) {
        const idx = Number(value);
        const hit = runtimes.find((item) => item.idx === idx);
        return { idx, name: hit?.agent_name ?? "" };
      }
      const lowered = value.toLowerCase();
      const hit =
        runtimes.find((item) => item.agent_name.trim().toLowerCase() === lowered) ||
        runtimes.find((item) => item.local_agent_id.trim().toLowerCase() === lowered) ||
        runtimes.find((item) => item.agent_id.trim().toLowerCase() === lowered);
      if (hit) {
        return { idx: hit.idx, name: hit.agent_name };
      }
      return { idx: 0, name: value };
    },
    [runtimes],
  );

  useEffect(() => {
    if (!aiImportRequest) {
      return;
    }
    if (processedAiImportNonceRef.current === aiImportRequest.nonce) {
      return;
    }
    if (readOnly) {
      processedAiImportNonceRef.current = aiImportRequest.nonce;
      onAiImportHandled?.();
      setError("읽기 전용 상태에서는 AI 워크플로우를 삽입할 수 없습니다. 체크인 후 다시 시도하세요.");
      return;
    }

    processedAiImportNonceRef.current = aiImportRequest.nonce;
    onAiImportHandled?.();

    const applyImport = async () => {
      setIsSaving(true);
      setError(null);
      try {
        const payload = parseAiWorkflowDesignResponse(aiImportRequest.assistantText);
        const createdItems: WorkNodeItem[] = [];

        for (const draft of payload.work_nodes) {
          const target = resolveTargetAgentIdx(draft.target_agent);
          const response = await fetch("/api/work-nodes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              uuid: draft.uuid,
              work_name: draft.work_name,
              work_description: draft.work_description,
              target_agent: target.idx,
              work_script: draft.work_script,
              script_type: draft.script_type || "",
              test_result: false,
              files: "",
              use_previous_work_result: Boolean(draft.use_previous_work_result),
              work_report: (draft.work_report || "").trim().slice(0, 200),
            }),
          });
          if (!response.ok) {
            throw new Error(
              await parseError(response, `작업노드 '${draft.logicalId}' 생성 실패`),
            );
          }
          const item = (await response.json()) as WorkNodeItem;
          createdItems.push({
            ...item,
            target_agent_name: item.target_agent_name || target.name,
          });
        }

        const remapped = payload.workflow;
        const mergedNodes = [
          ...workNodes.filter((n) => !createdItems.some((c) => c.uuid === n.uuid)),
          ...createdItems,
        ];
        setName(payload.workflow_name);
        setDescription(payload.workflow_description);
        setModel(hydrateEditor(remapped, mergedNodes, userNames));
        setSelectedNodeId(null);
        await onWorkNodesChanged();

        const isCreate = !workflowUuid;
        const saveBody: Record<string, string> = {
          workflow_name: payload.workflow_name,
          workflow_description: payload.workflow_description,
          workflow: remapped,
        };
        if (isCreate) {
          saveBody.uuid = payload.workflow_uuid;
        }
        const saveResponse = await fetch(
          isCreate ? "/api/workflows" : `/api/workflows/${workflowUuid}`,
          {
            method: isCreate ? "POST" : "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(saveBody),
          },
        );
        if (!saveResponse.ok) {
          throw new Error(
            await parseError(saveResponse, "작업노드는 생성됐지만 워크플로우 저장에 실패했습니다."),
          );
        }
        await onSaved((await saveResponse.json()) as WorkflowItem);
      } catch (err) {
        setError(err instanceof Error ? err.message : "AI 워크플로우 삽입에 실패했습니다.");
      } finally {
        setIsSaving(false);
      }
    };

    void applyImport();
  }, [
    aiImportRequest,
    readOnly,
    onAiImportHandled,
    resolveTargetAgentIdx,
    workNodes,
    userNames,
    onWorkNodesChanged,
    workflowUuid,
    onSaved,
  ]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const [runtimeRes, approverRes] = await Promise.all([
        fetch("/api/agentruntime"),
        fetch("/api/workflow-approvers"),
      ]);
      if (runtimeRes.ok) {
        const data = (await runtimeRes.json()) as AgentRuntimeRecord[];
        if (!cancelled) {
          setRuntimes(data);
        }
      }
      if (approverRes.ok) {
        const data = (await approverRes.json()) as WorkflowApprover[];
        if (!cancelled) {
          setApprovers(data);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handlePointer = (event: globalThis.MouseEvent) => {
      const target = event.target as Node;
      if (workflowCanvasRef.current?.contains(target)) {
        return;
      }
      if (editPanelRef.current?.contains(target)) {
        return;
      }
      setSelectedNodeId(null);
      setOpenMenuId(null);
      setOpenBalloon(null);
    };
    window.addEventListener("mousedown", handlePointer);
    return () => window.removeEventListener("mousedown", handlePointer);
  }, []);

  const createWorkNode = async (): Promise<WorkEditorNode> => {
    const response = await fetch("/api/work-nodes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ work_name: "새 작업노드" }),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "작업노드를 만들지 못했습니다."));
    }
    const item = (await response.json()) as WorkNodeItem;
    await onWorkNodesChanged();
    return workNodeFromItem(item);
  };

  const persistWork = async (
    node: WorkEditorNode,
    extras?: { validation_message?: string },
  ) => {
    try {
      const response = await fetch(`/api/work-nodes/${node.uuid}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(workNodeWriteBody(node, extras)),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업노드를 저장하지 못했습니다."));
      }
      const item = (await response.json()) as WorkNodeItem;
      setModel((current) => updateWork(current, node.clientId, workFieldsFromItem(item)));
      await onWorkNodesChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업노드를 저장하지 못했습니다.");
    }
  };

  const handleAddWork = async (afterId: string) => {
    setError(null);
    setOpenMenuId(null);
    setOpenBalloon(null);
    try {
      const node = await createWorkNode();
      setModel((current) => insertAfter(current, afterId, node));
      setSelectedNodeId(node.clientId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업노드를 만들지 못했습니다.");
    }
  };

  const handleAddHitl = (afterId: string) => {
    setOpenMenuId(null);
    setModel((current) =>
      insertAfter(current, afterId, {
        clientId: nextClientId("H"),
        type: "hitl",
        userid: "",
        username: "",
      }),
    );
  };

  const handleAddFailWork = async (workClientId: string) => {
    setOpenMenuId(null);
    setError(null);
    try {
      const node = await createWorkNode();
      setModel((current) => setFailWork(current, workClientId, node));
    } catch (err) {
      setError(err instanceof Error ? err.message : "실패시 작업노드를 만들지 못했습니다.");
    }
  };

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("워크플로우 명을 입력하세요.");
      return;
    }
    const invalid = validateEditor(model);
    if (invalid) {
      setError(invalid);
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const expression = serializeEditor(model);
      const isCreate = !workflowUuid;
      const response = await fetch(isCreate ? "/api/workflows" : `/api/workflows/${workflowUuid}`, {
        method: isCreate ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_name: trimmed,
          workflow_description: description,
          workflow: expression,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "워크플로우를 저장하지 못했습니다."));
      }
      await onSaved((await response.json()) as WorkflowItem);
    } catch (err) {
      setError(err instanceof Error ? err.message : "워크플로우를 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  const findWork = (clientId: string): WorkEditorNode | undefined => {
    if (model.extras[clientId]) {
      return model.extras[clientId];
    }
    const step = model.main.find((item) => item.clientId === clientId);
    return step?.type === "work" ? step : undefined;
  };

  const renderPlusMenu = (stepId: string, kind: "start" | "work" | "hitl") => {
    if (readOnly) {
      return (
        <div className="relative mx-1 flex items-center gap-0.5">
          <div className="h-px w-4 bg-slate-500" />
          <FlowArrow />
        </div>
      );
    }
    const isOpen = openMenuId === stepId;
    const onPlus = (event: ReactMouseEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      if (kind === "start") {
        void handleAddWork(stepId);
        return;
      }
      setOpenBalloon(null);
      setOpenMenuId(isOpen ? null : stepId);
    };
    return (
      <div className="relative mx-1 flex items-center gap-0.5">
        <div className="h-px w-4 bg-slate-500" />
        <PlusCircle onClick={onPlus} label={kind === "start" ? "작업노드 추가" : "다음 단계 추가"} />
        <FlowArrow />
        {isOpen ? (
          <div className="absolute left-1/2 top-8 z-30 w-36 -translate-x-1/2 rounded-md border border-slate-600 bg-slate-800 py-1 shadow-xl">
            <button
              type="button"
              className="block w-full px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
              onClick={() => void handleAddWork(stepId)}
            >
              다음 작업노드
            </button>
            {kind === "work" ? (
              <>
                <button
                  type="button"
                  className="block w-full px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
                  onClick={() => handleAddHitl(stepId)}
                >
                  승인자 지정
                </button>
                <button
                  type="button"
                  className="block w-full px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
                  onClick={() => void handleAddFailWork(stepId)}
                >
                  실패시 작업노드
                </button>
                <button
                  type="button"
                  className="block w-full px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
                  onClick={() => {
                    setOpenMenuId(null);
                    setModel((current) => terminateAfter(current, stepId));
                  }}
                >
                  종료
                </button>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  };

  const renderBalloon = (clientId: string) => (
    <Balloon>
      {approvers.length === 0 ? (
        <p className="text-[11px] text-slate-400">지정 가능한 승인자가 없습니다.</p>
      ) : (
        <div className="grid gap-1">
          {approvers.map((item) => (
            <button
              key={item.userid}
              type="button"
              className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-left text-[11px] text-slate-100 hover:bg-slate-700"
              onClick={() => {
                setModel((current) => ({
                  ...current,
                  main: current.main.map((step) =>
                    step.clientId === clientId && step.type === "hitl"
                      ? {
                          ...step,
                          userid: item.userid,
                          username: item.username || item.userid,
                        }
                      : step,
                  ),
                }));
                setOpenBalloon(null);
              }}
            >
              {item.username || item.userid}
            </button>
          ))}
        </div>
      )}
    </Balloon>
  );

  const renderApproverCard = (clientId: string, username: string, userid: string) => {
    const display = username || userid || "미지정";
    const isAwaiting =
      Boolean(awaitingHitlUserid) &&
      userid.trim().toLowerCase() === awaitingHitlUserid.trim().toLowerCase();
    return (
      <div
        aria-busy={isAwaiting || undefined}
        className={`relative w-[180px] rounded-sm border border-amber-400 bg-slate-950 px-2.5 py-2 pt-6 ${
          isAwaiting ? "wf-run-pulse" : ""
        }`}
      >
        {isAwaiting ? (
          <span className="absolute left-1.5 top-1.5 rounded-full border border-rose-500/80 bg-rose-950/80 px-1.5 py-0.5 text-[9px] font-semibold text-rose-100">
            승인 대기
          </span>
        ) : null}
        {readOnly ? null : <DeleteBox onClick={() => handleRemoveNode(clientId)} label="승인자 삭제" />}
        <div className="flex items-center gap-1">
          <span className="min-w-0 flex-1 truncate">
            <TextLabelChip title={display}>{display}</TextLabelChip>
          </span>
          {readOnly ? null : (
            <div className="relative shrink-0">
              <button
                type="button"
                aria-label="승인자 선택"
                title="승인자 선택"
                className="rounded p-1 text-slate-300 hover:bg-slate-800 hover:text-slate-100"
                onClick={(event) => {
                  event.stopPropagation();
                  setOpenMenuId(null);
                  setOpenBalloon((current) =>
                    current?.clientId === clientId ? null : { clientId, field: "approver" },
                  );
                }}
              >
                <HamburgerIcon />
              </button>
              {openBalloon?.clientId === clientId && openBalloon.field === "approver"
                ? renderBalloon(clientId)
                : null}
            </div>
          )}
        </div>
      </div>
    );
  };

  const handleRemoveNode = (clientId: string) => {
    setOpenMenuId(null);
    setOpenBalloon(null);
    setSelectedNodeId((current) => (current === clientId ? null : current));
    setModel((current) => removeNode(current, clientId));
  };

  const selectWorkNode = (clientId: string) => {
    if (readOnly) {
      return;
    }
    setSelectedNodeId(clientId);
    setOpenMenuId(null);
    setOpenBalloon(null);
  };

  const patchSelectedWork = (patch: Partial<WorkEditorNode>) => {
    if (!selectedNodeId) {
      return;
    }
    setModel((current) => updateWork(current, selectedNodeId, patch));
  };

  const handleSaveSelectedWork = () => {
    if (!selectedWorkNode) {
      return;
    }
    const node = findWork(selectedWorkNode.clientId);
    if (node) {
      void persistWork({ ...node, name: node.name.trim() || "새 작업노드" });
    }
  };

  const handlePersistSelectedPatch = async (
    patch: Partial<WorkEditorNode>,
    extras?: { validationMessage?: string },
  ) => {
    if (!selectedWorkNode) {
      return;
    }
    const node = findWork(selectedWorkNode.clientId);
    if (!node) {
      return;
    }
    const next = { ...node, ...patch };
    setModel((current) => updateWork(current, selectedWorkNode.clientId, patch));
    await persistWork(
      next,
      extras?.validationMessage != null
        ? { validation_message: extras.validationMessage }
        : undefined,
    );
  };

  const handleUploadSelectedFile = async (file: File) => {
    if (!selectedWorkNode) {
      return;
    }
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(`/api/work-nodes/${selectedWorkNode.uuid}/file`, {
      method: "POST",
      body,
    });
    if (!response.ok) {
      setError(await parseError(response, "파일을 올리지 못했습니다."));
      return;
    }
    const item = (await response.json()) as WorkNodeItem;
    setModel((current) => updateWork(current, selectedWorkNode.clientId, workFieldsFromItem(item)));
    await onWorkNodesChanged();
  };

  const isSelected = (clientId: string) => selectedNodeId === clientId;

  const hasMailReport = (node: WorkEditorNode): boolean =>
    Boolean((node.workReport || "").trim());

  const renderWorkCard = (node: WorkEditorNode, failBranch = false) => {
    const hasScript = Boolean(node.workScript.trim());
    const hasFile = Boolean(node.files.trim());
    const live = workNodes.find((item) => item.uuid === node.uuid);
    const isNodeRunning = isRunInProgress(
      live?.last_start_date ?? node.lastStartDate,
      live?.last_end_date ?? node.lastEndDate,
    );
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={(event) => {
          event.stopPropagation();
          selectWorkNode(node.clientId);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            selectWorkNode(node.clientId);
          }
        }}
        aria-busy={isNodeRunning || undefined}
        className={`relative w-[208px] rounded-lg border px-2.5 pb-2.5 pt-6 text-left ${
          failBranch ? "border-rose-400/80 bg-slate-950" : "border-sky-400/80 bg-slate-950"
        } ${readOnly ? "cursor-default" : "cursor-pointer"} ${
          isSelected(node.clientId) ? "ring-2 ring-sky-300 ring-offset-1 ring-offset-slate-900" : ""
        } ${isNodeRunning ? "wf-run-pulse" : ""}`}
      >
        {isNodeRunning ? (
          <span className="absolute left-1.5 top-1.5 rounded-full border border-rose-500/80 bg-rose-950/80 px-1.5 py-0.5 text-[9px] font-semibold text-rose-100">
            실행 중
          </span>
        ) : null}
        {readOnly ? null : (
          <DeleteBox onClick={() => handleRemoveNode(node.clientId)} label="작업노드 삭제" />
        )}
        <div className="grid min-w-0 gap-1.5">
          <div className="min-w-0">
            <p className="text-[10px] text-slate-500">작업명</p>
            <TextLabelChip title={node.name || "새 작업노드"}>
              {node.name || "새 작업노드"}
            </TextLabelChip>
          </div>
          <div className="min-w-0">
            <p className="text-[10px] text-slate-500">에이전트</p>
            <TextLabelChip title={node.targetAgentName || "미지정"}>
              {node.targetAgentName || "미지정"}
            </TextLabelChip>
          </div>
          <div>
            <p className="text-[10px] text-slate-500">작업 스크립트</p>
            {hasScript ? (
              <span className="text-sm leading-none" title="실행 결과 있음" aria-label="실행 결과 있음">
                ✅
              </span>
            ) : (
              <TextLabelChip title="미실행">미실행</TextLabelChip>
            )}
          </div>
          {hasFile ? (
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] text-slate-500">첨부 유무</p>
              <span className="text-sm leading-none" title="첨부 있음" aria-label="첨부 있음">
                ✅
              </span>
            </div>
          ) : null}
        </div>
      </div>
    );
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 border-b border-slate-800 px-4 py-3">
        <label className="grid gap-1 text-xs text-slate-400">
          워크플로우 명
          <div className="flex items-center gap-2">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              readOnly={readOnly}
              disabled={readOnly}
              className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-80"
            />
            {readOnly ? null : (
              <button
                type="button"
                disabled={isSaving || !name.trim()}
                onClick={() => void handleSave()}
                className="shrink-0 rounded-md border border-sky-700 bg-sky-950/50 px-3 py-2 text-sm text-sky-100 hover:bg-sky-900/60 disabled:opacity-50"
              >
                {saveLabel}
              </button>
            )}
          </div>
        </label>
        <label className="mt-3 grid gap-1 text-xs text-slate-400">
          워크플로우 설명
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={500}
            rows={2}
            readOnly={readOnly}
            disabled={readOnly}
            placeholder="워크플로우 메타 설명"
            className="resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-80"
          />
        </label>
      </div>

      {error ? (
        <div className="mx-4 mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-xs text-rose-200">
          {error}
        </div>
      ) : null}

      <div ref={splitLayoutRef} className="flex min-h-0 flex-1 flex-col">
        <div
          ref={workflowCanvasRef}
          className="min-h-0 flex-1 overflow-auto p-6"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setSelectedNodeId(null);
            }
          }}
        >
          <div className="flex min-h-[280px] items-center pb-40">
            {model.main.map((step) => {
              return (
                <div key={step.clientId} className="flex items-center self-center">
                  <div className="relative flex items-center">
                    {step.type === "start" || step.type === "end" ? (
                      <div className="flex h-10 min-w-10 items-center justify-center rounded-full border border-sky-300 bg-slate-950 px-2 text-xs font-semibold text-slate-100">
                        {step.type === "start" ? "시작" : "종료"}
                      </div>
                    ) : null}
                    {step.type === "hitl" ? (
                      renderApproverCard(step.clientId, step.username, step.userid)
                    ) : null}
                    {step.type === "work" ? renderWorkCard(step) : null}
                    {step.type === "work" &&
                    (hasMailReport(step) ||
                      step.fail.kind === "work" ||
                      step.fail.kind === "end") ? (
                      <div className="absolute left-1/2 top-full flex -translate-x-1/2 flex-col items-center">
                        {hasMailReport(step) ? (
                          <>
                            <FlowDownArrow tone="report" />
                            <MailReportBadge />
                          </>
                        ) : null}
                        {step.fail.kind === "work" && model.extras[step.fail.clientId] ? (
                          <>
                            <FlowDownArrow tone="fail" />
                            <div className="relative flex flex-col items-center">
                              {renderWorkCard(model.extras[step.fail.clientId], true)}
                              {hasMailReport(model.extras[step.fail.clientId]) ? (
                                <>
                                  <FlowDownArrow tone="report" />
                                  <MailReportBadge />
                                </>
                              ) : null}
                            </div>
                          </>
                        ) : null}
                        {step.fail.kind === "end" ? (
                          <>
                            <FlowDownArrow tone="fail" />
                            <div className="flex h-10 min-w-10 items-center justify-center rounded-full border border-rose-300 bg-slate-950 px-2 text-xs font-semibold text-rose-100">
                              종료
                            </div>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                  {step.type !== "end" ? renderPlusMenu(step.clientId, step.type) : null}
                </div>
              );
            })}
          </div>
        </div>

        {workflowUuid || (selectedWorkNode && !readOnly) ? (
          <>
            <div
              role="separator"
              aria-orientation="horizontal"
              aria-label="하단 패널 높이 조절"
              onMouseDown={handleEditPanelResizeStart}
              className="group flex h-2 shrink-0 cursor-row-resize items-center justify-center border-y border-slate-700 bg-slate-900 hover:bg-slate-800"
            >
              <span className="h-1 w-12 rounded-full bg-slate-600 group-hover:bg-slate-400" />
            </div>
            <section
              ref={editPanelRef}
              className="flex shrink-0 flex-col overflow-hidden bg-slate-950/40"
              style={{ height: editPanelHeight ?? resolveDefaultEditPanelHeight() }}
            >
              <header className="flex shrink-0 items-center gap-1 border-b border-slate-800 px-3 py-1.5">
                <button
                  type="button"
                  onClick={() => setBottomTab("results")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium ${
                    bottomTab === "results"
                      ? "bg-slate-800 text-slate-100"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  워크플로우 작업결과
                </button>
                <button
                  type="button"
                  onClick={() => setBottomTab("edit")}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium ${
                    bottomTab === "edit"
                      ? "bg-slate-800 text-slate-100"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  작업 편집
                </button>
              </header>
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                {bottomTab === "results" ? (
                  workflowUuid ? (
                    <WorkflowHistoryPanel workflowUuid={workflowUuid} />
                  ) : (
                    <div className="flex h-full items-center justify-center p-4 text-[11px] text-slate-500">
                      워크플로우를 선택하면 작업결과를 확인할 수 있습니다.
                    </div>
                  )
                ) : selectedWorkNode && !readOnly ? (
                  <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4">
                    <WorkNodeEditPanel
                      node={selectedWorkNode}
                      assignedAgents={assignedAgents}
                      runtimes={runtimes}
                      userid={user.userid}
                      onChange={patchSelectedWork}
                      onSave={handleSaveSelectedWork}
                      onPersistPatch={handlePersistSelectedPatch}
                      onUploadFile={handleUploadSelectedFile}
                    />
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center p-4 text-[11px] text-slate-500">
                    {readOnly
                      ? "읽기 모드에서는 작업 편집을 사용할 수 없습니다."
                      : "편집할 작업노드를 선택하세요."}
                  </div>
                )}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}
