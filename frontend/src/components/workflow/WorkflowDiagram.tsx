import type { WorkflowGraph, WorkflowGraphNode } from "../../types/workflow";
import { isRunInProgress } from "./workflowModel";

interface WorkflowDiagramProps {
  graph: WorkflowGraph;
  /** work_uuid → run dates / schedule wait */
  workRunDates?: Record<
    string,
    { last_start_date?: string; last_end_date?: string; schedule_wait?: boolean }
  >;
  /** Graph node id of HITL waiting for approval (e.g. H:userid@3) */
  awaitingHitlNodeId?: string | null;
  /** Fallback match when node id differs but approver userid matches */
  awaitingHitlUserid?: string | null;
  onAwaitingHitlClick?: () => void;
}

function nodeById(graph: WorkflowGraph, id: string): WorkflowGraphNode | undefined {
  return graph.nodes.find((node) => node.id === id);
}

function edgePath(from: WorkflowGraphNode, to: WorkflowGraphNode, kind: string): string {
  if (kind === "fail" || kind === "report") {
    const x1 = from.cx;
    const y1 = from.cy + from.height / 2;
    const x2 = to.cx;
    const y2 = to.cy - (to.cy > from.cy ? to.height / 2 : 0);
    if (Math.abs(y2 - y1) > 8) {
      const midY = (y1 + y2) / 2;
      return `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`;
    }
    return `M ${x1} ${y1} L ${x2} ${y2}`;
  }
  // 성공 연결: 노드 vertical center 높이에서 좌우 가장자리로 연결
  const x1 = from.cx + from.width / 2;
  const y1 = from.cy;
  const x2 = to.cx - to.width / 2;
  const y2 = to.cy;
  return `M ${x1} ${y1} L ${x2} ${y2}`;
}

export function WorkflowDiagram({
  graph,
  workRunDates = {},
  awaitingHitlNodeId = null,
  awaitingHitlUserid = null,
  onAwaitingHitlClick,
}: WorkflowDiagramProps) {
  if (graph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        작업 워크플로우 표현식이 없습니다.
      </div>
    );
  }

  const width = Math.max(graph.width, 400);
  const height = Math.max(graph.height, 240);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full"
      role="img"
      aria-label="작업 워크플로우 다이어그램"
    >
      <defs>
        <marker
          id="wf-arrow-success"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--wf-diagram-edge)" />
        </marker>
        <marker
          id="wf-arrow-fail"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--wf-diagram-edge-fail)" />
        </marker>
        <marker
          id="wf-arrow-report"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--wf-diagram-edge-report)" />
        </marker>
      </defs>
      {graph.edges.map((edge, index) => {
        const from = nodeById(graph, edge.source);
        const to = nodeById(graph, edge.target);
        if (!from || !to) {
          return null;
        }
        const isFail = edge.kind === "fail";
        const isReport = edge.kind === "report";
        return (
          <path
            key={`${edge.source}-${edge.target}-${index}`}
            d={edgePath(from, to, edge.kind)}
            fill="none"
            stroke={
              isFail
                ? "var(--wf-diagram-edge-fail)"
                : isReport
                  ? "var(--wf-diagram-edge-report)"
                  : "var(--wf-diagram-edge)"
            }
            strokeWidth={1.5}
            strokeDasharray={isFail ? "5 4" : undefined}
            markerEnd={
              isFail
                ? "url(#wf-arrow-fail)"
                : isReport
                  ? "url(#wf-arrow-report)"
                  : "url(#wf-arrow-success)"
            }
          />
        );
      })}
      {graph.nodes.map((node) => {
        if (node.kind === "start" || node.kind === "end" || node.kind === "mail") {
          const label =
            node.kind === "start" ? "시작" : node.kind === "end" ? "종료" : "메일전송";
          const stroke =
            node.kind === "mail"
              ? "var(--wf-diagram-mail-stroke)"
              : "var(--wf-diagram-start-stroke)";
          const radius = Math.min(node.width, node.height) / 2 || 22;
          return (
            <g key={node.id}>
              <circle
                cx={node.cx}
                cy={node.cy}
                r={radius}
                fill="var(--wf-diagram-node-fill)"
                stroke={stroke}
                strokeWidth={1.5}
              />
              <text
                x={node.cx}
                y={node.cy + 4}
                textAnchor="middle"
                fill="var(--wf-diagram-node-text)"
                fontSize={node.kind === "mail" ? 9 : 11}
                fontWeight="600"
              >
                {label}
              </text>
            </g>
          );
        }
        const x = node.cx - node.width / 2;
        const y = node.cy - node.height / 2;
        const isHitl = node.kind === "hitl";
        const dates = node.work_uuid ? workRunDates[node.work_uuid] : undefined;
        const isWorkRunning =
          !isHitl &&
          Boolean(node.work_uuid) &&
          isRunInProgress(dates?.last_start_date, dates?.last_end_date);
        const isScheduleWaiting = isWorkRunning && Boolean(dates?.schedule_wait);
        const isHitlAwaiting =
          isHitl &&
          ((Boolean(awaitingHitlNodeId) && node.id === awaitingHitlNodeId) ||
            (Boolean(awaitingHitlUserid) &&
              (node.userid || "").trim().toLowerCase() ===
                (awaitingHitlUserid || "").trim().toLowerCase()));
        const isRunning = isWorkRunning || isHitlAwaiting;
        const accentVar = isScheduleWaiting
          ? "var(--wf-schedule-accent)"
          : "var(--wf-run-accent)";
        const haloClass = isScheduleWaiting ? "wf-schedule-halo" : "wf-run-halo";
        const strokeClass = isScheduleWaiting ? "wf-schedule-stroke" : "wf-run-stroke";
        const pad = 5;
        const canClickHitl = isHitlAwaiting && Boolean(onAwaitingHitlClick);
        return (
          <g
            key={node.id}
            aria-busy={isRunning || undefined}
            style={canClickHitl ? { cursor: "pointer" } : undefined}
            onClick={
              canClickHitl
                ? (event) => {
                    event.stopPropagation();
                    onAwaitingHitlClick?.();
                  }
                : undefined
            }
          >
            {isRunning ? (
              <rect
                x={x - pad}
                y={y - pad}
                width={node.width + pad * 2}
                height={node.height + pad * 2}
                rx={isHitl ? 4 : 10}
                className={haloClass}
                pointerEvents="none"
              />
            ) : null}
            <rect
              x={x}
              y={y}
              width={node.width}
              height={node.height}
              rx={isHitl ? 2 : 8}
              fill={isHitl ? "var(--wf-diagram-hitl-fill)" : "var(--wf-diagram-node-fill)"}
              stroke={
                isRunning
                  ? accentVar
                  : isHitl
                    ? "var(--wf-diagram-hitl-stroke)"
                    : "var(--wf-diagram-work-stroke)"
              }
              strokeWidth={isRunning ? 2.5 : 1.5}
            />
            {isRunning ? (
              <rect
                x={x}
                y={y}
                width={node.width}
                height={node.height}
                rx={isHitl ? 2 : 8}
                className={strokeClass}
                pointerEvents="none"
              />
            ) : null}
            <text
              x={node.cx}
              y={node.cy + 4}
              textAnchor="middle"
              fill="var(--wf-diagram-node-text)"
              fontSize={isHitl ? 9 : 10}
              fontWeight={isRunning ? 700 : undefined}
              pointerEvents="none"
            >
              {isScheduleWaiting
                ? "예약대기"
                : node.label.length > 8
                  ? `${node.label.slice(0, 7)}…`
                  : node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
