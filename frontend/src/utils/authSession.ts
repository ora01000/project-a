import type { AuthUser } from "../types/auth";

const AUTH_SESSION_KEY = "project-a-auth-user";

export function loadAuthUser(): AuthUser | null {
  try {
    const raw = sessionStorage.getItem(AUTH_SESSION_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function saveAuthUser(user: AuthUser): void {
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(user));
}

export function clearAuthUser(): void {
  sessionStorage.removeItem(AUTH_SESSION_KEY);
}

export function formatUserLabel(user: AuthUser): string {
  return `${user.depart}/${user.username}`;
}
