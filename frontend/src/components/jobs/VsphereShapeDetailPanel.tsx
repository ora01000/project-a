import { useCallback, useEffect, useMemo, useState } from "react";

interface VsphereClusterListItem {
  idx: number;
  cluster_id: string;
  cluster_name: string | null;
  ha_enabled: boolean | null;
  drs_enabled: boolean | null;
}

interface VsphereHostListItem {
  idx: number;
  host_id: string;
  host_name: string | null;
  connection_state: string | null;
  power_state: string | null;
  cluster_id: string | null;
  cpu_count: number | null;
  memory_mib: number | null;
}

interface VsphereClusterDetail {
  cluster: Record<string, unknown>;
  hosts: Record<string, unknown>[];
}

interface VsphereHostDetail {
  host: Record<string, unknown>;
  vms: Record<string, unknown>[];
}

type VsphereCategory = "clusters" | "nodes";

interface VsphereShapeDetailPanelProps {
  clusterName: string;
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

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function asEnabledFlag(value: unknown): boolean | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (value === 1 || value === "1" || value === "true" || value === "TRUE") {
    return true;
  }
  if (value === 0 || value === "0" || value === "false" || value === "FALSE") {
    return false;
  }
  return null;
}

/** HA / DRS enabled flag → emoji (title keeps original). */
function formatHaDrsEmoji(value: unknown): { text: string; title: string } {
  const flag = asEnabledFlag(value);
  if (flag === true) {
    return { text: "✅", title: "enabled" };
  }
  if (flag === false) {
    return { text: "❌", title: "disabled" };
  }
  return { text: "➖", title: displayValue(value) };
}

/** Host/VM connection_state → emoji. */
function formatConnectionEmoji(value: unknown): { text: string; title: string } {
  const raw = displayValue(value);
  const key = raw.toUpperCase();
  if (raw === "-") {
    return { text: "➖", title: "-" };
  }
  if (key === "CONNECTED") {
    return { text: "🟢", title: raw };
  }
  if (key === "DISCONNECTED") {
    return { text: "🔴", title: raw };
  }
  if (key === "NOT_RESPONDING") {
    return { text: "🟠", title: raw };
  }
  return { text: "⚪", title: raw };
}

/** Host/VM power_state → emoji. */
function formatPowerEmoji(value: unknown): { text: string; title: string } {
  const raw = displayValue(value);
  const key = raw.toUpperCase();
  if (raw === "-") {
    return { text: "➖", title: "-" };
  }
  if (key === "POWERED_ON") {
    return { text: "⚡", title: raw };
  }
  if (key === "POWERED_OFF") {
    return { text: "⏹", title: raw };
  }
  if (key === "STANDBY" || key === "SUSPENDED") {
    return { text: "💤", title: raw };
  }
  return { text: "⚪", title: raw };
}

function EmojiCell({ text, title }: { text: string; title: string }) {
  return (
    <span className="inline-block text-sm leading-none" title={title} aria-label={title}>
      {text}
    </span>
  );
}

function categoryButtonClass(isSelected: boolean): string {
  if (isSelected) {
    return "border-b border-sky-400 text-sky-200";
  }
  return "border-b border-transparent text-slate-400 hover:text-slate-200";
}

