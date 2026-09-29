const RUNTIME_MODE_LABELS: Record<string, string> = {
  mock: "Runtime (mock)",
  http: "Runtime (AX플랫폼)",
  local: "Runtime (mock)",
};

export function runtimeModeLabel(mode: string | undefined): string {
  if (!mode) {
    return "Runtime";
  }
  return RUNTIME_MODE_LABELS[mode] ?? `Runtime (${mode})`;
}
