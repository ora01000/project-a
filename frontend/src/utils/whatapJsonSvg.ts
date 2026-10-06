import type { WhatapJsonChart } from "../types/whatapJson";

/** Always light theme — independent of app dark/light UI. */
const SERIES_COLORS = [
  "#0284c7",
  "#059669",
  "#d97706",
  "#e11d48",
  "#65a30d",
  "#0891b2",
  "#ea580c",
  "#c026d3",
];

const THEME = {
  background: "#ffffff",
  plotFill: "#f8fafc",
  plotStroke: "#e2e8f0",
  grid: "#e2e8f0",
  title: "#0f172a",
  subtitle: "#64748b",
  axisLabel: "#64748b",
  legend: "#334155",
} as const;

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function parseTimeMs(value: string): number | null {
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function formatTick(ms: number): string {
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(ms));
  } catch {
    return new Date(ms).toISOString();
  }
}

function niceMax(value: number): number {
  if (value <= 0) {
    return 1;
  }
  const exp = Math.floor(Math.log10(value));
  const base = 10 ** exp;
  const scaled = value / base;
  const nice = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return nice * base;
}

export function renderWhatapJsonSvg(chart: WhatapJsonChart): string {
  const width = 860;
  const height = 360;
  const padL = 56;
  const padR = 24;
  const padT = 48;
  const padB = 72;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const allPoints = chart.series.flatMap((series) =>
    series.points
      .map((point) => {
        const t = parseTimeMs(point.t);
        return t == null ? null : { t, v: point.v };
      })
      .filter((point): point is { t: number; v: number } => point !== null),
  );

  const minT =
    allPoints.length > 0
      ? Math.min(...allPoints.map((p) => p.t))
      : chart.from
        ? (parseTimeMs(chart.from) ?? Date.now())
        : Date.now();
  const maxT =
    allPoints.length > 0
      ? Math.max(...allPoints.map((p) => p.t))
      : chart.to
        ? (parseTimeMs(chart.to) ?? minT + 1)
        : minT + 1;
  const spanT = Math.max(1, maxT - minT);
  const maxV = niceMax(Math.max(0, ...allPoints.map((p) => p.v), 1));

  const titleParts = [
    chart.metric || "metric",
    chart.unit ? `(${chart.unit})` : "",
    chart.project ? `· project ${chart.project}` : "",
  ]
    .filter(Boolean)
    .join(" ");
  const subtitle = chart.source || "";

  const yTicks = 4;
  const gridLines: string[] = [];
  for (let i = 0; i <= yTicks; i += 1) {
    const ratio = i / yTicks;
    const y = padT + plotH * (1 - ratio);
    const value = maxV * ratio;
    gridLines.push(
      `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${(padL + plotW).toFixed(1)}" y2="${y.toFixed(1)}" stroke="${THEME.grid}" stroke-width="1" />`,
    );
    gridLines.push(
      `<text x="${padL - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" fill="${THEME.axisLabel}" font-size="11" font-family="ui-sans-serif,system-ui,sans-serif">${escapeXml(value.toFixed(value >= 10 ? 0 : 1))}</text>`,
    );
  }

  const xTickCount = 4;
  const xLabels: string[] = [];
  for (let i = 0; i <= xTickCount; i += 1) {
    const ratio = i / xTickCount;
    const x = padL + plotW * ratio;
    const t = minT + spanT * ratio;
    xLabels.push(
      `<text x="${x.toFixed(1)}" y="${(height - 36).toFixed(1)}" text-anchor="middle" fill="${THEME.axisLabel}" font-size="11" font-family="ui-sans-serif,system-ui,sans-serif">${escapeXml(formatTick(t))}</text>`,
    );
  }

  const paths: string[] = [];
  const legend: string[] = [];
  chart.series.forEach((series, index) => {
    const color = SERIES_COLORS[index % SERIES_COLORS.length];
    const coords = series.points
      .map((point) => {
        const t = parseTimeMs(point.t);
        if (t == null) {
          return null;
        }
        const x = padL + ((t - minT) / spanT) * plotW;
        const y = padT + (1 - point.v / maxV) * plotH;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .filter((value): value is string => value !== null);
    if (coords.length >= 2) {
      paths.push(
        `<polyline fill="none" stroke="${color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" points="${coords.join(" ")}" />`,
      );
    } else if (coords.length === 1) {
      const [x, y] = coords[0].split(",");
      paths.push(`<circle cx="${x}" cy="${y}" r="3.5" fill="${color}" />`);
    }
    const lx = padL + (index % 3) * 260;
    const ly = height - 14 + Math.floor(index / 3) * 0;
    legend.push(
      `<rect x="${lx}" y="${ly - 9}" width="10" height="10" rx="2" fill="${color}" />`,
      `<text x="${lx + 16}" y="${ly}" fill="${THEME.legend}" font-size="11" font-family="ui-sans-serif,system-ui,sans-serif">${escapeXml(series.name)}</text>`,
    );
  });

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img">`,
    `<rect width="100%" height="100%" fill="${THEME.background}" rx="8" />`,
    `<text x="${padL}" y="24" fill="${THEME.title}" font-size="15" font-weight="600" font-family="ui-sans-serif,system-ui,sans-serif">${escapeXml(titleParts)}</text>`,
    subtitle
      ? `<text x="${padL}" y="42" fill="${THEME.subtitle}" font-size="11" font-family="ui-sans-serif,system-ui,sans-serif">${escapeXml(subtitle)}</text>`
      : "",
    `<rect x="${padL}" y="${padT}" width="${plotW}" height="${plotH}" fill="${THEME.plotFill}" stroke="${THEME.plotStroke}" />`,
    ...gridLines,
    ...paths,
    ...xLabels,
    ...legend,
    `</svg>`,
  ]
    .filter(Boolean)
    .join("");
}