function tableRowClass(isSelected: boolean): string {
  if (isSelected) {
    return "bg-sky-950/60 text-sky-100";
  }
  return "text-slate-200 hover:bg-sky-950/40";
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/** memory_mib → GiB display (1 GiB = 1024 MiB). */
function formatMemoryGib(value: unknown): string {
  const mib = toNumber(value);
  if (mib === null) {
    return "-";
  }
  const gib = mib / 1024;
  if (Number.isInteger(gib)) {
    return String(gib);
  }
  return gib.toFixed(2).replace(/\.?0+$/, "");
}

function ClusterTable({
  rows,
  selectedIdx,
  onSelect,
}: {
  rows: VsphereClusterListItem[];
  selectedIdx: number | null;
  onSelect: (idx: number) => void;
}) {
  const summary = useMemo(() => {
    if (rows.length === 0) {
      return null;
    }
    return {
      cluster_id: `Σ summary (${rows.length})`,
      cluster_name: "",
      ha_enabled: null,
      drs_enabled: null,
    };
  }, [rows]);

  const columns = [
    { key: "cluster_id", label: "클러스터ID" },
    { key: "cluster_name", label: "클러스터명" },
    { key: "ha_enabled", label: "이중화" },
    { key: "drs_enabled", label: "DRS" },
  ] as const;

  return (
    <table className="min-w-full border-collapse text-left text-[11px]">
      <thead className="sticky top-0 bg-slate-900">
        <tr className="text-slate-400">
          {columns.map((column) => (
            <th key={column.key} className="whitespace-nowrap px-2 py-1 font-medium">
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.idx}
            className={`cursor-pointer border-t border-slate-800 ${tableRowClass(selectedIdx === row.idx)}`}
            onClick={() => onSelect(row.idx)}
          >
            <td className="whitespace-nowrap px-2 py-1 font-mono">{displayValue(row.cluster_id)}</td>
            <td className="whitespace-nowrap px-2 py-1">{displayValue(row.cluster_name)}</td>
            <td className="whitespace-nowrap px-2 py-1 text-center">
              <EmojiCell {...formatHaDrsEmoji(row.ha_enabled)} />
            </td>
            <td className="whitespace-nowrap px-2 py-1 text-center">
              <EmojiCell {...formatHaDrsEmoji(row.drs_enabled)} />
            </td>
          </tr>
        ))}
        {summary ? (
          <tr className="border-t border-slate-700 bg-slate-900/80 text-slate-300">
            <td className="whitespace-nowrap px-2 py-1 font-mono">{summary.cluster_id}</td>
            <td className="whitespace-nowrap px-2 py-1">{summary.cluster_name}</td>
            <td className="whitespace-nowrap px-2 py-1">-</td>
            <td className="whitespace-nowrap px-2 py-1">-</td>
          </tr>
        ) : null}
      </tbody>
    </table>
  );
}

