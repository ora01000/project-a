import { useMemo } from "react";

import type { AgentInfo, HealthInfo } from "../types/agent";
import type { TopologyEdge, TopologyNode } from "../types/topology";
import { LLM_NODE_ID, agentNodeId, mcpNodeId } from "../types/topology";
import { useTopology } from "../context/TopologyContext";

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
const SVG_HEIGHT = 240;

function statusStroke(status: string): string {
  if (status === "connected") {
    return "#34d399";
  }
  if (status === "partial" || status === "disabled") {
    return "#fbbf24";
  }
  return "#f87171";
}

function statusFill(status: string): string {
  if (status === "connected") {
    return "#064e3b";
  }
  if (status === "partial" || status === "disabled") {
    return "#451a03";
  }
  return "#450a0a";
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

  for (const agent of agents) {
    nodes.push({
      id: agentNodeId(agent.id),
      kind: "agent",
      label: agent.name,
      status: agent.status,
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

function computePositions(nodes: TopologyNode[]): Record<string, NodePosition> {
  const agents = nodes.filter((node) => node.kind === "agent");
  const mcps = nodes.filter((node) => node.kind === "mcp");
  const positions: Record<string, NodePosition> = {};

  positions[LLM_NODE_ID] = { x: SVG_WIDTH * 0.5, y: SVG_HEIGHT * 0.5 };

  agents.forEach((node, index) => {
    const yStep = SVG_HEIGHT / (agents.length + 1);
    positions[node.id] = { x: SVG_WIDTH * 0.18, y: yStep * (index + 1) };
  });

  mcps.forEach((node, index) => {
    const yStep = SVG_HEIGHT / (mcps.length + 1);
    positions[node.id] = { x: SVG_WIDTH * 0.82, y: yStep * (index + 1) };
  });

  return positions;
}

function isFlowActive(flowFrom: string, flowTo: string, edgeFrom: string, edgeTo: string): boolean {
  return flowFrom === edgeFrom && flowTo === edgeTo;
}

export function TopologyMap({ agents, health, embedded = false }: TopologyMapProps) {
  const { activeFlows } = useTopology();

  const nodes = useMemo(() => buildNodes(agents, health), [agents, health]);
  const edges = useMemo(() => buildEdges(agents), [agents]);
  const positions = useMemo(() => computePositions(nodes), [nodes]);

  const content = (
    <>
      {!embedded ? (
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Topology Map</h2>
          <p className="text-xs text-slate-500">에이전트 · LLM · MCP 호출 관계</p>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} className="min-w-[960px] w-full">
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

            const width = node.kind === "llm" ? 120 : 108;
            const height = 44;
            const x = position.x - width / 2;
            const y = position.y - height / 2;
            const stroke = statusStroke(node.status);
            const fill = statusFill(node.status);

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
                  fontSize="11"
                  fontWeight="600"
                >
                  {node.label.length > 16 ? `${node.label.slice(0, 15)}…` : node.label}
                </text>
                <text
                  x={position.x}
                  y={position.y + 12}
                  textAnchor="middle"
                  fill="#94a3b8"
                  fontSize="9"
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
    return content;
  }

  return (
    <section className="mt-8 rounded-xl border border-slate-800 bg-slate-900/70 p-4">{content}</section>
  );
}
