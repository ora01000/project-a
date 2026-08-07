import { useCallback, useEffect, useMemo, useState } from "react";

interface ShapeCluster {
  idx: number;
  cluster_name: string;
  last_update: string | null;
}

interface ShapeCounts {
  nodes: number;
  namespaces: number;
  deployments: number;
  pvcs: number;
}

interface ShapeHistoryPoint {
  label: string;
  stamp: string | null;
  is_latest: boolean;
  counts: ShapeCounts;
}

interface ShapeAnalysis {
  cluster_name: string;
  last_update: string | null;
  cluster_version: string | null;
  summary: ShapeCounts;
  history: ShapeHistoryPoint[];
}

interface InfraShapeTabProps {
  active: boolean;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string | Array<{ msg?: string }> }
    | null;
  if (!payload?.detail) {
    return fallback;
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => item.msg ?? JSON.stringify(item)).join(", ") || fallback;
  }
  return fallback;
}

const SERIES: { key: keyof ShapeCounts; label: string; color: string }[] = [
  { key: "nodes", label: "Nodes", color: "#38bdf8" },
  { key: "namespaces", label: "Namespaces", color: "#34d399" },
  { key: "deployments", label: "Deployments", color: "#fbbf24" },
  { key: "pvcs", label: "PVCs", color: "#f472b6" },
];

function clusterButtonClass(isSelected: boolean): string {
  if (isSelected) {
    return "border-sky-600 bg-sky-950/60 text-sky-100";
  }
  return "border-slate-700 bg-slate-900/80 text-slate-300 hover:border-slate-600 hover:bg-slate-800/60";
}