function HostTable({
  rows,
  selectedIdx,
  onSelect,
  selectable,
  showClusterId = true,
}: {
  rows: Record<string, unknown>[] | VsphereHostListItem[];
  selectedIdx?: number | null;
  onSelect?: (idx: number) => void;
  selectable?: boolean;
  /** false: 클러스터 탭 소속 호스트 — cluster_id 컬럼 숨김 */
  showClusterId?: boolean;
}) {
  const normalized = rows as Array<Record<string, unknown>>;
    const summary = useMemo(() => {
    if (normalized.length === 0) {
      return null;
    }
    let cpuTotal = 0;
    let memTotal = 0;
    let hasCpu = false;
    let hasMem = false;
    for (const row of normalized) {
      const cpu = toNumber(row.cpu_count);
      if (cpu !== null) {
        cpuTotal += cpu;
        hasCpu = true;
      }
      const mem = toNumber(row.memory_mib);
      if (mem !== null) {
        memTotal += mem;
        hasMem = true;
      }
    }
    return {
      host_id: `Σ summary (${normalized.length})`,
      host_name: "",
      connection_state: "",
      power_state: "",
      cluster_id: "",
      cpu_count: hasCpu ? cpuTotal : null,
      memory_mib: hasMem ? memTotal : null,
    };
  }, [normalized]);

  const columns = [
    { key: "host_id", label: "호스트ID" },
    { key: "host_name", label: "ESXi호스트명" },
    { key: "cpu_count", label: "CPU(코어)" },
    { key: "memory_mib", label: "MEM(GiB)" },
    { key: "connection_state", label: "연결상태" },
    { key: "power_state", label: "전원" },
    ...(showClusterId ? [{ key: "cluster_id", label: "소속클러스터" }] : []),
  ];

  return (
    <table className="min-w-full border-collapse text-left text-[11px]">
      <thead className="sticky top-0 bg-slate-900">
        <tr className="text-slate-400">
          {columns.map((column) => (
            <th key={column.key} className="whitespace-nowrap px-2 py-1 font-medium">
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {normalized.map((row, index) => {
          const idx = typeof row.idx === "number" ? row.idx : index;
          const isSelected = selectable && selectedIdx === idx;
          return (
            <tr
              key={idx}
              className={`border-t border-slate-800 ${
                selectable ? `cursor-pointer ${tableRowClass(Boolean(isSelected))}` : "text-slate-200"
              }`}
              onClick={() => {
                if (selectable && onSelect && typeof row.idx === "number") {
                  onSelect(row.idx);
                }
              }}
            >
              {columns.map((column) => {
                const raw = row[column.key];
                if (column.key === "connection_state") {
                  return (
                    <td key={column.key} className="whitespace-nowrap px-2 py-1 text-center">
                      <EmojiCell {...formatConnectionEmoji(raw)} />
                    </td>
                  );
                }
                if (column.key === "power_state") {
                  return (
                    <td key={column.key} className="whitespace-nowrap px-2 py-1 text-center">
                      <EmojiCell {...formatPowerEmoji(raw)} />
                    </td>
                  );
                }
                if (column.key === "memory_mib") {
                  return (
                    <td key={column.key} className="whitespace-nowrap px-2 py-1 font-mono">
                      {formatMemoryGib(raw)}
                    </td>
                  );
                }
                return (
                  <td key={column.key} className="whitespace-nowrap px-2 py-1 font-mono">
                    {displayValue(raw)}
                  </td>
                );
              })}
            </tr>
          );
        })}
        {summary ? (
          <tr className="border-t border-slate-700 bg-slate-900/80 text-slate-300">
            {columns.map((column) => (
              <td key={column.key} className="whitespace-nowrap px-2 py-1 font-mono">
                {column.key === "memory_mib"
                  ? formatMemoryGib(summary.memory_mib)
                  : displayValue(summary[column.key as keyof typeof summary])}
              </td>
            ))}
          </tr>
        ) : null}
      </tbody>
    </table>
  );
}

function isVsphereVmPoweredOff(row: Record<string, unknown>): boolean {
  return displayValue(row.power_state).toUpperCase() === "POWERED_OFF";
}

function buildVsphereVmSummary(
  rows: Record<string, unknown>[],
  label: string,
): {
  vm_id: string;
  vm_name: string;
  power_state: string;
  cpu_count: number | null;
  memory_mib: number | null;
} {
  let cpuTotal = 0;
  let memTotal = 0;
  let hasCpu = false;
  let hasMem = false;
  for (const row of rows) {
    const cpu = toNumber(row.cpu_count);
    if (cpu !== null) {
      cpuTotal += cpu;
      hasCpu = true;
    }
    const mem = toNumber(row.memory_mib);
    if (mem !== null) {
      memTotal += mem;
      hasMem = true;
    }
  }
  return {
    vm_id: `${label} (${rows.length})`,
    vm_name: "",
    power_state: "",
    cpu_count: hasCpu ? cpuTotal : null,
    memory_mib: hasMem ? memTotal : null,
  };
}

function VmTable({ rows }: { rows: Record<string, unknown>[] }) {
  const summaries = useMemo(() => {
    if (rows.length === 0) {
      return null;
    }
    const poweredOn = rows.filter((row) => !isVsphereVmPoweredOff(row));
    return [
      buildVsphereVmSummary(rows, "Σ summary"),
      buildVsphereVmSummary(poweredOn, "Σ 전원ON"),
    ];
  }, [rows]);

  const columns = [
    { key: "vm_id", label: "VMID" },
    { key: "vm_name", label: "VM명" },
    { key: "power_state", label: "전원" },
    { key: "cpu_count", label: "CPU" },
    { key: "memory_mib", label: "MEM(GB)" },
  ];

  return (
    <table className="min-w-full border-collapse text-left text-[11px]">
      <thead className="sticky top-0 bg-slate-900">
        <tr className="text-slate-400">
          {columns.map((column) => (
            <th key={column.key} className="whitespace-nowrap px-2 py-1 font-medium">
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={typeof row.idx === "number" ? row.idx : index} className="border-t border-slate-800 text-slate-200">
            {columns.map((column) => {
              if (column.key === "power_state") {
                return (
                  <td key={column.key} className="whitespace-nowrap px-2 py-1 text-center">
                    <EmojiCell {...formatPowerEmoji(row[column.key])} />
                  </td>
                );
              }
              if (column.key === "memory_mib") {
                return (
                  <td key={column.key} className="whitespace-nowrap px-2 py-1 font-mono">
                    {formatMemoryGib(row[column.key])}
                  </td>
                );
              }
              return (
                <td key={column.key} className="whitespace-nowrap px-2 py-1 font-mono">
                  {displayValue(row[column.key])}
                </td>
              );
            })}
          </tr>
        ))}
        {summaries?.map((summary, index) => (
          <tr
            key={`summary-${index}`}
            className="border-t border-slate-700 bg-slate-900/80 text-slate-300"
          >
            {columns.map((column) => {
              if (column.key === "power_state") {
                return (
                  <td key={column.key} className="whitespace-nowrap px-2 py-1 text-center">
                    -
                  </td>
                );
              }
              if (column.key === "memory_mib") {
                return (
                  <td key={column.key} className="whitespace-nowrap px-2 py-1 font-mono">
                    {formatMemoryGib(summary.memory_mib)}
                  </td>
                );
              }
              return (
                <td key={column.key} className="whitespace-nowrap px-2 py-1 font-mono">
                  {displayValue(summary[column.key as keyof typeof summary])}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function VsphereShapeDetailPanel({ clusterName, active }: VsphereShapeDetailPanelProps) {
  const [category, setCategory] = useState<VsphereCategory | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [clusters, setClusters] = useState<VsphereClusterListItem[]>([]);
  const [hosts, setHosts] = useState<VsphereHostListItem[]>([]);
  const [clusterDetail, setClusterDetail] = useState<VsphereClusterDetail | null>(null);
  const [hostDetail, setHostDetail] = useState<VsphereHostDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  useEffect(() => {
    setCategory(null);
    setSelectedIdx(null);
    setClusters([]);
    setHosts([]);
    setClusterDetail(null);
    setHostDetail(null);
    setError(null);
  }, [clusterName]);

  const clearSelection = useCallback(() => {
    setSelectedIdx(null);
    setClusterDetail(null);
    setHostDetail(null);
    setError(null);
  }, []);

  const selectCategory = useCallback(
    (next: VsphereCategory) => {
      setCategory(next);
      clearSelection();
    },
    [clearSelection],
  );

  useEffect(() => {
    if (!active || !clusterName || !category) {
      return;
    }
    const controller = new AbortController();
    setIsLoadingList(true);
    setError(null);
    void (async () => {
      try {
        const path =
          category === "clusters"
            ? `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}/vsphere-clusters`
            : `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}/vsphere-hosts`;
        const response = await fetch(path, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(await parseError(response, "목록을 불러오지 못했습니다."));
        }
        const data = await response.json();
        if (controller.signal.aborted) {
          return;
        }
        if (category === "clusters") {
          setClusters(data as VsphereClusterListItem[]);
          setHosts([]);
        } else {
          setHosts(data as VsphereHostListItem[]);
          setClusters([]);
        }
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        setClusters([]);
        setHosts([]);
        setError(err instanceof Error ? err.message : "목록을 불러오지 못했습니다.");
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingList(false);
        }
      }
    })();
    return () => controller.abort();
  }, [active, clusterName, category]);

  useEffect(() => {
    if (!active || !clusterName || !category || selectedIdx == null) {
      setIsLoadingDetail(false);
      return;
    }
    const controller = new AbortController();
    setIsLoadingDetail(true);
    setError(null);
    void (async () => {
      try {
        const path =
          category === "clusters"
            ? `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}/vsphere-clusters/${selectedIdx}`
            : `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}/vsphere-hosts/${selectedIdx}`;
        const response = await fetch(path, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(await parseError(response, "상세 정보를 불러오지 못했습니다."));
        }
        const data = await response.json();
        if (controller.signal.aborted) {
          return;
        }
        if (category === "clusters") {
          setClusterDetail(data as VsphereClusterDetail);
          setHostDetail(null);
        } else {
          setHostDetail(data as VsphereHostDetail);
          setClusterDetail(null);
        }
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        setClusterDetail(null);
        setHostDetail(null);
        setError(err instanceof Error ? err.message : "상세 정보를 불러오지 못했습니다.");
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingDetail(false);
        }
      }
    })();
    return () => controller.abort();
  }, [active, clusterName, category, selectedIdx]);

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
      <h3 className="mb-2 shrink-0 text-xs font-semibold text-slate-300">상세정보</h3>

      <div className="mb-2 flex shrink-0 flex-wrap gap-3">
        {(
          [
            { id: "clusters" as const, label: "클러스터" },
            { id: "nodes" as const, label: "ESXi호스트" },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => selectCategory(item.id)}
            className={`pb-0.5 text-[12px] font-medium transition-colors ${categoryButtonClass(category === item.id)}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <p className="mb-2 text-xs text-rose-300">{error}</p> : null}

      {!category ? (
        <p className="text-xs text-slate-500">클러스터 / ESXi호스트를 선택하세요.</p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="max-h-[45%] min-h-0 overflow-auto rounded border border-slate-800">
            {isLoadingList ? (
              <p className="p-2 text-xs text-slate-500">불러오는 중...</p>
            ) : category === "clusters" ? (
              clusters.length === 0 ? (
                <p className="p-2 text-xs text-slate-500">클러스터가 없습니다.</p>
              ) : (
                <ClusterTable
                  rows={clusters}
                  selectedIdx={selectedIdx}
                  onSelect={setSelectedIdx}
                />
              )
            ) : hosts.length === 0 ? (
              <p className="p-2 text-xs text-slate-500">호스트가 없습니다.</p>
            ) : (
              <HostTable
                rows={hosts}
                selectedIdx={selectedIdx}
                onSelect={setSelectedIdx}
                selectable
                showClusterId
              />
            )}
          </div>

          {selectedIdx != null ? (
            <div className="min-h-0 flex-1 overflow-auto rounded border border-slate-800">
              {isLoadingDetail ? (
                <p className="p-2 text-xs text-slate-500">상세 불러오는 중...</p>
              ) : category === "clusters" ? (
                clusterDetail ? (
                  <div className="p-2">
                    <p className="mb-1 text-[11px] text-slate-400">
                      소속 호스트 ({clusterDetail.hosts.length})
                    </p>
                    {clusterDetail.hosts.length === 0 ? (
                      <p className="text-xs text-slate-500">소속 호스트가 없습니다.</p>
                    ) : (
                      <HostTable rows={clusterDetail.hosts} showClusterId={false} />
                    )}
                  </div>
                ) : (
                  <p className="p-2 text-xs text-slate-500">상세 정보가 없습니다.</p>
                )
              ) : hostDetail ? (
                <div className="p-2">
                  <p className="mb-1 text-[11px] text-slate-400">
                    {displayValue(hostDetail.host.host_name ?? hostDetail.host.host_id)} 에 배치된 VM (
                    {hostDetail.vms.length})
                  </p>
                  {hostDetail.vms.length === 0 ? (
                    <p className="text-xs text-slate-500">VM이 없습니다.</p>
                  ) : (
                    <VmTable rows={hostDetail.vms} />
                  )}
                </div>
              ) : (
                <p className="p-2 text-xs text-slate-500">상세 정보가 없습니다.</p>
              )}
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
