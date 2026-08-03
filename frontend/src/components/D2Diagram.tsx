import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";

import { downloadDiagramSvg } from "../utils/diagramExport";
import { normalizeD2Definition } from "../utils/d2Normalize";

const D2_RENDER_CONFIG_VERSION = "v3-normalize-styles";
const renderedSvgCache = new Map<string, string>();

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.1;
const ZOOM_DEFAULT = 1;

let d2Instance: import("@terrastruct/d2").D2 | null = null;

function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));
}

function clampFitScale(value: number): number {
  return Math.min(4, Math.max(0.05, value));
}

function getSvgCacheKey(definition: string): string {
  return `${D2_RENDER_CONFIG_VERSION}:${definition}`;
}

async function getD2Client(): Promise<import("@terrastruct/d2").D2> {
  if (!d2Instance) {
    const { D2 } = await import("@terrastruct/d2");
    d2Instance = new D2();
  }
  return d2Instance;
}

async function renderD2Chart(definition: string): Promise<string> {
  const cacheKey = getSvgCacheKey(definition);
  const cached = renderedSvgCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const d2 = await getD2Client();
  const result = await d2.compile(normalizeD2Definition(definition));
  const svg = await d2.render(result.diagram, {
    ...result.renderOptions,
    darkThemeID: 200,
    pad: 24,
    noXMLTag: true,
    scale: 1,
  });
  renderedSvgCache.set(cacheKey, svg);
  return svg;
}

interface D2DiagramProps {
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

function D2DiagramInner({ chart }: D2DiagramProps) {
  const renderIdRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const normalizedChart = chart.trim();
  const cacheKey = normalizedChart ? getSvgCacheKey(normalizedChart) : "";
  const cachedSvg = cacheKey ? renderedSvgCache.get(cacheKey) ?? null : null;
  const [svg, setSvg] = useState<string | null>(cachedSvg);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);
  const [diagramSize, setDiagramSize] = useState<{ width: number; height: number } | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    setZoom(ZOOM_DEFAULT);
    setDiagramSize(null);
  }, [normalizedChart]);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const updateWidth = () => {
      setContainerWidth(container.clientWidth);
    };

    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(container);
    return () => observer.disconnect();
  }, [svg]);

  useLayoutEffect(() => {
    const svgElement = canvasRef.current?.querySelector("svg");
    if (!svgElement) {
      setDiagramSize(null);
      return;
    }

    const attrWidth = Number.parseFloat(svgElement.getAttribute("width") ?? "");
    const attrHeight = Number.parseFloat(svgElement.getAttribute("height") ?? "");
    if (attrWidth > 0 && attrHeight > 0) {
      setDiagramSize({ width: attrWidth, height: attrHeight });
      return;
    }

    const rect = svgElement.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      setDiagramSize({ width: rect.width, height: rect.height });
    }
  }, [svg]);

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
          const renderedSvg = await renderD2Chart(normalizedChart);
          if (!cancelled) {
            setSvg(renderedSvg);
            setRenderError(null);
          }
        } catch (err) {
          if (!cancelled) {
            setRenderError(err instanceof Error ? err.message : "D2 렌더링에 실패했습니다.");
          }
        }
      })();
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [normalizedChart, cacheKey]);

  const handleDownloadSvg = () => {
    if (!svg) {
      return;
    }
    downloadDiagramSvg(svg, "d2-diagram");
  };

  const horizontalPadding = 24;
  const fitScale =
    diagramSize && containerWidth > horizontalPadding
      ? clampFitScale((containerWidth - horizontalPadding) / diagramSize.width)
      : 1;
  const effectiveScale = fitScale * zoom;
  const scaledWidth = diagramSize ? diagramSize.width * effectiveScale : 0;
  const scaledHeight = diagramSize ? diagramSize.height * effectiveScale : 0;
  const zoomPercent = Math.round(effectiveScale * 100);
  const toolbarButtonClass =
    "flex h-7 w-7 items-center justify-center rounded text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40";

  if (renderError && !svg) {
    return (
      <div className="space-y-2">
        <pre className="overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-200">
          <code className="language-d2">{chart}</code>
        </pre>
        <p className="text-xs text-amber-300">D2 미리보기: {renderError}</p>
      </div>
    );
  }

  if (!svg) {
    return (
      <pre className="overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-400">
        <code className="language-d2">{chart}</code>
      </pre>
    );
  }

  return (
    <div
      ref={containerRef}
      className="d2-diagram relative w-full overflow-hidden rounded border border-slate-700 bg-slate-950/60"
    >
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
          title="가로 맞춤으로 초기화"
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

      <div className="overflow-hidden p-3 pt-11">
        <div
          className="mx-auto"
          style={
            diagramSize
              ? {
                  width: scaledWidth,
                  height: scaledHeight,
                }
              : undefined
          }
        >
          <div
            ref={canvasRef}
            className="d2-diagram-canvas inline-block"
            style={{
              transform: `scale(${effectiveScale})`,
              transformOrigin: "top left",
              width: diagramSize?.width,
              height: diagramSize?.height,
            }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>
      </div>
    </div>
  );
}

export const D2Diagram = memo(D2DiagramInner);
