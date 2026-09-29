import { memo, useCallback, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import type { FossflowCompactDiagram } from "../types/fossflow";
import { parseFossflowCompactJson } from "../types/fossflow";
import { compactToFossflowScene } from "../utils/fossflowCompact";
import { downloadDiagramPng } from "../utils/diagramExport";
import { renderFossflowScene } from "../utils/fossflowSvg";
import type { FossflowNodeHitbox } from "../utils/fossflowSvg";

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.1;
const ZOOM_DEFAULT = 1;
const PAN_THRESHOLD_PX = 4;

function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));
}

function clampFitScale(value: number): number {
  return Math.min(4, Math.max(0.05, value));
}

interface FossFlowDiagramProps {
  diagram: FossflowCompactDiagram | string;
}

interface PanSession {
  pointerId: number;
  startX: number;
  startY: number;
  scrollLeft: number;
  scrollTop: number;
  moved: boolean;
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
      <path d="M12 3v12m0 0l4-4m-4 4l-4-4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" />
    </svg>
  );
}

function FossFlowDiagramInner({ diagram }: FossFlowDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const panSessionRef = useRef<PanSession | null>(null);
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);
  const [diagramSize, setDiagramSize] = useState<{ width: number; height: number } | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [isPanning, setIsPanning] = useState(false);
  const [hoveredNode, setHoveredNode] = useState<FossflowNodeHitbox | null>(null);
  const [tooltipOffset, setTooltipOffset] = useState<{ left: number; top: number } | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const { render, error, title } = useMemo(() => {
    const compact = typeof diagram === "string" ? parseFossflowCompactJson(diagram) : diagram;
    if (!compact) {
      return { render: null, error: "FossFLOW compact JSON이 아닙니다.", title: "" };
    }
    try {
      const scene = compactToFossflowScene(compact);
      return { render: renderFossflowScene(scene), error: null, title: scene.title };
    } catch (err) {
      return {
        render: null,
        error: err instanceof Error ? err.message : "FossFLOW 렌더링에 실패했습니다.",
        title: "",
      };
    }
  }, [diagram]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current ?? containerRef.current;
    if (!viewport) {
      return;
    }
    const updateWidth = () => {
      setContainerWidth(viewport.clientWidth);
    };
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [render]);

  useLayoutEffect(() => {
    if (render) {
      setDiagramSize({ width: render.width, height: render.height });
      return;
    }
    const svgElement = canvasRef.current?.querySelector("svg");
    if (!svgElement) {
      setDiagramSize(null);
      return;
    }
    const attrWidth = Number.parseFloat(svgElement.getAttribute("width") ?? "");
    const attrHeight = Number.parseFloat(svgElement.getAttribute("height") ?? "");
    if (attrWidth > 0 && attrHeight > 0) {
      setDiagramSize({ width: attrWidth, height: attrHeight });
    }
  }, [render]);

  const hideTooltip = useCallback(() => {
    setHoveredNode(null);
    setTooltipOffset(null);
  }, []);

  const showNodeTooltip = (node: FossflowNodeHitbox, target: HTMLElement) => {
    if (panSessionRef.current?.moved) {
      return;
    }
    const container = containerRef.current;
    if (!container) {
      setHoveredNode(node);
      setTooltipOffset(null);
      return;
    }
    const root = container.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    setHoveredNode(node);
    setTooltipOffset({
      left: rect.left - root.left + rect.width / 2,
      top: rect.bottom - root.top + 8,
    });
  };

  const hideNodeTooltip = (index: number) => {
    setHoveredNode((current) => (current?.index === index ? null : current));
    setTooltipOffset(null);
  };

  const resetViewport = useCallback(() => {
    setZoom(ZOOM_DEFAULT);
    const viewport = viewportRef.current;
    if (viewport) {
      viewport.scrollLeft = 0;
      viewport.scrollTop = 0;
    }
  }, []);

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) {
      return;
    }
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    panSessionRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
      moved: false,
    };
    event.preventDefault();
    viewport.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const session = panSessionRef.current;
    const viewport = viewportRef.current;
    if (!session || session.pointerId !== event.pointerId || !viewport) {
      return;
    }
    const dx = event.clientX - session.startX;
    const dy = event.clientY - session.startY;
    if (!session.moved && dx * dx + dy * dy >= PAN_THRESHOLD_PX * PAN_THRESHOLD_PX) {
      session.moved = true;
      setIsPanning(true);
      hideTooltip();
    }
    if (!session.moved) {
      return;
    }
    event.preventDefault();
    viewport.scrollLeft = session.scrollLeft - dx;
    viewport.scrollTop = session.scrollTop - dy;
  };

  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const session = panSessionRef.current;
    if (!session || session.pointerId !== event.pointerId) {
      return;
    }
    const viewport = viewportRef.current;
    if (viewport?.hasPointerCapture(event.pointerId)) {
      viewport.releasePointerCapture(event.pointerId);
    }
    panSessionRef.current = null;
    setIsPanning(false);
  };

  const handleDownloadPng = () => {
    if (!render) {
      return;
    }
    setDownloadError(null);
    const svgNode = canvasRef.current?.querySelector("svg");
    const svgElement = svgNode instanceof SVGSVGElement ? svgNode : null;
    downloadDiagramPng(render.svg, title || "fossflow-diagram", svgElement).catch((err: unknown) => {
      setDownloadError(err instanceof Error ? err.message : "PNG 저장에 실패했습니다.");
    });
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

  if (error || !render) {
    return <p className="p-4 text-xs text-amber-300">FossFLOW 미리보기: {error}</p>;
  }

  return (
    <div
      ref={containerRef}
      className="fossflow-diagram relative h-full min-h-0 w-full flex-1 overflow-hidden rounded border border-slate-700 bg-slate-950/60"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-end p-2">
        <div className="pointer-events-auto flex w-fit items-center gap-1 rounded-md border border-slate-700 bg-slate-900/95 p-1 shadow-lg">
          <button
            type="button"
            onClick={handleDownloadPng}
            aria-label="PNG 다운로드"
            title="PNG 다운로드 (그리드·라인 포함)"
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
            onClick={resetViewport}
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
      </div>
      {downloadError ? <p className="absolute left-3 top-12 z-10 text-[11px] text-amber-300">{downloadError}</p> : null}

      <div
        ref={viewportRef}
        className={`h-full min-h-0 w-full overflow-auto p-3 pt-12 ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
        style={{ touchAction: "none" }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endPan}
        onPointerCancel={endPan}
        onDragStart={(event) => event.preventDefault()}
      >
        <div
          className="relative"
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
            className="relative inline-block select-none"
            style={{
              transform: `scale(${effectiveScale})`,
              transformOrigin: "top left",
              width: diagramSize?.width,
              height: diagramSize?.height,
            }}
          >
            <div dangerouslySetInnerHTML={{ __html: render.svg }} />
            {render.nodes.map((node) => (
              <button
                key={node.index}
                type="button"
                aria-label={node.description ? `${node.name}. ${node.description}` : node.name}
                className="absolute cursor-inherit border-0 bg-transparent p-0"
                style={{
                  left: node.x,
                  top: node.y,
                  width: node.width,
                  height: node.height,
                }}
                onMouseEnter={(event) => showNodeTooltip(node, event.currentTarget)}
                onMouseLeave={() => hideNodeTooltip(node.index)}
                onFocus={(event) => showNodeTooltip(node, event.currentTarget)}
                onBlur={() => hideNodeTooltip(node.index)}
              />
            ))}
          </div>
        </div>
      </div>
      {hoveredNode && tooltipOffset ? (
        <div
          className="pointer-events-none absolute z-20 max-w-xs rounded-md border border-slate-200 bg-white px-3 py-2 text-left shadow-lg"
          style={{
            left: tooltipOffset.left,
            top: tooltipOffset.top,
            transform: "translateX(-50%)",
          }}
        >
          <p className="text-xs font-semibold text-slate-900">{hoveredNode.name}</p>
          {hoveredNode.description ? (
            <p className="mt-1 text-[11px] leading-snug text-slate-600">{hoveredNode.description}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export const FossFlowDiagram = memo(FossFlowDiagramInner);
