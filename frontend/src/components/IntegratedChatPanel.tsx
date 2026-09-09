import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AgentInfo, IntegratedChatResponse, ToolUsage } from "../types/agent";
import type { AuthUser } from "../types/auth";
import { appendInputHistory, loadInputHistory } from "../utils/inputHistory";
import { formatResponseTimestamp } from "../utils/messageIndex";
import { flushSseBuffer, parseSseChunk } from "../utils/parseSse";
import { createSessionId, isUuidSessionId } from "../utils/sessionId";
import { AssistantMessageContent } from "./AssistantMessageContent";
import { CollapsibleUserMessage } from "./CollapsibleUserMessage";
import { JobIntakePanel } from "./JobIntakePanel";
import { OpenAiBillingConfirmDialog } from "./OpenAiBillingConfirmDialog";
import { ToolUsageList } from "./ToolUsageList";
import { fetchLlmBillingStatus } from "../utils/llmBilling";

interface IntegratedChatPanelProps {
  agents: AgentInfo[];
  user: AuthUser;
  isFullscreen: boolean;
  panelWidth?: number;
  onToggleFullscreen: () => void;
  onChatComplete?: () => void;
  onCopyToNote?: (content: string, noteName?: string) => Promise<void>;
  /** When set, only these agent IDs appear (ignores chat_enabled / assignment filters). */
  allowedAgentIds?: string[];
  /** Fill the composer and submit once (nonce must change each request). */
  externalSubmitRequest?: { nonce: number; message: string } | null;
  onExternalSubmitHandled?: () => void;
  /** Fired when an external submit is discarded (e.g. billing cancel) before chat starts. */
  onExternalSubmitAborted?: () => void;
  /** Fired after a successful assistant reply (not abort/error). */
  onAssistantResponse?: (payload: { agentId: string; content: string }) => void;
  /** Fired when a chat attempt finishes (success, error, or abort). */
  onChatSettled?: (payload: { agentId: string; ok: boolean; content: string }) => void;
  /** Expand user message input height for workflow terminal (fixed px; dashboard keeps default). */
  expandUserInput?: boolean;
  /** Fixed user input height when expandUserInput is true. Default 300. */
  userInputHeightPx?: number;
}

function createResponseId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="1" />
    </svg>
  );
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

const DEFAULT_AGENT_LIST_HEIGHT = 160;
const MIN_AGENT_LIST_HEIGHT = 80;
const FIXED_USER_INPUT_HEIGHT = 100;
const MIN_CONVERSATION_HEIGHT = 120;
const RESIZE_HANDLE_HEIGHT = 8;
const CHAT_HEADER_HEIGHT = 100;
/** Form padding (p-3 ×2) + gap between agent list and input (gap-2) */
const COMPOSER_FORM_CHROME = 24 + 8;
/** 대화창에 유지·렌더링할 최근 질의/응답 쌍 개수 */
const VISIBLE_CHAT_RESPONSE_LIMIT = 10;

type TerminalContentTab = "chat" | "job-intake";

const CONTENT_TABS: { id: TerminalContentTab; label: string }[] = [
  { id: "chat", label: "대화창" },
  { id: "job-intake", label: "작업접수" },
];

function keepRecentResponses(entries: IntegratedChatResponse[]): IntegratedChatResponse[] {
  if (entries.length <= VISIBLE_CHAT_RESPONSE_LIMIT) {
    return entries;
  }
  return entries.slice(-VISIBLE_CHAT_RESPONSE_LIMIT);
}

interface UserCommLogEntry {
  timestamp: string;
  agent_id: string;
  agent_name: string;
  user_message: string;
  assistant_message: string;
  tools: ToolUsage[];
}

function mapLogEntryToResponse(entry: UserCommLogEntry, index: number): IntegratedChatResponse {
  return {
    id: `${entry.timestamp}-${index}`,
    agentId: entry.agent_id,
    agentName: entry.agent_name,
    userContent: entry.user_message,
    assistantContent: entry.assistant_message,
    toolsUsed: entry.tools ?? [],
    createdAt: entry.timestamp,
  };
}

