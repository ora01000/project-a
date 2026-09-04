import type { WorkflowGraph, WorkflowGraphNode } from "../../types/workflow";

interface WorkflowDiagramProps {
  graph: WorkflowGraph;
}

function nodeById(graph: WorkflowGraph, id: string): WorkflowGraphNode | undefined {
  return graph.nodes.find((node) => node.id === id);
}

function edgePath(from: WorkflowGraphNode, to: WorkflowGraphNode, kind: string): string {
  if (kind === "fail") {
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

export function WorkflowDiagram({ graph }: WorkflowDiagramProps) {
  if (graph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        워크플로우 표현식이 없습니다.
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
      aria-label="워크플로우 다이어그램"
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
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
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
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#fb7185" />
        </marker>
      </defs>
      {graph.edges.map((edge, index) => {
        const from = nodeById(graph, edge.source);
        const to = nodeById(graph, edge.target);
        if (!from || !to) {
          return null;
        }
        const isFail = edge.kind === "fail";
        return (
          <path
            key={`${edge.source}-${edge.target}-${index}`}
            d={edgePath(from, to, edge.kind)}
            fill="none"
            stroke={isFail ? "#fb7185" : "#94a3b8"}
            strokeWidth={1.5}
            strokeDasharray={isFail ? "5 4" : undefined}
            markerEnd={isFail ? "url(#wf-arrow-fail)" : "url(#wf-arrow-success)"}
          />
        );
      })}
      {graph.nodes.map((node) => {
        if (node.kind === "start" || node.kind === "end") {
          const label = node.kind === "start" ? "시작" : "종료";
          return (
            <g key={node.id}>
              <circle
                cx={node.cx}
                cy={node.cy}
                r={22}
                fill="#0f172a"
                stroke="#7dd3fc"
                strokeWidth={1.5}
              />
              <text
                x={node.cx}
                y={node.cy + 4}
                textAnchor="middle"
                fill="#e2e8f0"
                fontSize="11"
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
        return (
          <g key={node.id}>
            <rect
              x={x}
              y={y}
              width={node.width}
              height={node.height}
              rx={isHitl ? 2 : 8}
              fill={isHitl ? "#1e293b" : "#0f172a"}
              stroke={isHitl ? "#fbbf24" : "#38bdf8"}
              strokeWidth={1.5}
            />
            <text
              x={node.cx}
              y={node.cy + 4}
              textAnchor="middle"
              fill="#e2e8f0"
              fontSize={isHitl ? 9 : 10}
            >
              {node.label.length > 8 ? `${node.label.slice(0, 7)}…` : node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
