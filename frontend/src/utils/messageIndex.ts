const MESSAGE_COUNTER_KEY = "project-a-message-counter";

export { formatMessageIndex, formatResponseTimestamp } from "./datetime";

export function getNextMessageNumber(agentId: string): number {
  try {
    const raw = localStorage.getItem(MESSAGE_COUNTER_KEY);
    const counters = raw ? (JSON.parse(raw) as Record<string, number>) : {};
    const next = (counters[agentId] ?? 0) + 1;
    counters[agentId] = next;
    localStorage.setItem(MESSAGE_COUNTER_KEY, JSON.stringify(counters));
    return next;
  } catch {
    return 1;
  }
}
