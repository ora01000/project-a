import type { ToolUsage } from "../types/agent";

interface ToolUsageListProps {
  tools: ToolUsage[];
}

export function ToolUsageList({ tools }: ToolUsageListProps) {
  if (tools.length === 0) {
    return <p className="mb-2 text-[10px] text-slate-500">사용된 MCP 도구 없음</p>;
  }

  return (
    <div className="mb-2 flex flex-wrap gap-1">
      {tools.map((tool, index) => (
        <span
          key={`${index}-${tool.mcp_server ?? "unknown"}-${tool.name}`}
          className="rounded-full border border-emerald-700/60 bg-emerald-950/50 px-2 py-0.5 text-[10px] text-emerald-200"
          title={tool.mcp_server ? `MCP: ${tool.mcp_server}` : undefined}
        >
          {tool.mcp_server ? `${tool.mcp_server}/` : ""}
          {tool.name}
        </span>
      ))}
    </div>
  );
}
