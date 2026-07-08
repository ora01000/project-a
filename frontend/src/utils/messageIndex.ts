const MESSAGE_COUNTER_KEY = "project-a-message-counter";

export function formatResponseTimestamp(date: Date): string {
  const year = String(date.getFullYear()).slice(-2);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");

  return `${year}년 ${month}월 ${day}일 ${hours}:${minutes}:${seconds}`;
}

export function formatMessageIndex(num: number, date: Date): string {
  const year = String(date.getFullYear()).slice(-2);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");

  return `${year}년 ${month}월 ${day}일 ${hours}:${minutes}:${seconds}-#${num}`;
}

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
