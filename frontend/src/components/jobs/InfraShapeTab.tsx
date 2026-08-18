import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useTheme } from "../../context/ThemeContext";
import {
  ClusterCapacityPanel,
  NodeCapacityPanel,
  StorageCapacityPanel,
  type ClusterShapeCapacity,
} from "./ClusterCapacityPanel";
import { ShapeDetailPanel } from "./ShapeDetailPanel";
import { VsphereShapeDetailPanel } from "./VsphereShapeDetailPanel";

interface ShapeCluster {
  idx: number;
  cluster_name: string;
  last_update: string | null;
  infra_type: string;
  display_name?: string;
}

interface ShapeCounts {
  nodes: number;
  namespaces: number;
  deployments: number;
  pvcs: number;
  vms: number;
  volumes: number;
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
  infra_type: string;
  display_name?: string;
  summary: ShapeCounts;
  history: ShapeHistoryPoint[];
}

interface InfraShapeTabProps {
  active: boolean;
  maskIps?: boolean;
  onCopyToNote?: (content: string, noteName?: string) => Promise<void>;
}

type SeriesKey = keyof ShapeCounts;

const BASE_SERIES: { key: SeriesKey; label: string; color: string }[] = [
  { key: "nodes", label: "Nodes", color: "#38bdf8" },
  { key: "namespaces", label: "Namespaces", color: "#34d399" },
  { key: "deployments", label: "Deployments", color: "#fbbf24" },
  { key: "pvcs", label: "PVCs", color: "#f472b6" },
];

const KUBEVIRT_EXTRA_SERIES: { key: SeriesKey; label: string; color: string }[] = [
  { key: "vms", label: "VMs", color: "#a78bfa" },
  { key: "volumes", label: "Volumes", color: "#fb923c" },
];

const VSPHERE_SERIES: { key: SeriesKey; label: string; color: string }[] = [
  { key: "namespaces", label: "Clusters", color: "#34d399" },
  { key: "nodes", label: "Hosts", color: "#38bdf8" },
  { key: "vms", label: "VMs", color: "#a78bfa" },
  { key: "volumes", label: "Datastores", color: "#fb923c" },
];

const BASE_SERIES_LIGHT: { key: SeriesKey; label: string; color: string }[] = [
  { key: "nodes", label: "Nodes", color: "#0284c7" },
  { key: "namespaces", label: "Namespaces", color: "#059669" },
  { key: "deployments", label: "Deployments", color: "#d97706" },
  { key: "pvcs", label: "PVCs", color: "#db2777" },
];

const KUBEVIRT_EXTRA_SERIES_LIGHT: { key: SeriesKey; label: string; color: string }[] = [
  { key: "vms", label: "VMs", color: "#7c3aed" },
  { key: "volumes", label: "Volumes", color: "#ea580c" },
];

const VSPHERE_SERIES_LIGHT: { key: SeriesKey; label: string; color: string }[] = [
  { key: "namespaces", label: "Clusters", color: "#059669" },
  { key: "nodes", label: "Hosts", color: "#0284c7" },
  { key: "vms", label: "VMs", color: "#7c3aed" },
  { key: "volumes", label: "Datastores", color: "#ea580c" },
];

