import type { CSSProperties } from "react";

const BODY = "#E8D4A8";
const OUTLINE = "#C4A574";
const SWIRL = "#8B5A2B";
const INK = "#1e293b";

interface MoonaIconProps {
  size?: number;
  /** false 이면 1프레임 정지 */
  animated?: boolean;
  className?: string;
  title?: string;
}

function Swirl() {
  return (
    <g>
      <rect x="9" y="0" width="2" height="1" fill={SWIRL} />
      <rect x="8" y="1" width="3" height="1" fill={SWIRL} />
      <rect x="5" y="2" width="6" height="1" fill={SWIRL} />
    </g>
  );
}

function Body() {
  return (
    <g>
      <rect x="5" y="3" width="6" height="1" fill={OUTLINE} />
      <rect x="4" y="4" width="1" height="1" fill={OUTLINE} />
      <rect x="11" y="4" width="1" height="1" fill={OUTLINE} />
      <rect x="3" y="5" width="1" height="4" fill={OUTLINE} />
      <rect x="12" y="5" width="1" height="4" fill={OUTLINE} />
      <rect x="4" y="9" width="1" height="1" fill={OUTLINE} />
      <rect x="11" y="9" width="1" height="1" fill={OUTLINE} />
      <rect x="5" y="10" width="6" height="1" fill={OUTLINE} />
      <rect x="5" y="4" width="6" height="6" fill={BODY} />
      <rect x="4" y="5" width="1" height="4" fill={BODY} />
      <rect x="11" y="5" width="1" height="4" fill={BODY} />
      <rect x="7" y="8" width="2" height="2" fill={INK} />
    </g>
  );
}

function Eyes({ blink }: { blink?: boolean }) {
  if (blink) {
    return (
      <g>
        <rect x="5" y="7" width="2" height="1" fill={INK} />
        <rect x="9" y="7" width="2" height="1" fill={INK} />
      </g>
    );
  }
  return (
    <g>
      <rect x="5" y="6" width="2" height="2" fill={INK} />
      <rect x="9" y="6" width="2" height="2" fill={INK} />
    </g>
  );
}

type LegPose = "neutral" | "in" | "out" | "shift";

function Legs({ pose }: { pose: LegPose }) {
  const d1 = pose === "in" ? 1 : pose === "out" ? -1 : 0;
  const d2 = pose === "shift" ? 1 : 0;
  const d3 = pose === "shift" ? -1 : 0;
  const d4 = pose === "in" ? -1 : pose === "out" ? 1 : 0;

  return (
    <g>
      <g transform={`translate(${d1} 0)`}>
        <rect x="3" y="11" width="2" height="3" fill={BODY} />
        <rect x="3" y="11" width="2" height="1" fill={OUTLINE} />
        <rect x="2" y="12" width="1" height="2" fill={OUTLINE} />
        <rect x="5" y="12" width="1" height="2" fill={OUTLINE} />
        <rect x="3" y="14" width="2" height="1" fill={OUTLINE} />
      </g>
      <g transform={`translate(${d2} 0)`}>
        <rect x="6" y="11" width="2" height="4" fill={BODY} />
        <rect x="6" y="11" width="2" height="1" fill={OUTLINE} />
        <rect x="5" y="12" width="1" height="3" fill={OUTLINE} />
        <rect x="8" y="12" width="1" height="3" fill={OUTLINE} />
        <rect x="6" y="15" width="2" height="1" fill={OUTLINE} />
      </g>
      <g transform={`translate(${d3} 0)`}>
        <rect x="9" y="11" width="2" height="4" fill={BODY} />
        <rect x="9" y="11" width="2" height="1" fill={OUTLINE} />
        <rect x="8" y="12" width="1" height="3" fill={OUTLINE} />
        <rect x="11" y="12" width="1" height="3" fill={OUTLINE} />
        <rect x="9" y="15" width="2" height="1" fill={OUTLINE} />
      </g>
      <g transform={`translate(${d4} 0)`}>
        <rect x="12" y="11" width="2" height="3" fill={BODY} />
        <rect x="12" y="11" width="2" height="1" fill={OUTLINE} />
        <rect x="11" y="12" width="1" height="2" fill={OUTLINE} />
        <rect x="14" y="12" width="1" height="2" fill={OUTLINE} />
        <rect x="12" y="14" width="2" height="1" fill={OUTLINE} />
      </g>
    </g>
  );
}

function Frame({
  offsetY,
  pose,
  blink,
}: {
  offsetY: number;
  pose: LegPose;
  blink?: boolean;
}) {
  return (
    <g transform={`translate(0 ${offsetY})`}>
      <Swirl />
      <Body />
      <Eyes blink={blink} />
      <Legs pose={pose} />
    </g>
  );
}

/**
 * 무너 4프레임 픽셀 아이콘 (인라인 SVG + CSS steps).
 * 1 기본 → 2 다리 모임 → 3 다리 벌림+blink → 4 교차 스웨이
 */
export function MoonaIcon({
  size = 14,
  animated = true,
  className = "",
  title,
}: MoonaIconProps) {
  const style = {
    ["--moona-size" as string]: `${size}px`,
  } as CSSProperties;

  return (
    <span
      className={`moona-icon ${animated ? "moona-icon--animated" : ""} ${className}`.trim()}
      style={style}
      role="img"
      aria-label={title ?? "무너"}
      title={title}
    >
      <span className="moona-icon__viewport">
        <svg
          className="moona-icon__strip"
          width={16}
          height={64}
          viewBox="0 0 16 64"
          shapeRendering="crispEdges"
          aria-hidden
        >
          <Frame offsetY={0} pose="neutral" />
          <Frame offsetY={16} pose="in" />
          <Frame offsetY={32} pose="out" blink />
          <Frame offsetY={48} pose="shift" />
        </svg>
      </span>
    </span>
  );
}