function ShapeTrendChart({ history }: { history: ShapeHistoryPoint[] }) {
  const width = 640;
  const height = 220;
  const padding = { top: 16, right: 16, bottom: 40, left: 40 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const maxValue = useMemo(() => {
    let peak = 1;
    for (const point of history) {
      for (const series of SERIES) {
        peak = Math.max(peak, point.counts[series.key]);
      }
    }
    return peak;
  }, [history]);

  if (history.length === 0) {
    return <p className="text-xs text-slate-500">추이 데이터가 없습니다.</p>;
  }

  const xFor = (index: number) => {
    if (history.length === 1) {
      return padding.left + innerW / 2;
    }
    return padding.left + (index / (history.length - 1)) * innerW;
  };
  const yFor = (value: number) =>
    padding.top + innerH - (value / maxValue) * innerH;

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full min-w-[480px]">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding.top + innerH * (1 - ratio);
          const value = Math.round(maxValue * ratio);
          return (
            <g key={ratio}>
              <line
                x1={padding.left}
                x2={width - padding.right}
                y1={y}
                y2={y}
                stroke="#334155"
                strokeWidth={1}
              />
              <text x={padding.left - 8} y={y + 3} textAnchor="end" className="fill-slate-500 text-[10px]">
                {value}
              </text>
            </g>
          );
        })}

        {SERIES.map((series) => {
          const points = history
            .map((point, index) => `${xFor(index)},${yFor(point.counts[series.key])}`)
            .join(" ");
          return (
            <g key={series.key}>
              <polyline
                fill="none"
                stroke={series.color}
                strokeWidth={2}
                points={points}
              />
              {history.map((point, index) => (
                <circle
                  key={`${series.key}-${index}`}
                  cx={xFor(index)}
                  cy={yFor(point.counts[series.key])}
                  r={3}
                  fill={series.color}
                />
              ))}
            </g>
          );
        })}

        {history.map((point, index) => (
          <text
            key={`label-${index}`}
            x={xFor(index)}
            y={height - 12}
            textAnchor="middle"
            className="fill-slate-400 text-[9px]"
          >
            {point.is_latest ? "latest" : point.label.slice(5, 16)}
          </text>
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3">
        {SERIES.map((series) => (
          <span key={series.key} className="inline-flex items-center gap-1.5 text-[11px] text-slate-300">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: series.color }} />
            {series.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function InfraShapeTab({ active }: InfraShapeTabProps) {
  const [clusters, setClusters] = useState<ShapeCluster[]>([]);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<ShapeAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);

  const loadClusters = useCallback(async () => {
    setIsLoadingList(true);
    setError(null);
    try {
      const response = await fetch("/api/k8s-infra/shape/clusters");
      if (!response.ok) {
        throw new Error(await parseError(response, "인프라 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as ShapeCluster[];
      setClusters(data);
      setSelectedName((current) => {
        if (current && data.some((item) => item.cluster_name === current)) {
          return current;
        }
        return data[0]?.cluster_name ?? null;
      });
    } catch (err) {
      setClusters([]);
      setSelectedName(null);
      setError(err instanceof Error ? err.message : "인프라 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoadingList(false);
    }
  }, []);

  const loadAnalysis = useCallback(async (clusterName: string) => {
    setIsLoadingAnalysis(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}`,
      );
      if (!response.ok) {
        throw new Error(await parseError(response, "형상 정보를 불러오지 못했습니다."));
      }
      const data = (await response.json()) as ShapeAnalysis;
      setAnalysis(data);
    } catch (err) {
      setAnalysis(null);
      setError(err instanceof Error ? err.message : "형상 정보를 불러오지 못했습니다.");
    } finally {
      setIsLoadingAnalysis(false);
    }
  }, []);

  useEffect(() => {
    if (!active) {
      return;
    }
    void loadClusters();
  }, [active, loadClusters]);

  useEffect(() => {
    if (!active || !selectedName) {
      return;
    }
    void loadAnalysis(selectedName);
  }, [active, selectedName, loadAnalysis]);

  const summaryItems = useMemo(() => {
    if (!analysis) {
      return [];
    }
    return [
      { label: "클러스터 이름", value: analysis.cluster_name },
      { label: "클러스터 버전", value: analysis.cluster_version ?? "-" },
      { label: "노드 개수", value: String(analysis.summary.nodes) },
      { label: "네임스페이스(프로젝트) 개수", value: String(analysis.summary.namespaces) },
      { label: "배포 개수", value: String(analysis.summary.deployments) },
      { label: "PVC 개수", value: String(analysis.summary.pvcs) },
    ];
  }, [analysis]);

  return (
    <div className="flex min-h-0 flex-1 gap-3 p-3">
      <aside className="flex w-[148px] shrink-0 flex-col border-r border-slate-700/80 pr-3">
        <h3 className="mb-2 text-xs font-semibold text-slate-300">인프라 목록</h3>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain">
          {isLoadingList && clusters.length === 0 ? (
            <p className="text-xs text-slate-500">불러오는 중...</p>
          ) : null}
          {!isLoadingList && clusters.length === 0 ? (
            <p className="text-xs text-slate-500">등록된 클러스터가 없습니다.</p>
          ) : null}
          {clusters.map((cluster) => {
            const isSelected = cluster.cluster_name === selectedName;
            return (
              <button
                key={cluster.idx}
                type="button"
                onClick={() => setSelectedName(cluster.cluster_name)}
                className={`block w-full rounded-full border px-2.5 py-1 text-left text-[11px] font-medium transition-colors ${clusterButtonClass(isSelected)}`}
                title={cluster.last_update ? `last_update: ${cluster.last_update}` : cluster.cluster_name}
              >
                {cluster.cluster_name}
              </button>
            );
          })}
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        {error ? (
          <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <section className="shrink-0 rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
          <h3 className="mb-2 text-xs font-semibold text-slate-300">요약</h3>
          {isLoadingAnalysis && !analysis ? (
            <p className="text-xs text-slate-500">불러오는 중...</p>
          ) : !analysis ? (
            <p className="text-xs text-slate-500">클러스터를 선택해 주세요.</p>
          ) : (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
              {summaryItems.map((item) => (
                <div key={item.label} className="min-w-0">
                  <dt className="text-[11px] text-slate-500">{item.label}</dt>
                  <dd className="truncate font-mono text-sm text-slate-100" title={item.value}>
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        <section className="flex min-h-0 flex-1 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
          <h3 className="mb-1 text-xs font-semibold text-slate-300">형상 변경 추이</h3>
          <p className="mb-2 text-[11px] text-slate-500">
            최신 테이블과 백업(최대 4세대) 기준 개수 변화
          </p>
          <div className="min-h-0 flex-1 overflow-auto">
            {analysis ? <ShapeTrendChart history={analysis.history} /> : (
              <p className="text-xs text-slate-500">추이 차트를 표시할 클러스터가 없습니다.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
