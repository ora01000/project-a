const MAX_INPUT_HISTORY = 10;

interface ChatInputHistoryResponse {
  messages?: string[];
}

function normalizeHistory(messages: string[] | undefined): string[] {
  if (!messages?.length) {
    return [];
  }
  return messages.filter((item) => item.trim()).slice(-MAX_INPUT_HISTORY);
}

export async function loadInputHistory(agentId: string): Promise<string[]> {
  const normalizedAgentId = agentId.trim();
  if (!normalizedAgentId) {
    return [];
  }

  try {
    const response = await fetch(`/api/chat/input-history/${encodeURIComponent(normalizedAgentId)}`);
    if (!response.ok) {
      return [];
    }
    const payload = (await response.json()) as ChatInputHistoryResponse;
    return normalizeHistory(payload.messages);
  } catch {
    return [];
  }
}

export async function appendInputHistory(agentId: string, message: string): Promise<string[]> {
  const normalizedAgentId = agentId.trim();
  const trimmed = message.trim();
  if (!normalizedAgentId || !trimmed) {
    return await loadInputHistory(normalizedAgentId);
  }

  try {
    const response = await fetch(`/api/chat/input-history/${encodeURIComponent(normalizedAgentId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: trimmed }),
    });
    if (!response.ok) {
      return await loadInputHistory(normalizedAgentId);
    }
    const payload = (await response.json()) as ChatInputHistoryResponse;
    return normalizeHistory(payload.messages);
  } catch {
    return await loadInputHistory(normalizedAgentId);
  }
}
