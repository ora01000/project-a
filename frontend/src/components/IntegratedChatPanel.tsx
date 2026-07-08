import { useEffect, useMemo, useRef, useState } from "react";

import type { AgentInfo, IntegratedChatResponse, ToolUsage } from "../types/agent";
import { agentNodeId, LLM_NODE_ID, mcpNodeId } from "../types/topology";
import { useTopology } from "../context/TopologyContext";
import { appendInputHistory, loadInputHistory } from "../utils/inputHistory";
import { formatResponseTimestamp } from "../utils/messageIndex";
import { flushSseBuffer, parseSseChunk } from "../utils/parseSse";
import { AssistantMessageContent } from "./AssistantMessageContent";
import { ToolUsageList } from "./ToolUsageList";

interface IntegratedChatPanelProps {
  agents: AgentInfo[];
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
}

function createResponseId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function IntegratedChatPanel({
  agents,
  isFullscreen,
  onToggleFullscreen,
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

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId) ?? null,
    [agents, selectedAgentId],
  );

  const isDisabled = !selectedAgent || selectedAgent.status === "disabled";

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
    () => responses.map((response) => response.assistantContent).join("\0"),
    [responses],
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

    try {
      const response = await fetch(`/api/agents/${selectedAgent.id}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
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
      const message = err instanceof Error ? err.message : "Unknown error";
      updateLastResponse(`오류: ${message}`, []);
    } finally {
      setIsLoading(false);
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
            {responses.length === 0 ? (
              <p className="text-slate-500">에이전트 응답이 여기에 표시됩니다.</p>
            ) : (
              responses.map((response) => (
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
              ))
            )}
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
            <button
              type="submit"
              disabled={isDisabled || isLoading || !input.trim()}
              className="rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {isLoading ? "..." : "전송"}
            </button>
          </div>
        </form>
      </div>
    </aside>
  );
}
