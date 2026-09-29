const UUID_SESSION_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuidSessionId(value: string): boolean {
  return UUID_SESSION_ID_RE.test(value.trim());
}

/** RFC 4122 UUID v4 without requiring a secure browser context. */
function createUuidV4Fallback(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const r = (Math.random() * 16) | 0;
    const v = char === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** Create a session id for agent chat; always returns UUID v4 format. */
export function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    try {
      return crypto.randomUUID();
    } catch {
      // randomUUID requires a secure context in some browsers.
    }
  }

  return createUuidV4Fallback();
}
