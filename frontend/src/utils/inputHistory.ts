const INPUT_HISTORY_KEY = "project-a-input-history";
const MAX_INPUT_HISTORY = 10;

export function loadInputHistory(agentId: string): string[] {
  try {
    const raw = localStorage.getItem(INPUT_HISTORY_KEY);
    if (!raw) {
      return [];
    }
    const all = JSON.parse(raw) as Record<string, string[]>;
    return all[agentId] ?? [];
  } catch {
    return [];
  }
}

export function saveInputHistory(agentId: string, history: string[]): void {
  try {
    const raw = localStorage.getItem(INPUT_HISTORY_KEY);
    const all = raw ? (JSON.parse(raw) as Record<string, string[]>) : {};
    all[agentId] = history.slice(-MAX_INPUT_HISTORY);
    localStorage.setItem(INPUT_HISTORY_KEY, JSON.stringify(all));
  } catch {
    // ignore storage errors
  }
}

export function appendInputHistory(agentId: string, message: string): string[] {
  const trimmed = message.trim();
  if (!trimmed) {
    return loadInputHistory(agentId);
  }

  const history = loadInputHistory(agentId).filter((item) => item !== trimmed);
  history.push(trimmed);
  const next = history.slice(-MAX_INPUT_HISTORY);
  saveInputHistory(agentId, next);
  return next;
}
