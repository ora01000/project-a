import { useMemo, useState } from "react";

import type { AgentInfo, HealthInfo } from "../types/agent";
import type { TopologyEdge, TopologyNode } from "../types/topology";
import { LLM_NODE_ID, agentNodeId, mcpNodeId } from "../types/topology";
import { useTopology } from "../context/TopologyContext";
import { connectionStatusFill, connectionStatusStroke } from "../utils/agentStatusStyle";

interface TopologyMapProps {
  agents: AgentInfo[];
  health: HealthInfo | null;
  embedded?: boolean;
}

interface NodePosition {
  x: number;
  y: number;
}

const SVG_WIDTH = 960;
const BASE_SVG_HEIGHT = 300;

const AGENT_NODE_WIDTH = 103;
const AGENT_NODE_HEIGHT = 42;
const MCP_NODE_WIDTH = 108;
const MCP_NODE_HEIGHT = 44;
const LLM_NODE_WIDTH = 120;
const LLM_NODE_HEIGHT = 44;

const NODE_VERTICAL_GAP = 14;
const NODE_HORIZONTAL_GAP = 18;
const REGULAR_COLUMNS = 2;
const LLM_LEFT_X = 118;
const REGULAR_TOP = 34;
const SYSTEM_BOTTOM_PADDING = 28;
const MCP_RIGHT_X = 820;

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.1;
const ZOOM_DEFAULT = 1;

interface LayoutMetrics {
  svgWidth: number;
  svgHeight: number;
  regularAgents: TopologyNode[];
  systemAgents: TopologyNode[];
  mcps: TopologyNode[];
}

function getNodeDimensions(kind: TopologyNode["kind"]): { width: number; height: number } {
  if (kind === "llm") {
    return { width: LLM_NODE_WIDTH, height: LLM_NODE_HEIGHT };
  }
  if (kind === "agent") {
    return { width: AGENT_NODE_WIDTH, height: AGENT_NODE_HEIGHT };
  }
  return { width: MCP_NODE_WIDTH, height: MCP_NODE_HEIGHT };
}

function computeLayoutMetrics(nodes: TopologyNode[]): LayoutMetrics {
  const regularAgents = nodes.filter((node) => node.kind === "agent" && !node.isSystem);
  const systemAgents = nodes.filter((node) => node.kind === "agent" && node.isSystem);
  const mcps = nodes.filter((node) => node.kind === "mcp");

  const regularRows = Math.max(1, Math.ceil(regularAgents.length / REGULAR_COLUMNS));
  const regularZoneHeight =
    regularRows * AGENT_NODE_HEIGHT + Math.max(0, regularRows - 1) * NODE_VERTICAL_GAP;

  const mcpZoneHeight =
    mcps.length > 0
      ? mcps.length * MCP_NODE_HEIGHT + Math.max(0, mcps.length - 1) * NODE_VERTICAL_GAP
      : 0;

  const systemZoneHeight = systemAgents.length > 0 ? AGENT_NODE_HEIGHT + SYSTEM_BOTTOM_PADDING : 0;
  const mainZoneHeight = Math.max(regularZoneHeight, mcpZoneHeight, LLM_NODE_HEIGHT + 20);
  const svgHeight = Math.max(
    BASE_SVG_HEIGHT,
    REGULAR_TOP + mainZoneHeight + 36 + systemZoneHeight,
  );

  return {
    svgWidth: SVG_WIDTH,
    svgHeight,
    regularAgents,
    systemAgents,
    mcps,
  };
}

