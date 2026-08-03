/** Create a session id for agent chat; works outside secure contexts (non-localhost HTTP). */
export function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    try {
      return crypto.randomUUID();
    } catch {
      // randomUUID requires a secure context in some browsers.
    }
  }

  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}
