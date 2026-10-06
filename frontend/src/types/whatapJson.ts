export interface WhatapJsonPoint {
  t: string;
  v: number;
}

export interface WhatapJsonSeries {
  name: string;
  oid?: number | string;
  points: WhatapJsonPoint[];
}

export interface WhatapJsonChart {
  source?: string;
  project?: string;
  metric?: string;
  unit?: string;
  from?: string;
  to?: string;
  interval_s?: number;
  series: WhatapJsonSeries[];
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function parsePoint(raw: unknown): WhatapJsonPoint | null {
  if (Array.isArray(raw) && raw.length >= 2) {
    const t = raw[0];
    const v = raw[1];
    if ((typeof t === "string" || typeof t === "number") && isFiniteNumber(Number(v))) {
      return { t: String(t), v: Number(v) };
    }
    return null;
  }
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    const t = obj.t ?? obj.time ?? obj.ts ?? obj.timestamp;
    const v = obj.v ?? obj.value ?? obj.y;
    if (t != null && isFiniteNumber(Number(v))) {
      return { t: String(t), v: Number(v) };
    }
  }
  return null;
}

export function isWhatapJsonChart(value: unknown): value is WhatapJsonChart {
  if (!value || typeof value !== "object") {
    return false;
  }
  const obj = value as Record<string, unknown>;
  if (!Array.isArray(obj.series) || obj.series.length === 0) {
    return false;
  }
  return obj.series.every((series) => {
    if (!series || typeof series !== "object") {
      return false;
    }
    const item = series as Record<string, unknown>;
    if (!Array.isArray(item.points) || item.points.length === 0) {
      return false;
    }
    return item.points.every((point) => parsePoint(point) !== null);
  });
}

export function parseWhatapJson(text: string): WhatapJsonChart | null {
  const trimmed = (text || "").trim();
  if (!trimmed) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (!isWhatapJsonChart(parsed)) {
      return null;
    }
    const root = parsed as unknown as Record<string, unknown>;
    const seriesRaw = root.series as unknown[];
    return {
      source: typeof root.source === "string" ? root.source : undefined,
      project: root.project != null ? String(root.project) : undefined,
      metric: typeof root.metric === "string" ? root.metric : undefined,
      unit: typeof root.unit === "string" ? root.unit : undefined,
      from: typeof root.from === "string" ? root.from : undefined,
      to: typeof root.to === "string" ? root.to : undefined,
      interval_s: isFiniteNumber(root.interval_s) ? root.interval_s : undefined,
      series: seriesRaw.map((series, index) => {
        const item = series as Record<string, unknown>;
        const points = (item.points as unknown[])
          .map(parsePoint)
          .filter((point): point is WhatapJsonPoint => point !== null);
        const name = typeof item.name === "string" && item.name.trim() ? item.name : `series-${index + 1}`;
        const oid =
          typeof item.oid === "number" || typeof item.oid === "string" ? item.oid : undefined;
        return { name, oid, points };
      }),
    };
  } catch {
    return null;
  }
}
