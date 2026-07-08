import { useEffect, useMemo, useRef, useState } from "react";

import type { ChatTurn, ToolUsage } from "../types/agent";
import { agentNodeId, LLM_NODE_ID, mcpNodeId } from "../types/topology";
import { useTopology } from "../context/TopologyContext";
import { appendInputHistory, loadInputHistory } from "../utils/inputHistory";
import { getNextMessageNumber } from "../utils/messageIndex";
import { flushSseBuffer, parseSseChunk } from "../utils/parseSse";
import { AssistantMessageContent } from "./AssistantMessageContent";
import { MessageIndexLabel } from "./MessageIndexLabel";
import { ToolUsageList } from "./ToolUsageList";

interface ChatPanelProps {
  agentId: string;
  disabled?: boolean;
}

export function ChatPanel({ agentId, disabled = false }: ChatPanelProps) {
  const { emitFlow } = useTopology();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [inputHistory, setInputHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const userScrollRef = useRef<HTMLDivElement>(null);
  const assistantScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTurns([]);
    setInput("");
    setInputHistory(loadInputHistory(agentId));
    setHistoryIndex(-1);
  }, [agentId]);

  const userScrollKey = useMemo(
    () => turns.map((turn) => turn.userContent).join("\0"),
    [turns],
  );
  const assistantScrollKey = useMemo(
    () => turns.map((turn) => turn.assistantContent).join("\0"),
    [turns],
  );

  useEffect(() => {
    userScrollRef.current?.scrollTo({
      top: userScrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [userScrollKey]);

  useEffect(() => {
    assistantScrollRef.current?.scrollTo({
      top: assistantScrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [assistantScrollKey]);

  const updateLastTurnAssistant = (content: string, toolsUsed?: ToolUsage[]) => {
    setTurns((prev) => {
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
    if (!trimmed || isLoading || disabled) {
      return;
    }

    const nextHistory = appendInputHistory(agentId, trimmed);
    setInputHistory(nextHistory);
    setHistoryIndex(-1);
    setInput("");
    setIsLoading(true);
    emitFlow(agentNodeId(agentId), LLM_NODE_ID);

    const num = getNextMessageNumber(agentId);
    const createdAt = new Date().toISOString();
    setTurns((prev) => [
      ...prev,
      { num, createdAt, userContent: trimmed, assistantContent: "", toolsUsed: [] },
    ]);

    try {
      const response = await fetch(`/api/agents/${agentId}/chat`, {
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
                emitFlow(agentNodeId(agentId), mcpNodeId(tool.mcp_server));
              }
            }
            updateLastTurnAssistant(assistantText, toolsUsed);
            continue;
          }

          if (event.event === "token") {
            const payload = JSON.parse(event.data) as { content: string };
            assistantText += payload.content;
            updateLastTurnAssistant(assistantText, toolsUsed);
            continue;
          }

          if (event.event === "done") {
            const payload = JSON.parse(event.data) as { tools?: ToolUsage[] };
            if (payload.tools) {
              toolsUsed = payload.tools;
            }
            updateLastTurnAssistant(assistantText, toolsUsed);
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
      updateLastTurnAssistant(`오류: ${message}`, []);
    } finally {
      setIsLoading(false);
    }
  };

  const canShowPrevious = inputHistory.length > 0;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1">
        <div className="text-xs font-medium uppercase tracking-wide text-sky-300">User</div>
        <div
          ref={userScrollRef}
          className="h-[100px] space-y-2 overflow-y-auto overscroll-contain rounded-md border border-slate-800 bg-slate-950/70 p-2 text-sm"
        >
          {turns.length === 0 ? (
            <p className="text-slate-500">입력한 메시지가 여기에 표시됩니다.</p>
          ) : (
            turns.map((turn) => (
              <div key={`user-${turn.num}-${turn.createdAt}`} className="rounded-md bg-sky-900/40 px-2 py-1 text-sky-100">
                <MessageIndexLabel num={turn.num} createdAt={turn.createdAt} />
                <span className="whitespace-pre-wrap">{turn.userContent}</span>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1 border-t border-slate-700 pt-2">
        <div className="text-xs font-medium uppercase tracking-wide text-emerald-300">Assistant</div>
        <div
          ref={assistantScrollRef}
          className="h-[300px] max-h-[600px] min-h-[300px] resize-y space-y-2 overflow-y-auto overscroll-contain rounded-md border border-slate-800 bg-slate-900/70 p-2 text-sm"
        >
          {turns.length === 0 ? (
            <p className="text-slate-500">에이전트 응답이 여기에 표시됩니다.</p>
          ) : (
            turns.map((turn) => (
              <div
                key={`assistant-${turn.num}-${turn.createdAt}`}
                className="rounded-md bg-slate-800/80 px-2 py-2 text-slate-100"
              >
                <MessageIndexLabel num={turn.num} createdAt={turn.createdAt} />
                <ToolUsageList tools={turn.toolsUsed} />
                {turn.assistantContent ? (
                  <AssistantMessageContent content={turn.assistantContent} />
                ) : (
                  <span className="text-slate-500">응답 생성 중...</span>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={handlePreviousMessage}
          disabled={disabled || isLoading || !canShowPrevious}
          title="이전 메시지 (최대 10개)"
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:text-slate-500"
        >
          ↑
        </button>
        <input
          value={input}
          onChange={(event) => handleInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowUp" && !event.shiftKey) {
              event.preventDefault();
              handlePreviousMessage();
            }
          }}
          placeholder={disabled ? "MCP 연결 대기 중..." : "메시지 입력..."}
          disabled={disabled || isLoading}
          className="flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-sky-500"
        />
        <button
          type="submit"
          disabled={disabled || isLoading || !input.trim()}
          className="rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-700"
        >
          {isLoading ? "..." : "전송"}
        </button>
      </form>
    </div>
  );
}
