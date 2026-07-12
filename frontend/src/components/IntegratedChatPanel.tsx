import { useEffect, useMemo, useRef, useState } from "react";

import type { AgentInfo, IntegratedChatResponse, ToolUsage } from "../types/agent";
import type { AuthUser } from "../types/auth";
import { agentNodeId, LLM_NODE_ID, mcpNodeId } from "../types/topology";
import { useTopology } from "../context/TopologyContext";
import { appendInputHistory, loadInputHistory } from "../utils/inputHistory";
import { formatResponseTimestamp } from "../utils/messageIndex";
import { flushSseBuffer, parseSseChunk } from "../utils/parseSse";
import { AssistantMessageContent } from "./AssistantMessageContent";
import { JobNotificationCard } from "./jobs/JobNotificationCard";
import { SignupNotificationCard } from "./users/SignupNotificationCard";
import { ToolUsageList } from "./ToolUsageList";
import type { JobNotification } from "../types/job";
import type { SignupNotification } from "../types/signup";

interface IntegratedChatPanelProps {
  agents: AgentInfo[];
  user: AuthUser;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onChatComplete?: () => void;
  jobNotifications?: JobNotification[];
  signupNotifications?: SignupNotification[];
  onJobReview?: (jobIdx: number) => void;
  onJobApprove?: (jobIdx: number) => void;
  onJobPending?: (jobIdx: number) => void;
  onJobReject?: (jobIdx: number) => void;
  onSignupApprove?: (userIdx: number) => void;
  onSignupReject?: (userIdx: number, reason: string) => void;
  onSignupHold?: (notificationIdx: number) => void;
  isJobActionProcessing?: boolean;
  isSignupActionProcessing?: boolean;
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
  onToggleFullscreen,
  onChatComplete,
  jobNotifications = [],
  signupNotifications = [],
  onJobReview,
  onJobApprove,
  onJobPending,
  onJobReject,
  onSignupApprove,
  onSignupReject,
  onSignupHold,
  isJobActionProcessing = false,
  isSignupActionProcessing = false,
}: IntegratedChatPanelProps) {
  const { emitFlow } = useTopology();
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [input, setInput] = useState("");
  const [responses, setResponses] = useState<IntegratedChatResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [inputHistory, setInputHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const assistantScrollRef = useRef<HTMLDivElement>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId) ?? null,
    [agents, selectedAgentId],
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
        setResponses(restored);
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
    if (agents.length === 0) {
      setSelectedAgentId("");
      return;
    }

    setSelectedAgentId((current) => {
      if (current && agents.some((agent) => agent.id === current)) {
        return current;
      }
      return agents[0]?.id ?? "";
    });
  }, [agents]);

  useEffect(() => {
    if (!selectedAgentId) {
      setInputHistory([]);
      setHistoryIndex(-1);
      return;
    }

    setInputHistory(loadInputHistory(selectedAgentId));
    setHistoryIndex(-1);
  }, [selectedAgentId]);

  const assistantScrollKey = useMemo(
    () =>
      [
        jobNotifications.map((notification) => notification.idx).join(","),
        signupNotifications.map((notification) => notification.idx).join(","),
        responses.map((response) => response.assistantContent).join("\0"),
      ].join("\0"),
    [jobNotifications, signupNotifications, responses],
  );

  useEffect(() => {
    assistantScrollRef.current?.scrollTo({
      top: assistantScrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [assistantScrollKey]);

  useEffect(() => {
    const node = layoutRef.current;
    if (!node) {
      return;
    }

    const reflow = () => {
      if (assistantScrollRef.current) {
        assistantScrollRef.current.scrollTop = assistantScrollRef.current.scrollHeight;
      }
    };

    const observer = new ResizeObserver(() => {
      window.requestAnimationFrame(reflow);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

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

  const handleInputChange = (value: string) => {
    setInput(value);
    if (historyIndex !== -1) {
      setHistoryIndex(-1);
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading || !selectedAgent) {
      return;
    }

    const nextHistory = appendInputHistory(selectedAgent.id, trimmed);
    setInputHistory(nextHistory);
    setHistoryIndex(-1);
    setInput("");
    setIsLoading(true);
    emitFlow(agentNodeId(selectedAgent.id), LLM_NODE_ID);

    const createdAt = new Date().toISOString();
    const responseId = createResponseId();
    setResponses((prev) => [
      ...prev,
      {
        id: responseId,
        agentId: selectedAgent.id,
        agentName: selectedAgent.name,
        userContent: trimmed,
        assistantContent: "",
        toolsUsed: [],
        createdAt,
      },
    ]);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const response = await fetch(`/api/agents/${selectedAgent.id}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, userid: user.userid }),
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
      let assistantText = "";
      let toolsUsed: ToolUsage[] = [];

      const applyEvents = (events: ReturnType<typeof parseSseChunk>["events"]) => {
        for (const event of events) {
          if (!event.data) {
            continue;
          }

          if (event.event === "tools") {
            const payload = JSON.parse(event.data) as { tools: ToolUsage[] };
            toolsUsed = payload.tools ?? [];
            for (const tool of toolsUsed) {
              if (tool.mcp_server) {
                emitFlow(agentNodeId(selectedAgent.id), mcpNodeId(tool.mcp_server));
              }
            }
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
    } catch (err) {
      if (isAbortError(err)) {
        return;
      }
      const message = err instanceof Error ? err.message : "Unknown error";
      updateLastResponse(`오류: ${message}`, []);
    } finally {
      abortControllerRef.current = null;
      setIsLoading(false);
      onChatComplete?.();
    }
  };

  const canShowPrevious = inputHistory.length > 0;

  return (
    <aside
      ref={layoutRef}
      className={`flex self-stretch flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-lg ${
        isFullscreen ? "min-h-0 w-full" : "min-h-0 w-[500px] shrink-0"
      }`}
    >
      <header className="flex h-[100px] shrink-0 items-center justify-between border-b border-slate-700 px-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-slate-100">통합 채팅</h2>
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
        <div className="flex min-h-0 flex-1 flex-col gap-1 px-3 pt-3">
          <div className="text-xs font-medium uppercase tracking-wide text-emerald-300">Assistant</div>
          <div
            ref={assistantScrollRef}
            className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain rounded-md border border-slate-800 bg-slate-900/70 p-2 text-sm"
          >
            {jobNotifications.length === 0 && signupNotifications.length === 0 && responses.length === 0 ? (
              <p className="text-slate-500">에이전트 응답이 여기에 표시됩니다.</p>
            ) : null}

            {signupNotifications.map((notification) => (
              <SignupNotificationCard
                key={`signup-${notification.idx}`}
                notification={notification}
                isProcessing={isSignupActionProcessing}
                onApprove={(userIdx) => onSignupApprove?.(userIdx)}
                onReject={(userIdx, reason) => onSignupReject?.(userIdx, reason)}
                onHold={(notificationIdx) => onSignupHold?.(notificationIdx)}
              />
            ))}

            {jobNotifications.map((notification) => (
              <JobNotificationCard
                key={notification.idx}
                notification={notification}
                isProcessing={isJobActionProcessing}
                onReview={(jobIdx) => onJobReview?.(jobIdx)}
                onApprove={(jobIdx) => onJobApprove?.(jobIdx)}
                onPending={(jobIdx) => onJobPending?.(jobIdx)}
                onReject={(jobIdx) => onJobReject?.(jobIdx)}
              />
            ))}

            {responses.map((response) => (
                <div
                  key={response.id}
                  className="rounded-md bg-slate-800/80 px-2 py-2 text-slate-100 break-words"
                >
                  <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] leading-tight text-slate-400">
                    <span className="rounded-full border border-sky-700/60 bg-sky-950/50 px-2 py-0.5 text-sky-200">
                      {response.agentName}
                    </span>
                    <span>{formatResponseTimestamp(new Date(response.createdAt))}</span>
                  </div>
                  <ToolUsageList tools={response.toolsUsed} />
                  {response.assistantContent ? (
                    <AssistantMessageContent content={response.assistantContent} />
                  ) : (
                    <span className="text-slate-500">응답 생성 중...</span>
                  )}
                </div>
              ))}
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex h-[200px] shrink-0 flex-col gap-2 border-t border-slate-700 p-3"
        >
          <label className="flex flex-col gap-1 text-xs text-slate-400">
            <span>에이전트</span>
            <select
              value={selectedAgentId}
              onChange={(event) => setSelectedAgentId(event.target.value)}
              disabled={agents.length === 0 || isLoading}
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500"
            >
              {agents.length === 0 ? (
                <option value="">등록된 에이전트 없음</option>
              ) : (
                agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} ({agent.status})
                  </option>
                ))
              )}
            </select>
          </label>

          <div className="flex min-h-0 flex-1 gap-2">
            <button
              type="button"
              onClick={handlePreviousMessage}
              disabled={isDisabled || isLoading || !canShowPrevious}
              title="이전 메시지 (최대 10개)"
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:text-slate-500"
            >
              ↑
            </button>
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
                className="flex items-center justify-center rounded-md bg-rose-600 px-3 py-2 text-white hover:bg-rose-500"
              >
                <StopIcon />
              </button>
            ) : (
              <button
                type="submit"
                disabled={isDisabled || !input.trim()}
                className="rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                전송
              </button>
            )}
          </div>
        </form>
      </div>
    </aside>
  );
}
