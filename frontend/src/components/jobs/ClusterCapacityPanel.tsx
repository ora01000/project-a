import { useMemo, useState } from "react";

import { useTheme } from "../../context/ThemeContext";

interface ResourceCapacity {
  capacity: number;
  request: number;
  limit: number;
}

export interface NodeShapeCapacity {
  node_name: string;
  cpu: ResourceCapacity;
  mem: ResourceCapacity;
}

export interface PvcShapeCapacity {
  name: string;
  capacity: number | null;
  used: number | null;
  namespace: string;
  deployment_name: string;
  storage_class: string;
  access_mode: string;
}

export interface ClusterShapeCapacity {
  cluster_name: string;
  infra_type: string;
  supported: boolean;
  node_count: number;
  include_all_nodes: boolean;
  cpu: ResourceCapacity | null;
  mem: ResourceCapacity | null;
  nodes?: NodeShapeCapacity[];
  storages?: PvcShapeCapacity[];
}

function formatMetric(value: number, digits = 2): string {
  if (!Number.isFinite(value)) {
    return "-";
  }
  const fixed = value.toFixed(digits);
  return fixed.replace(/\.?0+$/, "");
}

function ratioPct(numer: number, denom: number): number | null {
  if (!Number.isFinite(numer) || !Number.isFinite(denom) || denom <= 0) {
    return null;
  }
  return (numer / denom) * 100;
}

function formatPct(value: number | null): string {
  if (value == null) {
    return "-";
  }
  return `${formatMetric(value, 1)}%`;
}

function ringDash(request: number, capacity: number, radius: number): { used: number; free: number } {
  const circumference = 2 * Math.PI * radius;
  const rawRatio = capacity > 0 ? request / capacity : 0;
  const clamped = Math.min(Math.max(rawRatio, 0), 1);
  return { used: circumference * clamped, free: circumference * (1 - clamped) };
}

function usedStrokeColor(
  request: number,
  capacity: number,
  isLight: boolean,
  kind: "cpu" | "mem" | "storage",
): string {
  const over = capacity > 0 && request > capacity;
  if (over) {
    return isLight ? "#e11d48" : "#fb7185";
  }
  if (kind === "cpu") {
    return isLight ? "#0284c7" : "#38bdf8";
  }
  if (kind === "storage") {
    return isLight ? "#db2777" : "#f472b6";
  }
  return isLight ? "#059669" : "#34d399";
}

function RequestDonut({
  cpu,
  mem,
}: {
  cpu: ResourceCapacity;
  mem: ResourceCapacity;
}) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const size = 148;
  const cx = size / 2;
  const cy = size / 2;
  const outerStroke = 12;
  const innerStroke = 10;
  const gap = 4;
  const outerRadius = size / 2 - outerStroke / 2 - 1;
  const innerRadius = outerRadius - outerStroke / 2 - gap - innerStroke / 2;
  const cpuDash = ringDash(cpu.request, cpu.capacity, outerRadius);
  const memDash = ringDash(mem.request, mem.capacity, innerRadius);
  const cpuPct = ratioPct(cpu.request, cpu.capacity);
  const memPct = ratioPct(mem.request, mem.capacity);
  const cpuStroke = usedStrokeColor(cpu.request, cpu.capacity, isLight, "cpu");
  const memStroke = usedStrokeColor(mem.request, mem.capacity, isLight, "mem");

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="block">
        <circle
          cx={cx}
          cy={cy}
          r={outerRadius}
          fill="none"
          className="shape-donut-track"
          stroke="#1e293b"
          strokeWidth={outerStroke}
        />
        <circle
          cx={cx}
          cy={cy}
          r={outerRadius}
          fill="none"
          stroke={cpuStroke}
          strokeWidth={outerStroke}
          strokeLinecap="butt"
          strokeDasharray={`${cpuDash.used} ${cpuDash.free}`}
          transform={`rotate(-90 ${cx} ${cy})`}
        />
        <circle
          cx={cx}
          cy={cy}
          r={innerRadius}
          fill="none"
          className="shape-donut-track"
          stroke="#1e293b"
          strokeWidth={innerStroke}
        />
        <circle
          cx={cx}
          cy={cy}
          r={innerRadius}
          fill="none"
          stroke={memStroke}
          strokeWidth={innerStroke}
          strokeLinecap="butt"
          strokeDasharray={`${memDash.used} ${memDash.free}`}
          transform={`rotate(-90 ${cx} ${cy})`}
        />
        <text
          x={cx}
          y={cy - 8}
          textAnchor="middle"
          fill={cpuStroke}
          className="text-[12px] font-semibold"
        >
          CPU {formatPct(cpuPct)}
        </text>
        <text
          x={cx}
          y={cy + 12}
          textAnchor="middle"
          fill={memStroke}
          className="text-[12px] font-semibold"
        >
          MEM {formatPct(memPct)}
        </text>
      </svg>
    </div>
  );
}

