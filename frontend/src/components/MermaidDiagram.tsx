import { memo, useEffect, useId, useRef, useState } from "react";

import { downloadDiagramSvg } from "../utils/diagramExport";

let mermaidInitialized = false;
const MERMAID_RENDER_CONFIG_VERSION = "wrap-v1";
const renderedSvgCache = new Map<string, string>();

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.1;
const ZOOM_DEFAULT = 1;

function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));
}

function getSvgCacheKey(definition: string): string {
  return `${MERMAID_RENDER_CONFIG_VERSION}:${definition}`;
}

async function renderMermaidChart(elementId: string, definition: string): Promise<string> {
  const cacheKey = getSvgCacheKey(definition);
  const cached = renderedSvgCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const mermaid = (await import("mermaid")).default;
  if (!mermaidInitialized) {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "strict",
      fontFamily: "inherit",
      fontSize: 12,
      htmlLabels: true,
      flowchart: {
        useMaxWidth: true,
        wrappingWidth: 150,
        padding: 10,
        nodeSpacing: 40,
        rankSpacing: 45,
      },
      themeCSS: `
        .nodeLabel {
          overflow-wrap: anywhere;
          word-break: break-word;
          white-space: normal;
          line-height: 1.25;
        }
        .nodeLabel p {
          margin: 0;
          text-align: center;
        }
        .edgeLabel {
          overflow-wrap: anywhere;
          word-break: break-word;
          white-space: normal;
        }
      `,
    });
    mermaidInitialized = true;
  }
  const { svg } = await mermaid.render(elementId, definition);
  renderedSvgCache.set(cacheKey, svg);
  return svg;
}

interface MermaidDiagramProps {
  chart: string;
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
      <path d="M12 3v12m0 0l4-4m-4 4l-4-4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" />
    </svg>
  );
}

function MermaidDiagramInner({ chart }: MermaidDiagramProps) {
  const reactId = useId().replace(/:/g, "");
  const renderIdRef = useRef(0);
  const normalizedChart = chart.trim();
  const cacheKey = normalizedChart ? getSvgCacheKey(normalizedChart) : "";
  const cachedSvg = cacheKey ? renderedSvgCache.get(cacheKey) ?? null : null;
  const [svg, setSvg] = useState<string | null>(cachedSvg);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);

  useEffect(() => {
    setZoom(ZOOM_DEFAULT);
  }, [normalizedChart]);

  useEffect(() => {
    if (!normalizedChart) {
      setSvg(null);
      setRenderError(null);
      return;
    }

    const existing = renderedSvgCache.get(cacheKey);
    if (existing) {
      setSvg(existing);
      setRenderError(null);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          renderIdRef.current += 1;
          const elementId = `mermaid-${reactId}-${renderIdRef.current}`;
          const renderedSvg = await renderMermaidChart(elementId, normalizedChart);
          if (!cancelled) {
            setSvg(renderedSvg);
            setRenderError(null);
          }
        } catch (err) {
          if (!cancelled) {
            setRenderError(err instanceof Error ? err.message : "Mermaid 렌더링에 실패했습니다.");
          }
        }
      })();
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [normalizedChart, reactId, cacheKey]);

  const handleDownloadSvg = () => {
    if (!svg) {
      return;
    }
    downloadDiagramSvg(svg, "mermaid-diagram");
  };

  const zoomPercent = Math.round(zoom * 100);
  const toolbarButtonClass =
    "flex h-7 w-7 items-center justify-center rounded text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40";

  if (renderError && !svg) {
    return (
      <div className="space-y-2">
        <pre className="overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-200">
          <code className="language-mermaid">{chart}</code>
        </pre>
        <p className="text-xs text-amber-300">Mermaid 미리보기: {renderError}</p>
      </div>
    );
  }

  if (!svg) {
    return (
      <pre className="overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-400">
        <code className="language-mermaid">{chart}</code>
      </pre>
    );
  }

  return (
    <div className="mermaid-diagram relative overflow-hidden rounded border border-slate-700 bg-slate-950/60">
      <div className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/95 p-1 shadow-lg">
        <button
          type="button"
          onClick={handleDownloadSvg}
          aria-label="SVG 다운로드"
          title="SVG 다운로드"
          className={toolbarButtonClass}
        >
          <DownloadIcon />
        </button>
        <button
          type="button"
          onClick={() => setZoom((current) => clampZoom(current - ZOOM_STEP))}
          disabled={zoom <= ZOOM_MIN}
          aria-label="축소"
          title="축소"
          className={toolbarButtonClass}
        >
          −
        </button>
        <button
          type="button"
          onClick={() => setZoom(ZOOM_DEFAULT)}
          aria-label="배율 초기화"
          title="100%로 초기화"
          className="min-w-[3.25rem] rounded px-1.5 py-1 text-center font-mono text-[11px] text-slate-300 hover:bg-slate-800"
        >
          {zoomPercent}%
        </button>
        <button
          type="button"
          onClick={() => setZoom((current) => clampZoom(current + ZOOM_STEP))}
          disabled={zoom >= ZOOM_MAX}
          aria-label="확대"
          title="확대"
          className={toolbarButtonClass}
        >
          +
        </button>
      </div>

      <div className="max-h-[480px] overflow-auto p-3 pt-11">
        <div
          className="mermaid-diagram-canvas inline-block min-w-full"
          style={{ zoom }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}

export const MermaidDiagram = memo(MermaidDiagramInner);
