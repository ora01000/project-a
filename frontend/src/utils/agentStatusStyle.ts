const HEALTHY_CONNECTION_STATUSES = new Set(["connected", "ready", "mock"]);

export function isHealthyConnectionStatus(status: string): boolean {
  return HEALTHY_CONNECTION_STATUSES.has(status);
}

export function connectionStatusDotClass(status: string): string {
  if (isHealthyConnectionStatus(status)) {
    return "bg-emerald-500";
  }
  if (status === "partial" || status === "disabled" || status === "degraded") {
    return "bg-amber-500";
  }
  return "bg-rose-500";
}