export function ClusterCapacityPanel({
  capacity,
  isLoading,
}: {
  capacity: ClusterShapeCapacity | null;
  isLoading: boolean;
}) {
  const cpuOvercommit = capacity?.cpu
    ? ratioPct(capacity.cpu.limit, capacity.cpu.capacity)
    : null;
  const memOvercommit = capacity?.mem
    ? ratioPct(capacity.mem.limit, capacity.mem.capacity)
    : null;

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
      <h3 className="mb-2 shrink-0 text-xs font-semibold text-slate-300">클러스터 용량</h3>
      {isLoading && !capacity ? (
        <p className="text-xs text-slate-500">불러오는 중...</p>
      ) : !capacity ? (
        <p className="text-xs text-slate-500">클러스터를 선택해 주세요.</p>
      ) : !capacity.supported ? (
        <p className="text-xs text-slate-500">이 인프라 유형의 클러스터 용량은 준비 중입니다.</p>
      ) : !capacity.cpu || !capacity.mem ? (
        <p className="text-xs text-slate-500">용량 데이터가 없습니다.</p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col items-center gap-2">
          <RequestDonut cpu={capacity.cpu} mem={capacity.mem} />
          <div className="w-full text-center">
            <p className="text-[10px] text-slate-500">
              {capacity.infra_type === "vSphere"
                ? "가상화비율"
                : "가상화비율 (Limit 기준)"}
            </p>
            <p className="mt-0.5 font-mono text-[12px] text-slate-100">
              CPU {formatPct(cpuOvercommit)}
              <span className="mx-2 text-slate-600">·</span>
              MEM {formatPct(memOvercommit)}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function RatioBar({
  kind,
  request,
  capacity,
}: {
  kind: "cpu" | "mem";
  request: number;
  capacity: number;
}) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const pct = ratioPct(request, capacity);
  const widthPct = capacity > 0 ? Math.min(Math.max((request / capacity) * 100, 0), 100) : 0;
  const fill = usedStrokeColor(request, capacity, isLight, kind);
  return (
    <div className="relative h-4 overflow-hidden rounded-sm bg-slate-800 shape-bar-track">
      <div className="h-full" style={{ width: `${widthPct}%`, backgroundColor: fill }} />
      <span className="absolute inset-0 flex items-center justify-center font-mono text-[10px] font-semibold text-white [text-shadow:0_0_3px_rgba(0,0,0,0.85)]">
        {kind === "cpu" ? "CPU " : "MEM "}
        {formatPct(pct)}
      </span>
    </div>
  );
}

export function NodeCapacityPanel({
  capacity,
  isLoading,
}: {
  capacity: ClusterShapeCapacity | null;
  isLoading: boolean;
}) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const [sortKey, setSortKey] = useState<"cpu" | "mem">("cpu");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const nodes = useMemo(() => {
    const list = [...(capacity?.nodes ?? [])];
    list.sort((left, right) => {
      const leftRes = sortKey === "cpu" ? left.cpu : left.mem;
      const rightRes = sortKey === "cpu" ? right.cpu : right.mem;
      const leftRatio = leftRes.capacity > 0 ? leftRes.request / leftRes.capacity : -1;
      const rightRatio = rightRes.capacity > 0 ? rightRes.request / rightRes.capacity : -1;
      const delta = rightRatio - leftRatio;
      return sortDir === "desc" ? delta : -delta;
    });
    return list.slice(0, 5);
  }, [capacity?.nodes, sortKey, sortDir]);
  const showNodes =
    capacity?.infra_type === "k8s" ||
    capacity?.infra_type === "kubernetes" ||
    capacity?.infra_type === "kubevirt" ||
    capacity?.infra_type === "vSphere";
  const isVsphere = capacity?.infra_type === "vSphere";
  const panelTitle = isVsphere ? "호스트별 용량" : "노드별 용량";
  const emptyLabel = isVsphere ? "호스트가 없습니다." : "워커 노드가 없습니다.";
  const showSort = showNodes && (capacity?.nodes?.length ?? 0) > 0;

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
      <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-slate-300">{panelTitle}</h3>
        {showSort ? (
          <div className="flex shrink-0 gap-1">
            {(["cpu", "mem"] as const).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  if (sortKey === key) {
                    setSortDir((current) => (current === "desc" ? "asc" : "desc"));
                    return;
                  }
                  setSortKey(key);
                  setSortDir("desc");
                }}
                className={
                  sortKey === key
                    ? isLight
                      ? "rounded border border-sky-600 bg-sky-600 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                      : "rounded border border-sky-700 bg-sky-950/50 px-1.5 py-0.5 text-[10px] font-medium text-sky-200"
                    : isLight
                      ? "rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[10px] text-slate-600 hover:border-sky-400 hover:text-sky-700"
                      : "rounded border border-slate-700 bg-slate-900/60 px-1.5 py-0.5 text-[10px] text-slate-400 hover:border-slate-600 hover:text-slate-200"
                }
              >
                {key === "cpu" ? "CPU" : "MEM"}
                {sortKey === key ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {isLoading && !capacity ? (
        <p className="text-xs text-slate-500">불러오는 중...</p>
      ) : !capacity ? (
        <p className="text-xs text-slate-500">클러스터를 선택해 주세요.</p>
      ) : !showNodes ? (
        <p className="text-xs text-slate-500">이 인프라 유형의 노드별 용량은 준비 중입니다.</p>
      ) : nodes.length === 0 ? (
        <p className="text-xs text-slate-500">{emptyLabel}</p>
      ) : (
        <div className="min-h-0 max-h-[13rem] flex-1 space-y-2 overflow-x-hidden overflow-y-auto pr-1">
          {nodes.map((node) => (
            <div key={node.node_name} className="flex min-w-0 items-center gap-2">
              <div
                className="min-w-0 max-w-[38%] basis-[38%] truncate whitespace-nowrap font-mono text-[11px] text-slate-200"
                title={node.node_name}
              >
                {node.node_name}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <RatioBar kind="cpu" request={node.cpu.request} capacity={node.cpu.capacity} />
                <RatioBar kind="mem" request={node.mem.request} capacity={node.mem.capacity} />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function StorageRatioBar({
  used,
  capacity,
}: {
  used: number | null;
  capacity: number | null;
}) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const hasUsed = used != null && Number.isFinite(used);
  const cap = capacity != null && Number.isFinite(capacity) ? capacity : 0;
  if (!hasUsed) {
    return (
      <div className="relative h-4 overflow-hidden rounded-sm bg-slate-800 shape-bar-track">
        <span className="absolute inset-0 flex items-center justify-center font-mono text-[10px] font-semibold text-slate-200 [text-shadow:0_0_3px_rgba(0,0,0,0.85)]">
          용량: {capacity == null ? "-" : capacity}
        </span>
      </div>
    );
  }
  const pct = ratioPct(used, cap);
  const widthPct = cap > 0 ? Math.min(Math.max((used / cap) * 100, 0), 100) : 0;
  const fill = usedStrokeColor(used, cap, isLight, "storage");
  return (
    <div className="relative h-4 overflow-hidden rounded-sm bg-slate-800 shape-bar-track">
      <div className="h-full" style={{ width: `${widthPct}%`, backgroundColor: fill }} />
      <span className="absolute inset-0 flex items-center justify-center font-mono text-[10px] font-semibold text-white [text-shadow:0_0_3px_rgba(0,0,0,0.85)]">
        {formatPct(pct)}
      </span>
    </div>
  );
}

function pvcUsageRatio(pvc: PvcShapeCapacity): number {
  if (pvc.used == null || !Number.isFinite(pvc.used)) {
    return -1;
  }
  if (pvc.capacity == null || !Number.isFinite(pvc.capacity) || pvc.capacity <= 0) {
    return -1;
  }
  return pvc.used / pvc.capacity;
}

function storageTooltip(infraType: string | undefined, pvc: PvcShapeCapacity): string {
  if (infraType === "vSphere") {
    return [pvc.namespace, pvc.storage_class, pvc.access_mode].join("/");
  }
  return [pvc.namespace, pvc.deployment_name, pvc.storage_class, pvc.access_mode].join("/");
}

export function StorageCapacityPanel({
  capacity,
  isLoading,
}: {
  capacity: ClusterShapeCapacity | null;
  isLoading: boolean;
}) {
  const isVsphere = capacity?.infra_type === "vSphere";
  const storages = useMemo(() => {
    const list = [...(capacity?.storages ?? [])];
    list.sort((left, right) => pvcUsageRatio(right) - pvcUsageRatio(left));
    return list.slice(0, 5);
  }, [capacity?.storages]);
  const showStorage =
    capacity?.infra_type === "k8s" ||
    capacity?.infra_type === "kubernetes" ||
    capacity?.infra_type === "kubevirt" ||
    isVsphere;
  const emptyLabel = isVsphere ? "데이터스토어가 없습니다." : "PVC가 없습니다.";

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
      <h3 className="mb-2 shrink-0 text-xs font-semibold text-slate-300">저장소 용량</h3>
      {isLoading && !capacity ? (
        <p className="text-xs text-slate-500">불러오는 중...</p>
      ) : !capacity ? (
        <p className="text-xs text-slate-500">클러스터를 선택해 주세요.</p>
      ) : !showStorage ? (
        <p className="text-xs text-slate-500">이 인프라 유형의 저장소 용량은 준비 중입니다.</p>
      ) : storages.length === 0 ? (
        <p className="text-xs text-slate-500">{emptyLabel}</p>
      ) : (
        <div className="min-h-0 max-h-[13rem] flex-1 space-y-2 overflow-x-hidden overflow-y-auto pr-1">
          {storages.map((pvc, index) => {
            const tooltip = storageTooltip(capacity?.infra_type, pvc);
            return (
              <div
                key={`${pvc.namespace}/${pvc.name}/${index}`}
                className="flex min-w-0 items-center gap-2"
                title={tooltip}
              >
                <div
                  className="min-w-0 max-w-[38%] basis-[38%] truncate whitespace-nowrap font-mono text-[11px] text-slate-200"
                  title={tooltip}
                >
                  {pvc.name}
                </div>
                <div className="min-w-0 flex-1">
                  <StorageRatioBar used={pvc.used} capacity={pvc.capacity} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