export function IntegratedChatPanel({
  agents,
  user,
  isFullscreen,
  panelWidth = 650,
  onToggleFullscreen,
  onChatComplete,
  onCopyToNote,
  allowedAgentIds,
  externalSubmitRequest = null,
  onExternalSubmitHandled,
  onExternalSubmitAborted,
  onAssistantResponse,
  onChatSettled,
  expandUserInput = false,
  userInputHeightPx = 300,
}: IntegratedChatPanelProps) {
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [input, setInput] = useState("");
  const [responses, setResponses] = useState<IntegratedChatResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [inputHistory, setInputHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [sessionId, setSessionId] = useState(createSessionId);
  const [billingConfirmPrompt, setBillingConfirmPrompt] = useState<string | null>(null);
  const [billingConfirmModel, setBillingConfirmModel] = useState<string | null>(null);
  const [copyingResponseId, setCopyingResponseId] = useState<string | null>(null);
  const [contentTab, setContentTab] = useState<TerminalContentTab>("chat");
  const conversationScrollRef = useRef<HTMLDivElement>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const processedExternalNonceRef = useRef<number | null>(null);
  const sendChatMessageRef = useRef<(trimmed: string) => Promise<boolean>>(async () => false);
  const [agentListHeight, setAgentListHeight] = useState(DEFAULT_AGENT_LIST_HEIGHT);
  const isResizingRef = useRef(false);
  const resizeStartYRef = useRef(0);
  const resizeStartHeightRef = useRef(DEFAULT_AGENT_LIST_HEIGHT);

  const clampAgentListHeight = useCallback((nextHeight: number) => {
    const layoutHeight = layoutRef.current?.clientHeight ?? window.innerHeight;
    const maxAgentListHeight = Math.max(
      MIN_AGENT_LIST_HEIGHT,
      layoutHeight
        - CHAT_HEADER_HEIGHT
        - MIN_CONVERSATION_HEIGHT
        - RESIZE_HANDLE_HEIGHT
        - FIXED_USER_INPUT_HEIGHT
        - COMPOSER_FORM_CHROME,
    );
    return Math.min(maxAgentListHeight, Math.max(MIN_AGENT_LIST_HEIGHT, nextHeight));
  }, []);

  useEffect(() => {
    setSessionId((current) => (isUuidSessionId(current) ? current : createSessionId()));
  }, []);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isResizingRef.current) {
        return;
      }
      const deltaY = event.clientY - resizeStartYRef.current;
      setAgentListHeight(clampAgentListHeight(resizeStartHeightRef.current - deltaY));
    };

    const handleMouseUp = () => {
      if (!isResizingRef.current) {
        return;
      }
      isResizingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [clampAgentListHeight]);

  useEffect(() => {
    const node = layoutRef.current;
    if (!node) {
      return;
    }

    const onLayoutResize = () => {
      setAgentListHeight((current) => clampAgentListHeight(current));
    };

    const observer = new ResizeObserver(() => {
      window.requestAnimationFrame(onLayoutResize);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [clampAgentListHeight]);

  const handleAgentListResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    isResizingRef.current = true;
    resizeStartYRef.current = event.clientY;
    resizeStartHeightRef.current = agentListHeight;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  };

  const chatAgents = useMemo(() => {
    if (allowedAgentIds && allowedAgentIds.length > 0) {
      const allowed = new Set(allowedAgentIds.map((id) => id.trim()).filter(Boolean));
      const matched = agents.filter((agent) => allowed.has(agent.id));
      // Preserve allowedAgentIds order when possible
      const byId = new Map(matched.map((agent) => [agent.id, agent]));
      const ordered = allowedAgentIds
        .map((id) => byId.get(id.trim()))
        .filter((agent): agent is AgentInfo => Boolean(agent));
      return ordered;
    }
    const assignedIds = new Set(
      (user.agent_ids ?? []).map((id) => id.trim()).filter(Boolean),
    );
    const enabled = agents.filter((agent) => {
      if (agent.chat_enabled !== true) {
        return false;
      }
      return assignedIds.has(agent.id);
    });
    return [...enabled].sort((left, right) => left.name.localeCompare(right.name, "ko"));
  }, [agents, allowedAgentIds, user.agent_ids]);

  const selectedAgent = useMemo(
    () => chatAgents.find((agent) => agent.id === selectedAgentId) ?? null,
    [chatAgents, selectedAgentId],
  );

  const isDisabled = !selectedAgent || selectedAgent.status === "disabled";

  useEffect(() => {
    let cancelled = false;

    const loadChatHistory = async () => {
      try {
        const response = await fetch(`/api/chat/logs/${encodeURIComponent(user.userid)}`);
        if (!response.ok) {
          return;
        }

        const payload = (await response.json()) as {
          entries?: UserCommLogEntry[];
        };
        if (cancelled) {
          return;
        }

        const restored = (payload.entries ?? []).map(mapLogEntryToResponse);
        setResponses(keepRecentResponses(restored));
      } catch {
        if (!cancelled) {
          setResponses([]);
        }
      }
    };

    void loadChatHistory();
    return () => {
      cancelled = true;
    };
  }, [user.userid]);

  useEffect(() => {
    if (chatAgents.length === 0) {
      setSelectedAgentId("");
      return;
    }

    setSelectedAgentId((current) => {
      if (current && chatAgents.some((agent) => agent.id === current)) {
        return current;
      }
      return chatAgents[0]?.id ?? "";
    });
  }, [chatAgents]);

  useEffect(() => {
    if (!selectedAgentId) {
      setInputHistory([]);
      setHistoryIndex(-1);
      return;
    }

    let cancelled = false;
    setHistoryIndex(-1);
    void loadInputHistory(selectedAgentId).then((history) => {
      if (!cancelled) {
        setInputHistory(history);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [selectedAgentId]);

  const responseScrollKey = useMemo(
    () =>
      responses
        .map((response) => `${response.userContent}\0${response.assistantContent}`)
        .join("\0"),
    [responses],
  );

  useEffect(() => {
    conversationScrollRef.current?.scrollTo({
      top: conversationScrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [responseScrollKey]);

  const updateLastResponse = (content: string, toolsUsed?: ToolUsage[]) => {
    setResponses((prev) => {
      if (prev.length === 0) {
        return prev;
      }
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = {
        ...last,
        assistantContent: content,
        toolsUsed: toolsUsed ?? last.toolsUsed,
      };
      return next;
    });
  };

  const handlePreviousMessage = () => {
    if (inputHistory.length === 0) {
      return;
    }

    const nextIndex = historyIndex === -1 ? inputHistory.length - 1 : Math.max(0, historyIndex - 1);
    setHistoryIndex(nextIndex);
    setInput(inputHistory[nextIndex] ?? "");
  };

  const handleNextMessage = () => {
    if (inputHistory.length === 0 || historyIndex === -1) {
      return;
    }

    if (historyIndex >= inputHistory.length - 1) {
      setHistoryIndex(-1);
      setInput("");
      return;
    }

    const nextIndex = historyIndex + 1;
    setHistoryIndex(nextIndex);
    setInput(inputHistory[nextIndex] ?? "");
  };

  const handleInputChange = (value: string) => {
    setInput(value);
    if (historyIndex !== -1) {
      setHistoryIndex(-1);
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
  };

  const handleResetSession = () => {
    abortControllerRef.current?.abort();
    setSessionId(createSessionId());
    setResponses([]);
    setInput("");
    setHistoryIndex(-1);
  };

  const sendChatMessage = async (trimmed: string): Promise<boolean> => {
    if (!selectedAgent || isLoading) {
      return false;
    }

    const agentId = selectedAgent.id;
    const nextHistory = await appendInputHistory(agentId, trimmed);
    setInputHistory(nextHistory);
    setHistoryIndex(-1);
    setInput("");
    setIsLoading(true);

    const createdAt = new Date().toISOString();
    const responseId = createResponseId();
    setResponses((prev) =>
      keepRecentResponses([
        ...prev,
        {
          id: responseId,
          agentId,
          agentName: selectedAgent.name,
          userContent: trimmed,
          assistantContent: "",
          toolsUsed: [],
          createdAt,
        },
      ]),
    );

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    let assistantText = "";
    let toolsUsed: ToolUsage[] = [];
    let completedOk = false;

    try {
      const response = await fetch(`/api/agents/${agentId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          userid: user.userid,
          session_id: sessionId,
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Streaming response unavailable");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      const applyEvents = (events: ReturnType<typeof parseSseChunk>["events"]) => {
        for (const event of events) {
          if (!event.data) {
            continue;
          }

          if (event.event === "tools") {
            const payload = JSON.parse(event.data) as { tools: ToolUsage[] };
            toolsUsed = payload.tools ?? [];
            updateLastResponse(assistantText, toolsUsed);
            continue;
          }

          if (event.event === "token") {
            const payload = JSON.parse(event.data) as { content: string };
            assistantText += payload.content;
            updateLastResponse(assistantText, toolsUsed);
            continue;
          }

          if (event.event === "done") {
            const payload = JSON.parse(event.data) as { tools?: ToolUsage[] };
            if (payload.tools) {
              toolsUsed = payload.tools;
            }
            updateLastResponse(assistantText, toolsUsed);
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (value) {
          const parsed = parseSseChunk(buffer, decoder.decode(value, { stream: true }));
          buffer = parsed.remainder;
          applyEvents(parsed.events);
        }

        if (done) {
          applyEvents(flushSseBuffer(buffer));
          break;
        }
      }
      completedOk = Boolean(assistantText.trim());
    } catch (err) {
      if (isAbortError(err)) {
        updateLastResponse("요청이 취소되었습니다.", toolsUsed);
      } else {
        const message = err instanceof Error ? err.message : "Unknown error";
        updateLastResponse(`오류: ${message}`, []);
      }
    } finally {
      abortControllerRef.current = null;
      setIsLoading(false);
      onChatComplete?.();
      if (completedOk) {
        onAssistantResponse?.({ agentId, content: assistantText.trim() });
      }
      onChatSettled?.({
        agentId,
        ok: completedOk,
        content: assistantText.trim(),
      });
    }
    return true;
  };

  sendChatMessageRef.current = sendChatMessage;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading || !selectedAgent) {
      return;
    }

    try {
      const billingStatus = await fetchLlmBillingStatus();
      if (billingStatus.requires_confirmation) {
        setBillingConfirmModel(billingStatus.model);
        setBillingConfirmPrompt(trimmed);
        return;
      }
    } catch {
      // 상태 조회 실패 시 로컬 LLM으로 간주하고 기존 흐름 유지
    }

    await sendChatMessage(trimmed);
  };

  useEffect(() => {
    if (!externalSubmitRequest) {
      return;
    }
    if (processedExternalNonceRef.current === externalSubmitRequest.nonce) {
      return;
    }
    // Wait until idle so we never consume the request without attempting send.
    if (!selectedAgent || isLoading) {
      return;
    }

    const trimmed = externalSubmitRequest.message.trim();
    processedExternalNonceRef.current = externalSubmitRequest.nonce;
    onExternalSubmitHandled?.();

    if (!trimmed) {
      onExternalSubmitAborted?.();
      return;
    }

    setContentTab("chat");
    setInput(trimmed);

    const submitExternal = async () => {
      try {
        const billingStatus = await fetchLlmBillingStatus();
        if (billingStatus.requires_confirmation) {
          setBillingConfirmModel(billingStatus.model);
          setBillingConfirmPrompt(trimmed);
          return;
        }
      } catch {
        // keep going
      }
      const started = await sendChatMessageRef.current(trimmed);
      if (!started) {
        onExternalSubmitAborted?.();
      }
    };

    void submitExternal();
  }, [
    externalSubmitRequest,
    selectedAgent,
    isLoading,
    onExternalSubmitHandled,
    onExternalSubmitAborted,
  ]);

  const handleBillingConfirm = () => {
    if (!billingConfirmPrompt) {
      return;
    }
    const prompt = billingConfirmPrompt;
    setBillingConfirmPrompt(null);
    setBillingConfirmModel(null);
    void sendChatMessage(prompt).then((started) => {
      if (!started) {
        onExternalSubmitAborted?.();
      }
    });
  };

  const handleBillingCancel = () => {
    setBillingConfirmPrompt(null);
    setBillingConfirmModel(null);
    onExternalSubmitAborted?.();
  };

  const canShowPrevious = inputHistory.length > 0;
  const canShowNext = historyIndex !== -1;

  const handleCopyResponseToNote = async (response: IntegratedChatResponse) => {
    if (!onCopyToNote || !response.assistantContent.trim()) {
      return;
    }

    setCopyingResponseId(response.id);
    try {
      const noteName = `${response.agentName} ${formatResponseTimestamp(new Date(response.createdAt))}`.slice(
        0,
        50,
      );
      await onCopyToNote(response.assistantContent, noteName);
    } finally {
      setCopyingResponseId(null);
    }
  };

  return (
    <aside
      ref={layoutRef}
      style={isFullscreen ? undefined : { width: panelWidth }}
      className={`flex self-stretch flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg ${
        isFullscreen ? "min-h-0 w-full" : "min-h-0 shrink-0"
      }`}
    >
      <header className="flex h-[100px] shrink-0 items-center justify-between border-b border-slate-700 px-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-slate-100">대화형 터미널</h2>
          <p className="mt-1 text-sm text-slate-400">에이전트를 선택해 메시지를 전송하세요.</p>
        </div>
        <button
          type="button"
          onClick={onToggleFullscreen}
          title={isFullscreen ? "원복" : "전체화면"}
          className="shrink-0 rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
        >
          {isFullscreen ? "원복" : "전체화면"}
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-700 px-3 pt-2">
          {CONTENT_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setContentTab(tab.id)}
              className={`shrink-0 rounded-t-md px-3 py-2 text-xs font-medium ${
                contentTab === tab.id
                  ? "border border-b-0 border-slate-600 bg-slate-800 text-sky-200"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-1 px-3 pt-2">
          {contentTab === "chat" ? (
            <>
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-medium tracking-wide text-slate-300">대화 내용</div>
                <button
                  type="button"
                  onClick={handleResetSession}
                  disabled={isLoading}
                  title="에이전트 호출 세션 UUID를 새로 생성합니다"
                  className="shrink-0 rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  세션 초기화
                </button>
              </div>
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-800 bg-slate-950/50 text-sm">
                <div
                  ref={conversationScrollRef}
                  className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain p-2"
                >
                  {responses.length === 0 ? (
                    <p className="text-slate-500">대화 내용이 여기에 표시됩니다.</p>
                  ) : null}

                  {responses.map((response) => (
                    <div key={response.id} className="space-y-2">
                      <CollapsibleUserMessage
                        content={response.userContent}
                        createdAt={response.createdAt}
                      />
                      <div className="rounded-md border border-emerald-800/40 bg-emerald-950/35 px-2 py-2 text-slate-100 break-words">
                        <div className="mb-1 flex items-start justify-between gap-2">
                          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[10px] leading-tight text-emerald-300/80">
                            <span className="rounded-full border border-emerald-700/50 bg-emerald-950/60 px-2 py-0.5 text-emerald-200">
                              {response.agentName}
                            </span>
                            <span>{formatResponseTimestamp(new Date(response.createdAt))}</span>
                          </div>
                          {response.assistantContent && onCopyToNote ? (
                            <button
                              type="button"
                              disabled={copyingResponseId === response.id}
                              onClick={() => void handleCopyResponseToNote(response)}
                              className="shrink-0 rounded-md border border-slate-600 bg-slate-900/80 px-2 py-0.5 text-[10px] font-medium text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {copyingResponseId === response.id ? "복사 중..." : "노트로 복사"}
                            </button>
                          ) : null}
                        </div>
                        <ToolUsageList tools={response.toolsUsed} />
                        {response.assistantContent ? (
                          <AssistantMessageContent content={response.assistantContent} />
                        ) : (
                          <span className="text-slate-500">응답 생성 중...</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-800 bg-slate-950/50 text-sm">
              <JobIntakePanel user={user} />
            </div>
          )}
        </div>

        {contentTab === "chat" ? (
          <>
        <div
          role="separator"
          aria-orientation="horizontal"
          aria-label="대화창과 에이전트 목록 높이 조절"
          aria-valuenow={Math.round(agentListHeight)}
          aria-valuemin={MIN_AGENT_LIST_HEIGHT}
          onMouseDown={handleAgentListResizeStart}
          className="group flex h-2 shrink-0 cursor-row-resize items-center justify-center border-y border-slate-700 bg-slate-900 hover:bg-slate-800"
        >
          <span className="h-1 w-12 rounded-full bg-slate-600 group-hover:bg-slate-400" />
        </div>

        <form onSubmit={handleSubmit} className="flex shrink-0 flex-col gap-2 p-3">
          <div
            className={
              expandUserInput
                ? "flex shrink-0 flex-col gap-1 text-xs text-slate-400"
                : "flex min-h-0 shrink-0 flex-col gap-1 text-xs text-slate-400"
            }
            style={expandUserInput ? undefined : { height: agentListHeight }}
          >
            <span>에이전트</span>
            {chatAgents.length === 0 ? (
              <p className="min-h-0 flex-1 rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm text-slate-500">
                등록된 에이전트 없음
              </p>
            ) : (
              <div
                className={
                  expandUserInput
                    ? "rounded-md border border-slate-800 bg-slate-950/40 p-2"
                    : "min-h-0 flex-1 overflow-y-auto rounded-md border border-slate-800 bg-slate-950/40 p-2"
                }
                role="radiogroup"
                aria-label="에이전트 선택"
              >
                <div className="flex flex-wrap gap-1.5">
                  {chatAgents.map((agent) => {
                    const isSelected = selectedAgentId === agent.id;
                    return (
                      <button
                        key={agent.id}
                        type="button"
                        role="radio"
                        aria-checked={isSelected}
                        disabled={isLoading}
                        title={`${agent.name} (${agent.status})`}
                        onClick={() => setSelectedAgentId(agent.id)}
                        className={`rounded-md border px-2.5 py-1 text-left text-xs transition disabled:cursor-not-allowed disabled:opacity-50 ${
                          isSelected
                            ? "border-sky-500 bg-sky-950/70 text-sky-100"
                            : "border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-500 hover:bg-slate-800"
                        }`}
                      >
                        <span className="font-medium">{agent.name}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div
            className="flex shrink-0 gap-2"
            style={{
              height: expandUserInput ? userInputHeightPx : FIXED_USER_INPUT_HEIGHT,
            }}
          >
            <div className="flex h-full shrink-0 flex-col gap-1">
              <button
                type="button"
                onClick={handlePreviousMessage}
                disabled={isDisabled || isLoading || !canShowPrevious}
                title="이전 메시지 (최대 10개)"
                className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-slate-700 bg-slate-900 px-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:text-slate-500"
              >
                ↑
              </button>
              <button
                type="button"
                onClick={handleNextMessage}
                disabled={isDisabled || isLoading || !canShowNext}
                title="다음 메시지"
                className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-slate-700 bg-slate-900 px-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:text-slate-500"
              >
                ↓
              </button>
            </div>
            <textarea
              value={input}
              onChange={(event) => handleInputChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                  return;
                }
                if (event.key === "ArrowUp" && !event.shiftKey) {
                  event.preventDefault();
                  handlePreviousMessage();
                  return;
                }
                if (event.key === "ArrowDown" && !event.shiftKey) {
                  if (historyIndex === -1) {
                    return;
                  }
                  event.preventDefault();
                  handleNextMessage();
                }
              }}
              placeholder={
                !selectedAgent
                  ? "에이전트를 선택하세요..."
                  : isDisabled
                    ? "MCP 연결 대기 중..."
                    : "메시지 입력..."
              }
              disabled={isDisabled || isLoading}
              className="min-h-0 flex-1 resize-none rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-sky-500"
            />
            {isLoading ? (
              <button
                type="button"
                onClick={handleStop}
                title="응답 중단"
                aria-label="응답 중단"
                className="flex items-center justify-center self-stretch rounded-md bg-rose-600 px-3 py-2 text-white hover:bg-rose-500"
              >
                <StopIcon />
              </button>
            ) : (
              <button
                type="submit"
                disabled={isDisabled || !input.trim()}
                className="self-stretch rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                전송
              </button>
            )}
          </div>
        </form>
          </>
        ) : null}
      </div>
      {billingConfirmPrompt ? (
        <OpenAiBillingConfirmDialog
          prompt={billingConfirmPrompt}
          model={billingConfirmModel}
          onConfirm={handleBillingConfirm}
          onCancel={handleBillingCancel}
        />
      ) : null}
    </aside>
  );
}
