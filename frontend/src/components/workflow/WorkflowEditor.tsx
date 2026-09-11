import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
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
import {
  DEFAULT_WORKFLOW_CRON_EXPR,
  WorkflowScheduleField,
} from "./WorkflowScheduleField";
import { parseWorkNodeCronExpr } from "./WorkNodeScheduleField";
import { WorkNodeEditPanel } from "./WorkNodeEditPanel";
import { WorkNodeResultsPanel } from "./WorkNodeResultsPanel";
import { TemplateVariableInputs } from "./TemplateVariableInputs";
import { WorkflowApproverPickModal } from "./WorkflowApproverPickModal";
import { WorkflowHistoryPanel } from "./WorkflowHistoryPanel";
import { WorkflowIcon } from "./WorkflowIcon";
import {
  applyTemplateVariables,
  extractTemplateVariableNames,
  WorkflowTemplatePromptField,
} from "./WorkflowTemplateMarkdown";
import {
  formatAiWorkflowDesignJson,
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
  workFieldsFromItem,
  workNodeFromItem,
  workNodeWriteBody,
  hitlNodeWriteBody,
  isRunInProgress,
  type EditorModel,
  type HitlEditorNode,
  type WorkEditorNode,
} from "./workflowModel";

const CLARIFY_ANSWER_SECTION = "## 보완질의에 대한 답변";

export type DiagramPanelState =
  | "STATE_INPUT"
  | "STATE_GENERATE"
  | "STATE_RESPONSE_SUCCESS"
  | "STATE_RESPONSE_ADDITIONAL_DATA";

export type DiagramAgentEvent = {
  nonce: number;
  kind: "success" | "clarify" | "error";
  content: string;
};

interface WorkflowEditorProps {
  user: AuthUser;
  workNodes: WorkNodeItem[];
  initialName: string;
  initialExpression: string;
  initialDescription?: string;
  initialCron?: boolean;
  initialCronExpr?: string;
  readOnly?: boolean;
  /** Changes only when starting a new create/edit session — not on create→edit after save. */
  sessionKey: string;
  onSaved: (item: WorkflowItem) => Promise<void> | void;
  onWorkNodesChanged: () => Promise<void> | void;
  /** Stop a running work node (fails the whole workflow). */
  onStopWorkNode?: (workUuid: string) => Promise<void> | void;
  workflowUuid?: string;
  awaitingHitlUserid?: string;
  awaitingJobIdx?: number | null;
  onAwaitingHitlApprove?: () => void;
  aiImportRequest?: { nonce: number; assistantText: string } | null;
  onAiImportHandled?: () => void;
  diagramAgentEvent?: DiagramAgentEvent | null;
  onDiagramAgentEventHandled?: () => void;
  onDiagramGenerate?: (prompt: string) => void;
  onSaveStateChange?: (state: { canSave: boolean; isSaving: boolean }) => void;
}

export type WorkflowEditorHandle = {
  save: () => Promise<void>;
};


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
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-sky-400 bg-slate-900 text-sky-200 hover:bg-sky-950"
    >
      <WorkflowIcon name="connect" size="sm" label={label} />
    </button>
  );
}

