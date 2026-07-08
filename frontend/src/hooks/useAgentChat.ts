import { useCallback, useState } from "react";

import type { ChatMessage } from "../types/agent";
import { flushSseBuffer, parseSseChunk } from "../utils/parseSse";

interface UseAgentChatResult {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (agentId: string, message: string) => Promise<void>;
  clearMessages: () => void;
}

export function useAgentChat(): UseAgentChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (agentId: string, message: string) => {
    setIsLoading(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: message }]);

    try {
      const response = await fetch(`/api/agents/${agentId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("Streaming response body is empty");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantText = "";

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      const applyTokenEvents = (events: ReturnType<typeof parseSseChunk>["events"]) => {
        for (const event of events) {
          if (event.event !== "token") {
            continue;
          }

          const payload = JSON.parse(event.data) as { content: string };
          assistantText += payload.content;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { role: "assistant", content: assistantText };
            return next;
          });
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (value) {
          const parsed = parseSseChunk(buffer, decoder.decode(value, { stream: true }));
          buffer = parsed.remainder;
          applyTokenEvents(parsed.events);
        }

        if (done) {
          applyTokenEvents(flushSseBuffer(buffer));
          break;
        }
      }
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "Unknown error";
      setError(messageText);
      setMessages((prev) => [...prev, { role: "assistant", content: `오류: ${messageText}` }]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isLoading, error, sendMessage, clearMessages };
}
