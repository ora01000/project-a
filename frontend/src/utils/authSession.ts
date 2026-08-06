import type { AuthUser } from "../types/auth";
import { bandLabel } from "../types/user";

const AUTH_SESSION_KEY = "project-a-auth-user";

/** Default session TTL when server does not provide expires_in (1 hour). */
export const AUTH_SESSION_TIMEOUT_MS = 60 * 60 * 1000;

interface AuthSessionPayload {
  accessToken: string;
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
    if (!parsed || typeof parsed !== "object") {
      return null;
    }

    const payload = parsed as Partial<AuthSessionPayload>;
    if (
      typeof payload.accessToken === "string" &&
      isAuthUser(payload.user) &&
      typeof payload.expiresAt === "number"
    ) {
      return {
        accessToken: payload.accessToken,
        user: payload.user,
        expiresAt: payload.expiresAt,
      };
    }
    return null;
  } catch {
    return null;
  }
}

function writePayload(payload: AuthSessionPayload): void {
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(payload));
}

export function getAccessToken(): string | null {
  return readPayload()?.accessToken ?? null;
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

/** Remaining session time in minutes for menu bar display. */
export function formatAuthSessionRemaining(remainingMs: number): string {
  const totalMinutes = Math.floor(Math.max(0, remainingMs) / 60000);
  return `세션: ${totalMinutes}분`;
}

export const SESSION_EXTEND_THRESHOLD_MS = 5 * 60 * 1000;

export async function extendAuthSession(): Promise<number> {
  const response = await fetch("/api/auth/me");
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "세션 연장에 실패했습니다.");
  }
  const payload = (await response.json()) as { expires_in?: number };
  const expiresInSeconds =
    typeof payload.expires_in === "number" && payload.expires_in > 0 ? payload.expires_in : 3600;
  touchAuthSession(expiresInSeconds);
  return expiresInSeconds;
}

export function startAuthSession(
  user: AuthUser,
  accessToken: string,
  expiresInSeconds: number,
  now = Date.now(),
): void {
  writePayload({
    accessToken,
    user,
    expiresAt: now + Math.max(1, expiresInSeconds) * 1000,
  });
}

export function touchAuthSession(expiresInSeconds: number, now = Date.now()): void {
  const payload = readPayload();
  if (!payload) {
    return;
  }
  writePayload({
    ...payload,
    expiresAt: now + Math.max(1, expiresInSeconds) * 1000,
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

export function saveAuthUser(user: AuthUser, now = Date.now()): void {
  const payload = readPayload();
  if (!payload || payload.expiresAt <= now) {
    clearAuthUser();
    return;
  }
  writePayload({
    ...payload,
    user,
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

export function userFromAuthResponse(payload: Record<string, unknown>): AuthUser {
  return {
    idx: Number(payload.idx),
    userid: String(payload.userid),
    email: String(payload.email ?? ""),
    username: String(payload.username),
    depart: String(payload.depart ?? ""),
    role: Number(payload.role),
    band: Number(payload.band ?? 1),
    agents: String(payload.agents ?? ""),
    agent_ids: Array.isArray(payload.agent_ids) ? (payload.agent_ids as string[]) : [],
  };
}