function computePositions(metrics: LayoutMetrics): Record<string, NodePosition> {
  const { svgWidth, svgHeight, regularAgents, systemAgents, mcps } = metrics;
  const positions: Record<string, NodePosition> = {};

  const regularRows = Math.max(1, Math.ceil(regularAgents.length / REGULAR_COLUMNS));
  const regularZoneHeight =
    regularRows * AGENT_NODE_HEIGHT + Math.max(0, regularRows - 1) * NODE_VERTICAL_GAP;
  const regularZoneCenterY = REGULAR_TOP + regularZoneHeight / 2;

  const regularBlockWidth =
    REGULAR_COLUMNS * AGENT_NODE_WIDTH + (REGULAR_COLUMNS - 1) * NODE_HORIZONTAL_GAP;
  const regularCenterStartX = svgWidth * 0.5 - regularBlockWidth / 2;
  const regularColumn1X = regularCenterStartX + AGENT_NODE_WIDTH / 2;
  const regularColumn2X = regularCenterStartX + AGENT_NODE_WIDTH + NODE_HORIZONTAL_GAP + AGENT_NODE_WIDTH / 2;

  regularAgents.forEach((node, index) => {
    const column = index % REGULAR_COLUMNS;
    const row = Math.floor(index / REGULAR_COLUMNS);
    positions[node.id] = {
      x: column === 0 ? regularColumn1X : regularColumn2X,
      y: REGULAR_TOP + AGENT_NODE_HEIGHT / 2 + row * (AGENT_NODE_HEIGHT + NODE_VERTICAL_GAP),
    };
  });

  positions[LLM_NODE_ID] = { x: LLM_LEFT_X + LLM_NODE_WIDTH / 2, y: regularZoneCenterY };

  const systemY = svgHeight - SYSTEM_BOTTOM_PADDING - AGENT_NODE_HEIGHT / 2;
  const systemSpacing = AGENT_NODE_WIDTH + NODE_HORIZONTAL_GAP;
  const systemTotalWidth =
    systemAgents.length > 0
      ? systemAgents.length * AGENT_NODE_WIDTH + Math.max(0, systemAgents.length - 1) * NODE_HORIZONTAL_GAP
      : 0;
  const systemStartX = (svgWidth - systemTotalWidth) / 2 + AGENT_NODE_WIDTH / 2;

  systemAgents.forEach((node, index) => {
    positions[node.id] = {
      x: systemStartX + index * systemSpacing,
      y: systemY,
    };
  });

  const mcpZoneHeight =
    mcps.length > 0
      ? mcps.length * MCP_NODE_HEIGHT + Math.max(0, mcps.length - 1) * NODE_VERTICAL_GAP
      : 0;
  const mcpTop = REGULAR_TOP + Math.max(0, (regularZoneHeight - mcpZoneHeight) / 2);

  mcps.forEach((node, index) => {
    positions[node.id] = {
      x: MCP_RIGHT_X,
      y: mcpTop + MCP_NODE_HEIGHT / 2 + index * (MCP_NODE_HEIGHT + NODE_VERTICAL_GAP),
    };
  });

  return positions;
}

const SYSTEM_AGENT_ORDER = [
  "inventory",
  "sys-inventory",
  "sys-whatap-events",
  "sys-job-planning",
  "sys-job-execution",
];

function isTopologySystemAgent(agent: AgentInfo): boolean {
  return Boolean(agent.is_system) || agent.id === "inventory" || agent.name === "인벤토리";
}

function systemAgentSortIndex(agentId: string): number {
  const index = SYSTEM_AGENT_ORDER.indexOf(agentId);
  return index === -1 ? SYSTEM_AGENT_ORDER.length : index;
}

function buildNodes(agents: AgentInfo[], health: HealthInfo | null): TopologyNode[] {
  const mcpIds = new Set<string>();
  for (const agent of agents) {
    for (const server of agent.mcp_servers) {
      mcpIds.add(server);
    }
  }
  if (health?.mcp) {
    for (const server of Object.keys(health.mcp)) {
      mcpIds.add(server);
    }
  }

  const nodes: TopologyNode[] = [
    {
      id: LLM_NODE_ID,
      kind: "llm",
      label: "Local LLM",
      status: health?.llm ?? "unknown",
    },
  ];

  const sortedAgents = [...agents].sort((left, right) => {
    const leftSystem = isTopologySystemAgent(left);
    const rightSystem = isTopologySystemAgent(right);
    if (leftSystem !== rightSystem) {
      return leftSystem ? 1 : -1;
    }
    if (leftSystem && rightSystem) {
      return systemAgentSortIndex(left.id) - systemAgentSortIndex(right.id);
    }
    return left.name.localeCompare(right.name, "ko");
  });

  for (const agent of sortedAgents) {
    nodes.push({
      id: agentNodeId(agent.id),
      kind: "agent",
      label: agent.name,
      status: agent.status,
      isSystem: isTopologySystemAgent(agent),
    });
  }

  for (const serverId of [...mcpIds].sort()) {
    nodes.push({
      id: mcpNodeId(serverId),
      kind: "mcp",
      label: serverId,
      status: health?.mcp?.[serverId] ?? "unknown",
    });
  }

  return nodes;
}