function FlowDashLine({ widthClass = "w-4" }: { widthClass?: string }) {
  return (
    <svg
      viewBox="0 0 16 12"
      className={`h-3 ${widthClass} shrink-0 text-slate-400`}
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      <path
        d="M0 6 H16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray="3 2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function FlowArrow() {
  return (
    <svg viewBox="0 0 28 12" className="h-3 w-7 shrink-0 text-slate-400" aria-hidden="true">
      <path
        d="M1 6 H20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray="3 2"
        strokeLinecap="round"
      />
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
      className="flex h-10 min-w-10 items-center justify-center gap-1 rounded-full border border-emerald-400 bg-slate-950 px-2 text-[10px] font-semibold text-emerald-100"
      title="작업 완료 후 결과 메일 전송"
    >
      <WorkflowIcon name="mail" size="sm" label="메일전송" />
      <span>메일</span>
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
      className="absolute right-1 top-1 z-10 flex h-5 w-5 items-center justify-center rounded-sm bg-transparent text-slate-300 hover:bg-rose-950/60 hover:text-rose-200"
    >
      <WorkflowIcon name="delete" size="xs" label="삭제" />
    </button>
  );
}

function StopBox({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      aria-label="작업 중지"
      title="실행 중지 (워크플로우 실패 종료)"
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="absolute right-1 top-1 z-10 inline-flex items-center gap-1 rounded-sm border border-rose-500/80 bg-rose-950/80 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-rose-100 hover:bg-rose-900 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <WorkflowIcon name="stop" size="xs" label="중지" />
      중지
    </button>
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

export const WorkflowEditor = forwardRef<WorkflowEditorHandle, WorkflowEditorProps>(function WorkflowEditor(
  {
    user,
    workNodes,
    initialName,
    initialExpression,
    initialDescription = "",
    initialCron = false,
    initialCronExpr = DEFAULT_WORKFLOW_CRON_EXPR,
    readOnly = false,
    sessionKey,
    onSaved,
    onWorkNodesChanged,
    onStopWorkNode,
    workflowUuid,
    awaitingHitlUserid = "",
    awaitingJobIdx = null,
    onAwaitingHitlApprove,
    aiImportRequest = null,
    onAiImportHandled,
    diagramAgentEvent = null,
    onDiagramAgentEventHandled,
    onDiagramGenerate,
    onSaveStateChange,
  },
  ref,
) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [cronEnabled, setCronEnabled] = useState(initialCron);
  const [cronExpr, setCronExpr] = useState(initialCronExpr || DEFAULT_WORKFLOW_CRON_EXPR);
  const [diagramPrompt, setDiagramPrompt] = useState("");
  const [templateNames, setTemplateNames] = useState<string[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [isLoadingTemplate, setIsLoadingTemplate] = useState(false);
  const [templateVarValues, setTemplateVarValues] = useState<Record<string, string>>({});
  const [diagramPanelState, setDiagramPanelState] = useState<DiagramPanelState>("STATE_INPUT");
  const [diagramResultJson, setDiagramResultJson] = useState("");
  const [clarifyMessages, setClarifyMessages] = useState<string[]>([]);
  const [workingPrompt, setWorkingPrompt] = useState("");
  const lastSentPromptRef = useRef("");
  const diagramStateBeforeGenerateRef = useRef<DiagramPanelState>("STATE_INPUT");
  const sessionTemplateCacheRef = useRef<
    Record<string, { content: string; vars: Record<string, string> }>
  >({});
  const skipNextHydrateRef = useRef(false);
  const processedDiagramEventNonceRef = useRef<number | null>(null);
  const clarifyPromptTextareaRef = useRef<HTMLTextAreaElement>(null);
  const processedAiImportNonceRef = useRef<number | null>(null);
  const activeSessionKeyRef = useRef(sessionKey);
  const [model, setModel] = useState<EditorModel>(() => emptyEditorModel());
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isStoppingUuid, setIsStoppingUuid] = useState<string | null>(null);
  const [runtimes, setRuntimes] = useState<AgentRuntimeRecord[]>([]);
  const [approvers, setApprovers] = useState<WorkflowApprover[]>([]);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [approverPickClientId, setApproverPickClientId] = useState<string | null>(null);
  const approverPickClientIdRef = useRef<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [bottomTab, setBottomTab] = useState<"edit" | "results" | "work-results">("results");
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

  const selectedHitlNode = useMemo(() => {
    if (!selectedNodeId) {
      return null;
    }
    const step = model.main.find((item) => item.clientId === selectedNodeId);
    return step?.type === "hitl" ? step : null;
  }, [model, selectedNodeId]);

  const workflowWorkNodes = useMemo(() => {
    const seen = new Set<string>();
    const nodes: WorkEditorNode[] = [];
    for (const step of model.main) {
      if (step.type !== "work") {
        continue;
      }
      const key = step.uuid.trim() || step.clientId;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      nodes.push(step);
    }
    for (const extra of Object.values(model.extras)) {
      const key = extra.uuid.trim() || extra.clientId;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      nodes.push(extra);
    }
    return nodes;
  }, [model]);

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
    if (activeSessionKeyRef.current === sessionKey) {
      return;
    }
    activeSessionKeyRef.current = sessionKey;
    setDiagramPanelState("STATE_INPUT");
    setDiagramResultJson("");
    setClarifyMessages([]);
    setWorkingPrompt("");
    setDiagramPrompt("");
    setSelectedTemplate("");
    setTemplateVarValues({});
    sessionTemplateCacheRef.current = {};
    lastSentPromptRef.current = "";
    processedDiagramEventNonceRef.current = null;
    processedAiImportNonceRef.current = null;
    skipNextHydrateRef.current = false;
  }, [sessionKey]);

  useEffect(() => {
    if (skipNextHydrateRef.current) {
      skipNextHydrateRef.current = false;
      return;
    }
    try {
      setModel(hydrateEditor(initialExpression, workNodes, userNames));
      setSelectedNodeId(null);
      setError(null);
    } catch (err) {
      setModel(emptyEditorModel());
      setSelectedNodeId(null);
      setError(err instanceof Error ? err.message : "작업 워크플로우 표현식을 읽지 못했습니다.");
    }
    // 노드 목록 갱신으로 편집중 그래프가 초기화되지 않도록 workNodes는 의존성에서 제외한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialExpression, workflowUuid, sessionKey]);

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
    setCronEnabled(Boolean(initialCron));
    setCronExpr((initialCronExpr || DEFAULT_WORKFLOW_CRON_EXPR).slice(0, 20));
  }, [initialCron, initialCronExpr]);

  useEffect(() => {
    if (readOnly) {
      setSelectedNodeId(null);
      setOpenMenuId(null);
      setApproverPickClientId(null);
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
      setError("읽기 전용 상태에서는 AI 작업 워크플로우를 삽입할 수 없습니다. 체크인 후 다시 시도하세요.");
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
              target_agent: draft.worker === "hitl" ? 0 : target.idx,
              work_script: draft.worker === "hitl" ? "" : draft.work_script,
              script_type: draft.worker === "hitl" ? "" : draft.script_type || "",
              test_result: false,
              files: "",
              use_previous_work_result: Boolean(draft.use_previous_work_result),
              work_report: (draft.work_report || "").trim().slice(0, 400),
              cron: Boolean(draft.cron),
              cron_expr: (draft.cron_expr || "0 9 * * *").slice(0, 20),
              worker: draft.worker || "agent",
              upload: Boolean(draft.upload),
              upload_path: "",
              approver_userid: draft.approver_userid || "",
              crud: draft.worker === "hitl" ? "" : draft.crud || "",
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
        setCronEnabled(Boolean(payload.cron));
        setCronExpr((payload.cron_expr || DEFAULT_WORKFLOW_CRON_EXPR).slice(0, 20));
        setModel(hydrateEditor(remapped, mergedNodes, userNames));
        setSelectedNodeId(null);
        skipNextHydrateRef.current = true;
        await onWorkNodesChanged();

        const isCreate = !workflowUuid;
        const saveBody: Record<string, unknown> = {
          workflow_name: payload.workflow_name,
          workflow_description: payload.workflow_description,
          workflow: remapped,
          cron: Boolean(payload.cron),
          cron_expr: (payload.cron_expr || DEFAULT_WORKFLOW_CRON_EXPR).slice(0, 20),
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
            await parseError(saveResponse, "작업노드는 생성됐지만 작업 워크플로우 저장에 실패했습니다."),
          );
        }
        await onSaved((await saveResponse.json()) as WorkflowItem);
      } catch (err) {
        setError(err instanceof Error ? err.message : "AI 작업 워크플로우 삽입에 실패했습니다.");
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
      const [runtimeRes, approverRes, templateRes] = await Promise.all([
        fetch("/api/agentruntime"),
        fetch("/api/workflow-approvers"),
        fetch("/api/workflow-templates"),
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
      if (templateRes.ok) {
        const data = (await templateRes.json()) as { name: string }[];
        if (!cancelled) {
          setTemplateNames(data.map((item) => item.name));
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const rememberCurrentTemplateSession = (templateName: string) => {
    const key = templateName.trim();
    if (!key) {
      return;
    }
    sessionTemplateCacheRef.current[key] = {
      content: diagramPrompt,
      vars: { ...templateVarValues },
    };
  };

  const syncTemplateVarFields = (content: string, previousVars?: Record<string, string>) => {
    const names = extractTemplateVariableNames(content);
    const source = previousVars ?? templateVarValues;
    const nextValues: Record<string, string> = {};
    for (const varName of names) {
      nextValues[varName] = source[varName] ?? "";
    }
    setTemplateVarValues(nextValues);
  };

  const handleTemplateSelect = async (name: string) => {
    if (selectedTemplate) {
      rememberCurrentTemplateSession(selectedTemplate);
    }
    setSelectedTemplate(name);
    if (!name) {
      setDiagramPrompt("");
      setTemplateVarValues({});
      return;
    }

    const cached = sessionTemplateCacheRef.current[name];
    if (cached) {
      setDiagramPrompt(cached.content);
      setTemplateVarValues({ ...cached.vars });
      setError(null);
      return;
    }

    setIsLoadingTemplate(true);
    setError(null);
    try {
      const response = await fetch(`/api/workflow-templates/${encodeURIComponent(name)}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "양식을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as { name: string; content: string };
      // Server file is read-only source; session edits never write back.
      setDiagramPrompt(data.content);
      syncTemplateVarFields(data.content, {});
      sessionTemplateCacheRef.current[name] = {
        content: data.content,
        vars: Object.fromEntries(
          extractTemplateVariableNames(data.content).map((varName) => [varName, ""]),
        ),
      };
    } catch (err) {
      setDiagramPrompt("");
      setTemplateVarValues({});
      setError(err instanceof Error ? err.message : "양식을 불러오지 못했습니다.");
    } finally {
      setIsLoadingTemplate(false);
    }
  };

  const handleDiagramPromptChange = (nextContent: string) => {
    setDiagramPrompt(nextContent);
    setTemplateVarValues((current) => {
      const nextValues: Record<string, string> = {};
      for (const varName of extractTemplateVariableNames(nextContent)) {
        nextValues[varName] = current[varName] ?? "";
      }
      return nextValues;
    });
  };

  // Keep session cache in sync with prompt + var edits (never persists to md files).
  useEffect(() => {
    if (!selectedTemplate || diagramPanelState === "STATE_RESPONSE_SUCCESS") {
      return;
    }
    sessionTemplateCacheRef.current[selectedTemplate] = {
      content: diagramPrompt,
      vars: { ...templateVarValues },
    };
  }, [selectedTemplate, diagramPrompt, templateVarValues, diagramPanelState]);

  const templateVarNames = useMemo(
    () => extractTemplateVariableNames(diagramPrompt),
    [diagramPrompt],
  );

  const hasEmptyTemplateVars = templateVarNames.some(
    (varName) => !(templateVarValues[varName] ?? "").trim(),
  );

  const isDiagramBusy = diagramPanelState === "STATE_GENERATE";
  const isDiagramInputLocked = isDiagramBusy || readOnly;

  const handleDiagramGenerate = () => {
    if (!onDiagramGenerate || readOnly || isDiagramBusy) {
      return;
    }

    let promptToSend = "";
    if (diagramPanelState === "STATE_RESPONSE_ADDITIONAL_DATA") {
      promptToSend = workingPrompt.trim();
      if (!promptToSend) {
        setError("보완 답변이 포함된 프롬프트를 입력하세요.");
        return;
      }
    } else {
      if (!diagramPrompt.trim()) {
        return;
      }
      if (hasEmptyTemplateVars) {
        setError("양식 변수 값을 모두 입력하세요.");
        return;
      }
      promptToSend = applyTemplateVariables(diagramPrompt, templateVarValues).trim();
    }

    setError(null);
    lastSentPromptRef.current = promptToSend;
    diagramStateBeforeGenerateRef.current = diagramPanelState;
    setDiagramPanelState("STATE_GENERATE");
    onDiagramGenerate(promptToSend);
  };

  const handleDiagramRegenerate = () => {
    setDiagramResultJson("");
    setClarifyMessages([]);
    setWorkingPrompt("");
    lastSentPromptRef.current = "";
    setDiagramPanelState("STATE_INPUT");
    setError(null);
  };

  useEffect(() => {
    if (!diagramAgentEvent) {
      return;
    }
    if (processedDiagramEventNonceRef.current === diagramAgentEvent.nonce) {
      return;
    }
    processedDiagramEventNonceRef.current = diagramAgentEvent.nonce;
    onDiagramAgentEventHandled?.();

    if (diagramAgentEvent.kind === "success") {
      setDiagramResultJson(formatAiWorkflowDesignJson(diagramAgentEvent.content));
      setClarifyMessages([]);
      setWorkingPrompt("");
      setDiagramPanelState("STATE_RESPONSE_SUCCESS");
      return;
    }

    if (diagramAgentEvent.kind === "clarify") {
      setClarifyMessages((current) => [...current, diagramAgentEvent.content]);
      setWorkingPrompt((current) => {
        const base = (current.trim() ? current : lastSentPromptRef.current).trimEnd();
        return `${base}\n\n${CLARIFY_ANSWER_SECTION}\n`;
      });
      setDiagramPanelState("STATE_RESPONSE_ADDITIONAL_DATA");
      return;
    }

    setError(diagramAgentEvent.content || "작업 워크플로우 생성에 실패했습니다.");
    setDiagramPanelState((current) => {
      if (current !== "STATE_GENERATE") {
        return current;
      }
      return diagramStateBeforeGenerateRef.current === "STATE_RESPONSE_ADDITIONAL_DATA"
        ? "STATE_RESPONSE_ADDITIONAL_DATA"
        : "STATE_INPUT";
    });
  }, [diagramAgentEvent, onDiagramAgentEventHandled]);

  // Recover if generate UI stayed busy but AI import already arrived (event race / remount).
  useEffect(() => {
    if (!aiImportRequest || diagramPanelState !== "STATE_GENERATE") {
      return;
    }
    setDiagramResultJson(formatAiWorkflowDesignJson(aiImportRequest.assistantText));
    setClarifyMessages([]);
    setWorkingPrompt("");
    setDiagramPanelState("STATE_RESPONSE_SUCCESS");
  }, [aiImportRequest, diagramPanelState]);

  useEffect(() => {
    if (diagramPanelState !== "STATE_RESPONSE_ADDITIONAL_DATA") {
      return;
    }
    const node = clarifyPromptTextareaRef.current;
    if (!node) {
      return;
    }
    const focusId = window.requestAnimationFrame(() => {
      node.focus();
      const cursor = node.value.length;
      node.setSelectionRange(cursor, cursor);
      node.scrollTop = node.scrollHeight;
    });
    return () => window.cancelAnimationFrame(focusId);
  }, [diagramPanelState, workingPrompt, clarifyMessages.length]);

  useEffect(() => {
    approverPickClientIdRef.current = approverPickClientId;
  }, [approverPickClientId]);

  useEffect(() => {
    const handlePointer = (event: globalThis.MouseEvent) => {
      if (approverPickClientIdRef.current) {
        return;
      }
      const target = event.target as Node;
      if (workflowCanvasRef.current?.contains(target)) {
        return;
      }
      if (editPanelRef.current?.contains(target)) {
        return;
      }
      setSelectedNodeId(null);
      setOpenMenuId(null);
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
    setApproverPickClientId(null);
    try {
      const node = await createWorkNode();
      setModel((current) => insertAfter(current, afterId, node));
      setSelectedNodeId(node.clientId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업노드를 만들지 못했습니다.");
    }
  };

  const handleAddHitl = async (afterId: string) => {
    setOpenMenuId(null);
    setError(null);
    try {
      const response = await fetch("/api/work-nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          work_name: "결재승인",
          worker: "hitl",
          upload: false,
          approver_userid: "",
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "승인 노드를 만들지 못했습니다."));
      }
      const item = (await response.json()) as WorkNodeItem;
      await onWorkNodesChanged();
      const userid = (item.approver_userid || "").trim();
      setModel((current) =>
        insertAfter(current, afterId, {
          clientId: nextClientId(`H${item.uuid}`),
          type: "hitl",
          uuid: item.uuid,
          userid,
          username: userid,
          name: item.work_name || "결재승인",
          description: item.work_description || "",
          upload: Boolean(item.upload),
          uploadPath: item.upload_path || "",
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "승인 노드를 만들지 못했습니다.");
    }
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

  const handleSave = useCallback(async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("작업 워크플로우 명을 입력하세요.");
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
          cron: cronEnabled,
          cron_expr: (cronExpr || DEFAULT_WORKFLOW_CRON_EXPR).slice(0, 20),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 워크플로우를 저장하지 못했습니다."));
      }
      await onSaved((await response.json()) as WorkflowItem);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 워크플로우를 저장하지 못했습니다.");
    } finally {
      setIsSaving(false);
    }
  }, [
    cronEnabled,
    cronExpr,
    description,
    model,
    name,
    onSaved,
    workflowUuid,
  ]);

  useImperativeHandle(ref, () => ({ save: handleSave }), [handleSave]);

  useEffect(() => {
    onSaveStateChange?.({
      canSave: !readOnly && Boolean(name.trim()),
      isSaving,
    });
  }, [isSaving, name, onSaveStateChange, readOnly]);

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
          <FlowDashLine />
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
      setApproverPickClientId(null);
      setOpenMenuId(isOpen ? null : stepId);
    };
    return (
      <div className="relative mx-1 flex items-center gap-0.5">
        <FlowDashLine />
        <PlusCircle onClick={onPlus} label={kind === "start" ? "작업노드 추가" : "다음 단계 추가"} />
        <FlowArrow />
        {isOpen ? (
          <div className="absolute left-1/2 top-8 z-30 w-40 -translate-x-1/2 rounded-md border border-slate-600 bg-slate-800 py-1 shadow-xl">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
              onClick={() => void handleAddWork(stepId)}
            >
              <WorkflowIcon name="work-node" size="xs" />
              다음 작업노드
            </button>
            {kind === "work" ? (
              <>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
                  onClick={() => handleAddHitl(stepId)}
                >
                  <WorkflowIcon name="approve" size="xs" />
                  승인자 지정
                </button>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
                  onClick={() => void handleAddFailWork(stepId)}
                >
                  <WorkflowIcon name="fail-branch" size="xs" />
                  실패시 작업노드
                </button>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-100 hover:bg-slate-700"
                  onClick={() => {
                    setOpenMenuId(null);
                    setModel((current) => terminateAfter(current, stepId));
                  }}
                >
                  <WorkflowIcon name="stop" size="xs" />
                  종료
                </button>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  };

  const renderApproverCard = (
    clientId: string,
    username: string,
    userid: string,
    upload = false,
  ) => {
    const display = username || userid || "미지정";
    const isAwaiting =
      Boolean(awaitingHitlUserid) &&
      userid.trim().toLowerCase() === awaitingHitlUserid.trim().toLowerCase();
    const canOpenHitlApprove =
      isAwaiting && awaitingJobIdx != null && typeof onAwaitingHitlApprove === "function";
    return (
      <div
        aria-busy={isAwaiting || undefined}
        title={canOpenHitlApprove ? "클릭하여 승인·반려·파일 업로드" : undefined}
        className={`relative w-[208px] rounded-sm border border-amber-400 bg-slate-950 px-2.5 py-2 pt-6 ${
          isAwaiting ? "wf-run-pulse" : ""
        } ${canOpenHitlApprove ? "cursor-pointer hover:border-rose-400" : ""}`}
        onClick={
          canOpenHitlApprove
            ? (event) => {
                event.stopPropagation();
                onAwaitingHitlApprove();
              }
            : undefined
        }
      >
        <div className="absolute left-1.5 top-1.5 flex max-w-[calc(100%-2rem)] flex-wrap gap-1">
          {isAwaiting ? (
            <span
              className={`inline-flex items-center gap-1 rounded-full border border-rose-500/80 bg-rose-950/80 px-1.5 py-0.5 text-[9px] font-semibold text-rose-100 ${
                canOpenHitlApprove ? "ring-1 ring-rose-300/60" : ""
              }`}
            >
              <WorkflowIcon name="approve" size="xs" label="승인 대기" />
              승인 대기
            </span>
          ) : null}
        </div>
        {readOnly ? null : <DeleteBox onClick={() => handleRemoveNode(clientId)} label="승인자 삭제" />}
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="min-w-0 flex-1 truncate">
            <TextLabelChip title={display}>{display}</TextLabelChip>
          </span>
          {upload ? (
            <span
              className="inline-flex shrink-0 items-center gap-1 rounded-md border border-sky-500/80 bg-sky-950/50 px-2.5 py-1 text-[11px] font-medium text-sky-100"
              title="승인 시 파일 업로드 필수"
            >
              <WorkflowIcon name="upload" size="xs" label="업로드" />
              업로드
            </span>
          ) : null}
          {readOnly ? null : (
            <button
              type="button"
              aria-label="결재자 선택"
              title="결재자 선택"
              className="inline-flex shrink-0 items-center gap-1 rounded-md border border-emerald-700/80 bg-emerald-950/40 px-2.5 py-1 text-[11px] font-medium text-emerald-100 hover:bg-emerald-900/50"
              onClick={(event) => {
                event.stopPropagation();
                setOpenMenuId(null);
                setApproverPickClientId(clientId);
              }}
            >
              <WorkflowIcon name="owner" size="xs" label="결재자" />
              결재자
            </button>
          )}
        </div>
      </div>
    );
  };

  const handleRemoveNode = (clientId: string) => {
    setOpenMenuId(null);
    setApproverPickClientId(null);
    setSelectedNodeId((current) => (current === clientId ? null : current));
    setModel((current) => removeNode(current, clientId));
  };

  const selectWorkNode = (clientId: string) => {
    if (readOnly) {
      return;
    }
    setSelectedNodeId(clientId);
    setOpenMenuId(null);
    setApproverPickClientId(null);
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

  const showDiagramPromptPanel = !workflowUuid;

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
    const isScheduleWaiting = isNodeRunning && Boolean(live?.schedule_wait ?? node.scheduleWait);
    const isCronEnabled = Boolean(live?.cron ?? node.cron);
    const scheduleDraft = parseWorkNodeCronExpr(live?.cron_expr ?? node.cronExpr);
    const scheduleLabel = `${String(scheduleDraft.hour).padStart(2, "0")}시 ${String(scheduleDraft.minute).padStart(2, "0")}분 예약됨`;
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
        } ${
          isScheduleWaiting ? "wf-schedule-pulse" : isNodeRunning ? "wf-run-pulse" : ""
        }`}
      >
        {isScheduleWaiting ? (
          <span className="absolute left-1.5 top-1.5 inline-flex items-center gap-1 rounded-full border border-amber-500/80 bg-amber-950/80 px-1.5 py-0.5 text-[9px] font-semibold text-amber-100">
            <WorkflowIcon name="history" size="xs" label="예약대기중" />
            예약대기중
          </span>
        ) : isNodeRunning ? (
          <span className="absolute left-1.5 top-1.5 inline-flex items-center gap-1 rounded-full border border-rose-500/80 bg-rose-950/80 px-1.5 py-0.5 text-[9px] font-semibold text-rose-100">
            <WorkflowIcon name="run" size="xs" label="실행 중" />
            실행 중
          </span>
        ) : null}
        {isNodeRunning && onStopWorkNode && node.uuid ? (
          <StopBox
            disabled={isStoppingUuid === node.uuid}
            onClick={() => {
              const label = (node.name || "").trim() || "이 작업노드";
              const confirmed = window.confirm(
                `"${label}" 실행을 중지하시겠습니까?\n해당 작업노드와 작업 워크플로우가 실패로 종료됩니다.`,
              );
              if (!confirmed) {
                return;
              }
              void (async () => {
                setIsStoppingUuid(node.uuid);
                setError(null);
                try {
                  await onStopWorkNode(node.uuid);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "작업노드를 중지하지 못했습니다.");
                } finally {
                  setIsStoppingUuid(null);
                }
              })();
            }}
          />
        ) : readOnly ? null : (
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
            <div className="flex min-w-0 items-center justify-between gap-2">
              {hasScript ? (
                <span className="inline-flex items-center" title="실행 결과 있음" aria-label="실행 결과 있음">
                  <WorkflowIcon name="approve" size="sm" label="실행 결과 있음" />
                </span>
              ) : (
                <TextLabelChip title="미실행">미실행</TextLabelChip>
              )}
              {isCronEnabled ? (
                <span
                  className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-amber-200/90"
                  title={scheduleLabel}
                >
                  <WorkflowIcon name="history" size="xs" label="스케줄" />
                  {scheduleLabel}
                </span>
              ) : null}
            </div>
          </div>
          {hasFile ? (
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] text-slate-500">첨부 유무</p>
              <span className="inline-flex items-center" title="첨부 있음" aria-label="첨부 있음">
                <WorkflowIcon name="upload" size="sm" label="첨부 있음" />
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
        <div className="flex min-w-0 gap-4">
          <div
            className={`min-w-0 ${
              showDiagramPromptPanel && cronEnabled ? "basis-[40%] flex-[2]" : "flex-1"
            }`}
          >
            <label className="grid gap-1 text-xs text-slate-400">
              작업 워크플로우 명
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={100}
                readOnly={readOnly}
                disabled={readOnly}
                className="min-w-0 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-80"
              />
            </label>
            <label className="mt-3 grid gap-1 text-xs text-slate-400">
              작업 워크플로우 설명
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                maxLength={500}
                rows={2}
                readOnly={readOnly}
                disabled={readOnly}
                placeholder="작업 워크플로우 메타 설명"
                className="resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-80"
              />
            </label>
          </div>

          {showDiagramPromptPanel ? (
          <div className={`min-w-0 ${cronEnabled ? "basis-[40%] flex-[2]" : "flex-1"}`}>
            <div className="grid gap-1 text-xs text-slate-400">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5">
                  <WorkflowIcon name="ai" size="sm" label="다이어그램 생성" />
                  다이어그램 생성 프롬프트
                </span>
                {diagramPanelState === "STATE_RESPONSE_SUCCESS" ? (
                  <button
                    type="button"
                    disabled={readOnly}
                    onClick={handleDiagramRegenerate}
                    className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-600 bg-slate-900 px-3 py-1 text-[11px] font-medium text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <WorkflowIcon name="quickstart" size="xs" />
                    다시생성하기
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={
                      isDiagramInputLocked ||
                      isLoadingTemplate ||
                      !onDiagramGenerate ||
                      (diagramPanelState === "STATE_RESPONSE_ADDITIONAL_DATA"
                        ? !workingPrompt.trim()
                        : !diagramPrompt.trim() || hasEmptyTemplateVars)
                    }
                    onClick={handleDiagramGenerate}
                    className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-600 bg-slate-900 px-3 py-1 text-[11px] font-medium text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                    title="대화형 터미널로 전송"
                  >
                    <WorkflowIcon name="ai" size="xs" />
                    {isDiagramBusy ? "생성 중…" : "생성"}
                  </button>
                )}
              </div>

              {diagramPanelState === "STATE_RESPONSE_SUCCESS" ? (
                <pre className="max-h-64 min-h-[7.5rem] overflow-auto rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-[11px] leading-5 text-emerald-100 whitespace-pre-wrap">
                  {diagramResultJson || "결과 JSON이 비어 있습니다."}
                </pre>
              ) : (
                <>
                  <select
                    value={selectedTemplate}
                    disabled={
                      isDiagramInputLocked ||
                      isLoadingTemplate ||
                      diagramPanelState !== "STATE_INPUT"
                    }
                    onChange={(event) => {
                      void handleTemplateSelect(event.target.value);
                    }}
                    className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 disabled:opacity-80"
                    aria-label="다이어그램 생성 양식"
                  >
                    <option value="">양식 선택</option>
                    {templateNames.map((templateName) => (
                      <option key={templateName} value={templateName}>
                        {templateName}
                      </option>
                    ))}
                  </select>

                  {diagramPanelState === "STATE_RESPONSE_ADDITIONAL_DATA" ||
                  (diagramPanelState === "STATE_GENERATE" &&
                    diagramStateBeforeGenerateRef.current ===
                      "STATE_RESPONSE_ADDITIONAL_DATA") ? (
                    <>
                      {clarifyMessages.length > 0 ? (
                        <div className="grid gap-2">
                          {clarifyMessages.map((message, index) => (
                            <div
                              key={`clarify-${index}`}
                              className="rounded-md border border-amber-800/70 bg-amber-950/30 px-3 py-2 text-xs leading-5 text-amber-100 whitespace-pre-wrap"
                            >
                              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-amber-300/90">
                                보완 질의 {clarifyMessages.length > 1 ? `#${index + 1}` : ""}
                              </p>
                              {message}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      <textarea
                        ref={clarifyPromptTextareaRef}
                        value={workingPrompt}
                        onChange={(event) => setWorkingPrompt(event.target.value)}
                        disabled={isDiagramInputLocked}
                        rows={8}
                        spellCheck={false}
                        className="w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-[12px] leading-5 text-slate-200 disabled:opacity-80"
                        aria-label="보완질의 반영 프롬프트"
                      />
                    </>
                  ) : (
                    <>
                      <WorkflowTemplatePromptField
                        value={diagramPrompt}
                        onChange={handleDiagramPromptChange}
                        disabled={isDiagramInputLocked}
                        placeholder="양식을 선택하거나 클릭하여 편집하세요"
                        rows={8}
                      />
                      {templateVarNames.length > 0 ? (
                        <TemplateVariableInputs
                          varNames={templateVarNames}
                          values={templateVarValues}
                          locked={isDiagramInputLocked}
                          onChange={(varName, value) => {
                            setTemplateVarValues((current) => ({
                              ...current,
                              [varName]: value,
                            }));
                          }}
                        />
                      ) : null}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
          ) : null}

          <div
            className={`min-w-0 ${
              cronEnabled
                ? showDiagramPromptPanel
                  ? "basis-[20%] flex-1"
                  : "w-[30%] shrink-0"
                : "w-auto shrink-0 self-start"
            }`}
          >
            <WorkflowScheduleField
              enabled={cronEnabled}
              cronExpr={cronExpr}
              readOnly={readOnly}
              onChange={({ enabled, cronExpr: nextExpr }) => {
                setCronEnabled(enabled);
                setCronExpr(nextExpr);
              }}
            />
          </div>
        </div>
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
                      renderApproverCard(
                        step.clientId,
                        step.username,
                        step.userid,
                        Boolean(step.upload),
                      )
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
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium ${
                    bottomTab === "results"
                      ? "bg-slate-800 text-slate-100"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  <WorkflowIcon name="history" size="xs" label="작업결과" />
                  작업 워크플로우 작업결과
                </button>
                <button
                  type="button"
                  onClick={() => setBottomTab("work-results")}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium ${
                    bottomTab === "work-results"
                      ? "bg-slate-800 text-slate-100"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  <WorkflowIcon name="result" size="xs" label="작업 결과" />
                  작업 결과
                </button>
                <button
                  type="button"
                  onClick={() => setBottomTab("edit")}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium ${
                    bottomTab === "edit"
                      ? "bg-slate-800 text-slate-100"
                      : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  <WorkflowIcon name="edit" size="xs" label="작업 편집" />
                  작업 편집
                </button>
              </header>
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                {bottomTab === "results" ? (
                  workflowUuid ? (
                    <WorkflowHistoryPanel workflowUuid={workflowUuid} />
                  ) : (
                    <div className="flex h-full items-center justify-center p-4 text-[11px] text-slate-500">
                      작업 워크플로우를 선택하면 작업결과를 확인할 수 있습니다.
                    </div>
                  )
                ) : bottomTab === "work-results" ? (
                  <WorkNodeResultsPanel
                    workNodes={workflowWorkNodes.map((node) => ({
                      uuid: node.uuid,
                      name: node.name,
                      validateDate: node.validateDate,
                      lastEndDate: node.lastEndDate,
                      lastSuccess: node.lastSuccess,
                    }))}
                    selectedWorkUuid={selectedWorkNode?.uuid?.trim() || null}
                  />
                ) : selectedHitlNode && !readOnly ? (
                  <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4 text-[11px] text-slate-300">
                    <p className="inline-flex items-center gap-1.5">
                      <WorkflowIcon name="approve" size="sm" />
                      <span className="text-slate-500">승인 노드</span>{" "}
                      {selectedHitlNode.name || selectedHitlNode.uuid}
                    </p>
                    <p className="inline-flex items-center gap-1.5">
                      <WorkflowIcon name="owner" size="sm" />
                      <span className="text-slate-500">승인자</span>{" "}
                      {selectedHitlNode.username || selectedHitlNode.userid || "(미지정)"}
                    </p>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={Boolean(selectedHitlNode.upload)}
                        onChange={(event) => {
                          const upload = event.target.checked;
                          const next: HitlEditorNode = { ...selectedHitlNode, upload };
                          setModel((current) => ({
                            ...current,
                            main: current.main.map((step) =>
                              step.clientId === selectedHitlNode.clientId && step.type === "hitl"
                                ? next
                                : step,
                            ),
                          }));
                          if (selectedHitlNode.uuid) {
                            void fetch(`/api/work-nodes/${selectedHitlNode.uuid}`, {
                              method: "PUT",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify(hitlNodeWriteBody(next)),
                            }).then(async (response) => {
                              if (!response.ok) {
                                setError(
                                  await parseError(response, "승인 노드를 저장하지 못했습니다."),
                                );
                                return;
                              }
                              await onWorkNodesChanged();
                            });
                          }
                        }}
                      />
                      <WorkflowIcon name="upload" size="sm" />
                      승인 시 파일 업로드 필수
                    </label>
                  </div>
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

      {approverPickClientId ? (
        <WorkflowApproverPickModal
          approvers={approvers}
          initialUserid={
            (
              model.main.find(
                (step) => step.clientId === approverPickClientId && step.type === "hitl",
              ) as { userid?: string } | undefined
            )?.userid || ""
          }
          onClose={() => setApproverPickClientId(null)}
          onConfirm={({ userid, username }) => {
            const clientId = approverPickClientId;
            setModel((current) => ({
              ...current,
              main: current.main.map((step) =>
                step.clientId === clientId && step.type === "hitl"
                  ? { ...step, userid, username }
                  : step,
              ),
            }));
            const step = model.main.find(
              (item) => item.clientId === clientId && item.type === "hitl",
            ) as HitlEditorNode | undefined;
            if (step?.uuid) {
              const next: HitlEditorNode = { ...step, userid, username };
              void fetch(`/api/work-nodes/${step.uuid}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(hitlNodeWriteBody(next)),
              }).then(async (response) => {
                if (!response.ok) {
                  setError(await parseError(response, "승인 노드를 저장하지 못했습니다."));
                  return;
                }
                await onWorkNodesChanged();
              });
            }
          }}
        />
      ) : null}
    </div>
  );
});
