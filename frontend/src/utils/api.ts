import { clearAuthUser, getAccessToken, touchAuthSession } from "./authSession";

const PUBLIC_API_ROUTES: Array<{ method: string; path: string }> = [
  { method: "GET", path: "/api/auth/provider" },
  { method: "POST", path: "/api/auth/login" },
  { method: "POST", path: "/api/auth/register" },
  { method: "POST", path: "/api/auth/madang/register" },
  { method: "POST", path: "/api/jobs" },
  { method: "GET", path: "/api/release-notes" },
];

const PUBLIC_API_PREFIXES = ["/api/debug/"];

function resolveRequestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

function resolveRequestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) {
    return init.method.toUpperCase();
  }
  if (typeof input !== "string" && !(input instanceof URL) && input.method) {
    return input.method.toUpperCase();
  }
  return "GET";
}

function isPublicApiRequest(url: string, method: string): boolean {
  let path = url;
  try {
    path = new URL(url, window.location.origin).pathname;
  } catch {
    // keep raw url
  }

  if (!path.startsWith("/api/")) {
    return true;
  }

  const upperMethod = method.toUpperCase();
  if (PUBLIC_API_ROUTES.some((route) => route.method === upperMethod && route.path === path)) {
    return true;
  }

  return PUBLIC_API_PREFIXES.some((prefix) => path.startsWith(prefix));
}

let authFetchInstalled = false;
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export function installAuthFetchInterceptor(): void {
  if (authFetchInstalled || typeof window === "undefined") {
    return;
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = resolveRequestUrl(input);
    const method = resolveRequestMethod(input, init);
    const headers = new Headers(init?.headers);

    if (!isPublicApiRequest(url, method)) {
      const token = getAccessToken();
      if (token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
      }
    }

    const response = await originalFetch(input, { ...init, headers });

    if (response.status === 401 && !isPublicApiRequest(url, method)) {
      clearAuthUser();
      onUnauthorized?.();
      return response;
    }

    if (response.ok && url.includes("/api/auth/me")) {
      try {
        const payload = (await response.clone().json()) as { expires_in?: number };
        if (typeof payload.expires_in === "number") {
          touchAuthSession(payload.expires_in);
        }
      } catch {
        // ignore parse errors
      }
    }

    return response;
  };

  authFetchInstalled = true;
}

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return window.fetch(input, init);
}

export async function logoutSession(): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    clearAuthUser();
    return;
  }

  try {
    await window.fetch("/api/auth/logout", { method: "POST" });
  } catch {
    // best effort
  } finally {
    clearAuthUser();
  }
}