function buildEdges(agents: AgentInfo[]): TopologyEdge[] {
  const edges: TopologyEdge[] = [];

  for (const agent of agents) {
    edges.push({
      id: `${agentNodeId(agent.id)}->${LLM_NODE_ID}`,
      from: agentNodeId(agent.id),
      to: LLM_NODE_ID,
    });

    for (const server of agent.mcp_servers) {
      edges.push({
        id: `${agentNodeId(agent.id)}->${mcpNodeId(server)}`,
        from: agentNodeId(agent.id),
        to: mcpNodeId(server),
      });
    }
  }

  return edges;
}

function isFlowActive(flowFrom: string, flowTo: string, edgeFrom: string, edgeTo: string): boolean {
  return flowFrom === edgeFrom && flowTo === edgeTo;
}

function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));
}

export function TopologyMap({ agents, health, embedded = false }: TopologyMapProps) {
  const { activeFlows } = useTopology();
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);

  const nodes = useMemo(() => buildNodes(agents, health), [agents, health]);
  const edges = useMemo(() => buildEdges(agents), [agents]);
  const layout = useMemo(() => computeLayoutMetrics(nodes), [nodes]);
  const positions = useMemo(() => computePositions(layout), [layout]);

  const displayWidth = Math.round(layout.svgWidth * zoom);
  const displayHeight = Math.round(layout.svgHeight * zoom);
  const zoomPercent = Math.round(zoom * 100);

  const content = (
    <>
      {!embedded ? (
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-normal text-slate-200">Topology Map</h2>
          <p className="text-[10px] text-slate-500">에이전트 · LLM · MCP 호출 관계</p>
        </div>
      ) : null}

      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-auto">
        <div className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900/95 p-1 shadow-lg">
          <button
            type="button"
            onClick={() => setZoom((current) => clampZoom(current - ZOOM_STEP))}
            disabled={zoom <= ZOOM_MIN}
            aria-label="축소"
            title="축소"
            className="flex h-7 w-7 items-center justify-center rounded text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
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
            className="flex h-7 w-7 items-center justify-center rounded text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            +
          </button>
        </div>

        <svg
          viewBox={`0 0 ${layout.svgWidth} ${layout.svgHeight}`}
          width={displayWidth}
          height={displayHeight}
          className="block shrink-0"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#64748b" />
            </marker>
            <marker id="arrow-active" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#38bdf8" />
            </marker>
          </defs>

          {edges.map((edge) => {
            const from = positions[edge.from];
            const to = positions[edge.to];
            if (!from || !to) {
              return null;
            }

            const isActive = activeFlows.some((flow) => isFlowActive(flow.from, flow.to, edge.from, edge.to));

            return (
              <g key={edge.id}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={isActive ? "#38bdf8" : "#334155"}
                  strokeWidth={isActive ? 2.5 : 1.5}
                  markerEnd={isActive ? "url(#arrow-active)" : "url(#arrow)"}
                  className={isActive ? "topology-flow-line" : undefined}
                />
              </g>
            );
          })}

          {nodes.map((node) => {
            const position = positions[node.id];
            if (!position) {
              return null;
            }

            const { width, height } = getNodeDimensions(node.kind);
            const x = position.x - width / 2;
            const y = position.y - height / 2;
            const stroke = connectionStatusStroke(node.status);
            const fill = connectionStatusFill(node.status);

            return (
              <g key={node.id}>
                <rect
                  x={x}
                  y={y}
                  rx={10}
                  ry={10}
                  width={width}
                  height={height}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={1.5}
                />
                <text
                  x={position.x}
                  y={position.y - 4}
                  textAnchor="middle"
                  fill="#f1f5f9"
                  fontSize="9"
                  fontWeight="400"
                >
                  {node.label.length > 16 ? `${node.label.slice(0, 15)}…` : node.label}
                </text>
                <text
                  x={position.x}
                  y={position.y + 12}
                  textAnchor="middle"
                  fill="#94a3b8"
                  fontSize="7"
                  fontWeight="400"
                  style={{ textTransform: "uppercase" }}
                >
                  {node.kind} · {node.status}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </>
  );

  if (embedded) {
    return <div className="flex min-h-0 flex-1 flex-col">{content}</div>;
  }

  return (
    <section className="mt-8 flex min-h-[320px] flex-col rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      {content}
    </section>
  );
}
