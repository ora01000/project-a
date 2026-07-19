import type { AuthUser } from "../types/auth";
import { bandLabel } from "../types/user";

const AUTH_SESSION_KEY = "project-a-auth-user";

/** Frontend login session lifetime (absolute TTL from login). */
export const AUTH_SESSION_TIMEOUT_MS = 60 * 60 * 1000;

interface AuthSessionPayload {
  user: AuthUser;
  expiresAt: number;
}

function isAuthUser(value: unknown): value is AuthUser {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<AuthUser>;
  return (
    typeof candidate.idx === "number" &&
    typeof candidate.userid === "string" &&
    typeof candidate.username === "string"
  );
}

function readPayload(): AuthSessionPayload | null {
  try {
    const raw = sessionStorage.getItem(AUTH_SESSION_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as unknown;

    // New format: { user, expiresAt }
    if (parsed && typeof parsed === "object" && "user" in parsed && "expiresAt" in parsed) {
      const payload = parsed as Partial<AuthSessionPayload>;
      if (isAuthUser(payload.user) && typeof payload.expiresAt === "number") {
        return { user: payload.user, expiresAt: payload.expiresAt };
      }
      return null;
    }

    // Legacy format (AuthUser only) — no timeout metadata; force re-login.
    return null;
  } catch {
    return null;
  }
}

function writePayload(payload: AuthSessionPayload): void {
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(payload));
}

export function isAuthSessionExpired(now = Date.now()): boolean {
  const payload = readPayload();
  if (!payload) {
    return true;
  }
  return payload.expiresAt <= now;
}

export function getAuthSessionExpiresAt(): number | null {
  return readPayload()?.expiresAt ?? null;
}

export function getAuthSessionRemainingMs(now = Date.now()): number {
  const expiresAt = getAuthSessionExpiresAt();
  if (expiresAt === null) {
    return 0;
  }
  return Math.max(0, expiresAt - now);
}

/** Start a new login session (1 hour absolute TTL). */
export function startAuthSession(user: AuthUser, now = Date.now()): void {
  writePayload({
    user,
    expiresAt: now + AUTH_SESSION_TIMEOUT_MS,
  });
}

export function loadAuthUser(now = Date.now()): AuthUser | null {
  const payload = readPayload();
  if (!payload) {
    return null;
  }
  if (payload.expiresAt <= now) {
    clearAuthUser();
    return null;
  }
  return payload.user;
}

/** Update stored user while preserving the existing session expiry. */
export function saveAuthUser(user: AuthUser, now = Date.now()): void {
  const payload = readPayload();
  if (!payload || payload.expiresAt <= now) {
    clearAuthUser();
    return;
  }
  writePayload({
    user,
    expiresAt: payload.expiresAt,
  });
}

export function clearAuthUser(): void {
  sessionStorage.removeItem(AUTH_SESSION_KEY);
}

export function formatUserLabel(user: AuthUser): string {
  const title = bandLabel(user.band);
  const name = title ? `${user.username} ${title}` : user.username;
  return `${user.depart}/${name}`;
}
