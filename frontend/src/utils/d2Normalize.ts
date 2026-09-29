/** Normalize common invalid D2 style keywords produced by LLMs before compile. */

function strokeDashReplacement(_match: string, value?: string): string {
  if (!value) {
    return "stroke-dash: 5";
  }

  const normalized = value.trim().toLowerCase();
  if (normalized === "false" || normalized === "0") {
    return "stroke-dash: 0";
  }
  if (/^\d+$/.test(normalized)) {
    return `stroke-dash: ${normalized}`;
  }

  return "stroke-dash: 5";
}

export function normalizeD2Definition(definition: string): string {
  let normalized = definition;

  normalized = normalized.replace(
    /\.style\.stroke-dashed(?:\s*:\s*([^\n]+))?/gi,
    (_match, value?: string) => `.style.${strokeDashReplacement("stroke-dashed", value)}`,
  );

  normalized = normalized.replace(
    /\bstroke-dashed\s*:\s*([^\n]+)/gi,
    (_match, value: string) => strokeDashReplacement("stroke-dashed", value),
  );

  normalized = normalized.replace(/\bstroke-dashed\b/gi, "stroke-dash: 5");

  return normalized;
}