function seriesForInfraType(infraType: string, isLight: boolean) {
  if (infraType === "kubevirt") {
    return isLight
      ? [...BASE_SERIES_LIGHT, ...KUBEVIRT_EXTRA_SERIES_LIGHT]
      : [...BASE_SERIES, ...KUBEVIRT_EXTRA_SERIES];
  }
  if (infraType === "vSphere") {
    return isLight ? VSPHERE_SERIES_LIGHT : VSPHERE_SERIES;
  }
  return isLight ? BASE_SERIES_LIGHT : BASE_SERIES;
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

function clusterButtonClass(isSelected: boolean): string {
  if (isSelected) {
    return "border-sky-600 bg-sky-950/60 text-sky-100";
  }
  return "border-slate-700 bg-slate-900/80 text-slate-300 hover:border-slate-600 hover:bg-slate-800/60";
}

function clusterListLabel(cluster: { cluster_name: string; display_name?: string }): string {
  const display = (cluster.display_name ?? "").trim();
  return display ? `${cluster.cluster_name} ${display}` : cluster.cluster_name;
}

function ShapeTrendChart({
  history,
  infraType,
}: {
  history: ShapeHistoryPoint[];
  infraType: string;
}) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const series = useMemo(() => seriesForInfraType(infraType, isLight), [infraType, isLight]);

  useLayoutEffect(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    const update = () => {
      const rect = node.getBoundingClientRect();
      setSize({
        width: Math.max(0, Math.floor(rect.width)),
        height: Math.max(0, Math.floor(rect.height)),
      });
    };
    update();
    const observer = new ResizeObserver(() => update());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const legendH = 28;
  const width = Math.max(size.width, 1);
  const height = Math.max(size.height - legendH, 1);
  const padding = {
    top: 16,
    right: 16,
    bottom: 36,
    left: 44,
  };
  const innerW = Math.max(width - padding.left - padding.right, 1);
  const innerH = Math.max(height - padding.top - padding.bottom, 1);

  const maxValue = useMemo(() => {
    let peak = 1;
    for (const point of history) {
      for (const item of series) {
        peak = Math.max(peak, point.counts[item.key] ?? 0);
      }
    }
    return peak;
  }, [history, series]);

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
    <div ref={containerRef} className="flex h-full min-h-0 w-full flex-col">
      {size.width > 0 && size.height > 0 ? (
        <>
          <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            className="block min-h-0 w-full flex-1"
          >
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
                    className="shape-chart-grid"
                    stroke="#334155"
                    strokeWidth={1}
                  />
                  <text
                    x={padding.left - 8}
                    y={y + 3}
                    textAnchor="end"
                    className="fill-slate-500 text-[10px]"
                  >
                    {value}
                  </text>
                </g>
              );
            })}

            {series.map((item) => {
              const points = history
                .map((point, index) => `${xFor(index)},${yFor(point.counts[item.key] ?? 0)}`)
                .join(" ");
              return (
                <g key={item.key}>
                  <polyline
                    fill="none"
                    stroke={item.color}
                    strokeWidth={2}
                    points={points}
                  />
                  {history.map((point, index) => (
                    <circle
                      key={`${item.key}-${index}`}
                      cx={xFor(index)}
                      cy={yFor(point.counts[item.key] ?? 0)}
                      r={3}
                      fill={item.color}
                    />
                  ))}
                </g>
              );
            })}

            {history.map((point, index) => (
              <text
                key={`label-${index}`}
                x={xFor(index)}
                y={height - 10}
                textAnchor="middle"
                className="fill-slate-400 text-[9px]"
              >
                {point.is_latest ? "latest" : point.label.slice(5, 16)}
              </text>
            ))}
          </svg>
          <div className="flex h-7 shrink-0 flex-wrap items-center gap-3">
            {series.map((item) => (
              <span
                key={item.key}
                className="inline-flex items-center gap-1.5 text-[11px] text-slate-300"
              >
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                {item.label}
              </span>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

export function InfraShapeTab({ active, maskIps = false, onCopyToNote }: InfraShapeTabProps) {
  const [clusters, setClusters] = useState<ShapeCluster[]>([]);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<ShapeAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);
  const [isGapAnalyzing, setIsGapAnalyzing] = useState(false);
  const [gapAnalysisMessage, setGapAnalysisMessage] = useState<string | null>(null);
  const [capacity, setCapacity] = useState<ClusterShapeCapacity | null>(null);
  const [isLoadingCapacity, setIsLoadingCapacity] = useState(false);

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

  const loadCapacity = useCallback(async (clusterName: string) => {
    setIsLoadingCapacity(true);
    try {
      const response = await fetch(
        `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}/capacity`,
      );
      if (!response.ok) {
        throw new Error(await parseError(response, "용량 정보를 불러오지 못했습니다."));
      }
      const data = (await response.json()) as ClusterShapeCapacity;
      setCapacity(data);
    } catch {
      setCapacity(null);
    } finally {
      setIsLoadingCapacity(false);
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
      setCapacity(null);
      return;
    }
    void loadAnalysis(selectedName);
    void loadCapacity(selectedName);
  }, [active, selectedName, loadAnalysis, loadCapacity]);

  const summaryItems = useMemo(() => {
    if (!analysis) {
      return [];
    }
    if (analysis.infra_type === "vSphere") {
      return [
        { label: "등록 이름", value: analysis.cluster_name },
        { label: "표시 이름", value: (analysis.display_name ?? "").trim() || "-" },
        { label: "인프라 유형", value: analysis.infra_type },
        { label: "마지막 수집", value: analysis.last_update ?? "-" },
        { label: "클러스터 개수", value: String(analysis.summary.namespaces ?? 0) },
        { label: "호스트 개수", value: String(analysis.summary.nodes ?? 0) },
        { label: "VM 개수", value: String(analysis.summary.vms ?? 0) },
        { label: "데이터스토어 개수", value: String(analysis.summary.volumes ?? 0) },
      ];
    }
    const items = [
      { label: "클러스터 이름", value: analysis.cluster_name },
      { label: "표시 이름", value: (analysis.display_name ?? "").trim() || "-" },
      { label: "인프라 유형", value: analysis.infra_type || "k8s" },
      { label: "클러스터 버전", value: analysis.cluster_version ?? "-" },
      { label: "노드 개수", value: String(analysis.summary.nodes) },
      { label: "네임스페이스(프로젝트) 개수", value: String(analysis.summary.namespaces) },
      { label: "배포 개수", value: String(analysis.summary.deployments) },
      { label: "PVC 개수", value: String(analysis.summary.pvcs) },
    ];
    if (analysis.infra_type === "kubevirt") {
      items.push(
        { label: "VM 개수", value: String(analysis.summary.vms ?? 0) },
        { label: "볼륨 개수", value: String(analysis.summary.volumes ?? 0) },
      );
    }
    return items;
  }, [analysis]);

  const selectedInfraType = useMemo(() => {
    const fromList = clusters.find((item) => item.cluster_name === selectedName)?.infra_type;
    return analysis?.infra_type || fromList || "k8s";
  }, [analysis?.infra_type, clusters, selectedName]);

  const runGapAnalysis = useCallback(async () => {
    if (!selectedName) {
      return;
    }
    const infraType = selectedInfraType;
    const message =
      `${selectedName} is ${infraType}. ` +
      "Compare inventory rows across snapshot generations (latest and backups). " +
      "Report added, removed, and changed resources with count trends. " +
      "Do not focus on table or schema DDL differences unless they block the comparison.";
    setIsGapAnalyzing(true);
    setGapAnalysisMessage(null);
    try {
      const response = await fetch("/api/infra-gap-analysis/invoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          cluster_name: selectedName,
          infra_type: infraType,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "AI 갭분석 요청에 실패했습니다."));
      }
      const payload = (await response.json()) as { content?: string };
      const reportContent = (payload.content || "").trim();
      if (!reportContent) {
        throw new Error("갭분석 결과가 비어 있습니다.");
      }

      const reportDate = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Seoul",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date());
      const noteName =
        `[GAP분석 보고서][${reportDate}] ${selectedName}(${infraType}) 의 인프라 형상 보고`;

      if (onCopyToNote) {
        await onCopyToNote(reportContent, noteName);
        setGapAnalysisMessage(
          "갭분석이 완료되어 나의 노트에 저장했습니다. 상세정보 > 대화로그에서도 확인할 수 있습니다.",
        );
      } else {
        setGapAnalysisMessage(
          "갭분석이 완료되었습니다. 상세정보 > 대화로그에서 확인할 수 있습니다.",
        );
      }
    } catch (err) {
      setGapAnalysisMessage(err instanceof Error ? err.message : "AI 갭분석 요청에 실패했습니다.");
    } finally {
      setIsGapAnalyzing(false);
    }
  }, [selectedName, selectedInfraType, onCopyToNote]);

  return (
    <div className="flex min-h-0 flex-1 gap-3 p-3">
      <aside className="flex w-[178px] shrink-0 flex-col border-r border-slate-700/80 pr-3">
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
            const infraType = cluster.infra_type || "k8s";
            return (
              <button
                key={cluster.idx}
                type="button"
                onClick={() => setSelectedName(cluster.cluster_name)}
                className={`block w-full rounded-md border px-2.5 py-1.5 text-left text-[11px] font-medium transition-colors ${clusterButtonClass(isSelected)}`}
                title={
                  cluster.last_update
                    ? `${infraType} · last_update: ${cluster.last_update}`
                    : `${clusterListLabel(cluster)} (${infraType})`
                }
              >
                <span className="block truncate">{clusterListLabel(cluster)}</span>
                <span
                  className={`mt-0.5 block truncate text-[10px] font-normal ${
                    isSelected ? "text-sky-300/80" : "text-slate-500"
                  }`}
                >
                  {infraType}
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 gap-3">
        <div className="flex min-h-0 min-w-0 flex-[3] flex-col gap-3">
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

          <div className="grid shrink-0 grid-cols-3 gap-3">
            <ClusterCapacityPanel capacity={capacity} isLoading={isLoadingCapacity} />
            <NodeCapacityPanel capacity={capacity} isLoading={isLoadingCapacity} />
            <StorageCapacityPanel capacity={capacity} isLoading={isLoadingCapacity} />
          </div>

          <section className="flex min-h-0 flex-1 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
            <div className="mb-1 flex shrink-0 items-center justify-between gap-2">
              <h3 className="text-xs font-semibold text-slate-300">형상 추이</h3>
              <button
                type="button"
                disabled={!selectedName || isGapAnalyzing}
                onClick={() => void runGapAnalysis()}
                className="rounded border border-sky-700 bg-sky-950/50 px-2 py-0.5 text-[11px] font-medium text-sky-200 hover:bg-sky-900/60 disabled:cursor-not-allowed disabled:opacity-40"
                title={
                  selectedName
                    ? `${selectedName} (${selectedInfraType}) AI 갭분석`
                    : "클러스터를 선택해 주세요"
                }
              >
                {isGapAnalyzing ? "분석 중..." : "AI갭분석"}
              </button>
            </div>
            <p className="mb-2 text-[11px] text-slate-500">
              최신 테이블과 백업(최대 4세대) 기준 개수 변화
            </p>
            {gapAnalysisMessage ? (
              <p
                className={`mb-2 shrink-0 rounded-md border px-2 py-1 text-[11px] ${
                  gapAnalysisMessage.startsWith("갭분석 실패")
                    ? "border-rose-800 bg-rose-950/40 text-rose-200"
                    : "border-emerald-800 bg-emerald-950/30 text-emerald-200"
                }`}
              >
                {gapAnalysisMessage}
              </p>
            ) : null}
            <div className="min-h-0 flex-1 overflow-hidden">
              {analysis ? (
                <ShapeTrendChart
                  history={analysis.history}
                  infraType={analysis.infra_type || "k8s"}
                />
              ) : (
                <p className="text-xs text-slate-500">추이 차트를 표시할 클러스터가 없습니다.</p>
              )}
            </div>
          </section>
        </div>

        <div className="flex min-h-0 min-w-0 flex-[2] flex-col">
          {selectedInfraType === "vSphere" && selectedName ? (
            <VsphereShapeDetailPanel active={active} clusterName={selectedName} />
          ) : (
            <ShapeDetailPanel
              active={active}
              clusterName={selectedName}
              infraType={selectedInfraType}
              maskIps={maskIps}
            />
          )}
        </div>
      </div>
    </div>
  );
}
