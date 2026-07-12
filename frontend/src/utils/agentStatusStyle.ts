const HEALTHY_CONNECTION_STATUSES = new Set(["connected", "ready"]);

export function isHealthyConnectionStatus(status: string): boolean {
  return HEALTHY_CONNECTION_STATUSES.has(status);
}

export function connectionStatusDotClass(status: string): string {
  if (isHealthyConnectionStatus(status)) {
    return "bg-emerald-500";
  }
  if (status === "partial" || status === "disabled") {
    return "bg-amber-500";
  }
  return "bg-rose-500";
}

export function connectionStatusStroke(status: string): string {
  if (isHealthyConnectionStatus(status)) {
    return "#34d399";
  }
  if (status === "partial" || status === "disabled") {
    return "#fbbf24";
  }
  return "#f87171";
}

export function connectionStatusFill(status: string): string {
  if (isHealthyConnectionStatus(status)) {
    return "#064e3b";
  }
  if (status === "partial" || status === "disabled") {
    return "#451a03";
  }
  return "#450a0a";
}
