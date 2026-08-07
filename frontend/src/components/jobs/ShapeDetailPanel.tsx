import { useCallback, useEffect, useMemo, useState } from "react";

type DetailCategory = "namespaces" | "nodes" | "vms";

interface NamespaceListItem {
  idx: number;
  namespace: string;
  okd_display_name: string | null;
}

interface NodeListItem {
  idx: number;
  node_name: string;
  node_cpu: number | null;
  node_mem: number | null;
  node_os: string | null;
  node_k8s_ver: string | null;
}

interface VmListItem {
  idx: number;
  name: string;
  namespace: string | null;
  printable_status: string | null;
  ready: boolean | null;
  node_name: string | null;
}

interface NamespaceDetail {
  namespace: Record<string, unknown>;
  deployments: Record<string, unknown>[];
  pvcs: Record<string, unknown>[];
}

interface NodeDetail {
  node: Record<string, unknown>;
}

interface VmDetail {
  vm: Record<string, unknown>;
  volumes: Record<string, unknown>[];
}

interface ShapeDetailPanelProps {
  clusterName: string | null;
  infraType: string;
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

function categoryButtonClass(isSelected: boolean): string {
  if (isSelected) {
    return "border-b border-sky-400 text-sky-200";
  }
  return "border-b border-transparent text-slate-400 hover:text-slate-200";
}

function itemButtonClass(isSelected: boolean): string {
  if (isSelected) {
    return "bg-slate-800 text-sky-100";
  }
  return "text-slate-400 hover:bg-slate-800 hover:text-slate-200";
}

function KeyValueGrid({
  data,
  keys,
}: {
  data: Record<string, unknown>;
  keys: { key: string; label: string }[];
}) {
  return (
    <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5">
      {keys.map((item) => (
        <div key={item.key} className="min-w-0">
          <dt className="text-[10px] text-slate-500">{item.label}</dt>
          <dd className="truncate font-mono text-[11px] text-slate-100" title={displayValue(data[item.key])}>
            {displayValue(data[item.key])}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function SimpleTable({
  columns,
  rows,
  emptyLabel,
}: {
  columns: { key: string; label: string }[];
  rows: Record<string, unknown>[];
  emptyLabel: string;
}) {
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">{emptyLabel}</p>;
  }
  return (
    <div className="overflow-auto">
      <table className="w-full min-w-[280px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-700 text-slate-500">
            {columns.map((column) => (
              <th key={column.key} className="px-1.5 py-1 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-slate-800/80 text-slate-200">
              {columns.map((column) => (
                <td key={column.key} className="max-w-[120px] truncate px-1.5 py-1 font-mono" title={displayValue(row[column.key])}>
                  {displayValue(row[column.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const NAMESPACE_KEYS = [
  { key: "namespace", label: "namespace" },
  { key: "okd_display_name", label: "display name" },
  { key: "resource_quota_cpu_limit", label: "CPU quota" },
  { key: "resource_quota_mem_limit", label: "Mem quota (Gi)" },
  { key: "resource_quota_pod_limit", label: "Pod quota" },
  { key: "okd_egressip1", label: "egressIP1" },
  { key: "okd_egressip2", label: "egressIP2" },
  { key: "using_egressip", label: "using egressIP" },
  { key: "egressip_assigned_node", label: "egressIP node" },
];

const NODE_KEYS = [
  { key: "node_name", label: "node" },
  { key: "node_cpu", label: "CPU" },
  { key: "node_mem", label: "Mem (Gi)" },
  { key: "node_os", label: "OS" },
  { key: "node_k8s_ver", label: "K8s ver" },
];

const VM_KEYS = [
  { key: "name", label: "name" },
  { key: "namespace", label: "namespace" },
  { key: "run_strategy", label: "run strategy" },
  { key: "printable_status", label: "status" },
  { key: "ready", label: "ready" },
  { key: "vmi_phase", label: "VMI phase" },
  { key: "node_name", label: "node" },
  { key: "ip_address", label: "IP" },
  { key: "cpu_cores", label: "CPU cores" },
  { key: "memory_gi", label: "Mem (Gi)" },
  { key: "disk_count", label: "disks" },
  { key: "network_count", label: "networks" },
  { key: "os_info", label: "OS" },
  { key: "created_at", label: "created" },
];

const DEP_COLUMNS = [
  { key: "name", label: "name" },
  { key: "type", label: "type" },
  { key: "replicas", label: "replicas" },
  { key: "resource_cpu_request", label: "cpu req" },
  { key: "resource_mem_request", label: "mem req" },
  { key: "containers_cnt", label: "containers" },
];

const PVC_COLUMNS = [
  { key: "name", label: "name" },
  { key: "storage_class", label: "storage class" },
  { key: "capacity", label: "capacity" },
  { key: "used", label: "used" },
  { key: "access_mode", label: "access" },
];

const VOLUME_COLUMNS = [
  { key: "volume_name", label: "volume" },
  { key: "pvc_name", label: "PVC" },
  { key: "capacity_gi", label: "capacity (Gi)" },
];

export function ShapeDetailPanel({
  clusterName,
  infraType,
  active,
}: ShapeDetailPanelProps) {
  const [category, setCategory] = useState<DetailCategory | null>(null);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [namespaces, setNamespaces] = useState<NamespaceListItem[]>([]);
  const [nodes, setNodes] = useState<NodeListItem[]>([]);
  const [vms, setVms] = useState<VmListItem[]>([]);
  const [namespaceDetail, setNamespaceDetail] = useState<NamespaceDetail | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeDetail | null>(null);
  const [vmDetail, setVmDetail] = useState<VmDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const categories = useMemo(() => {
    const base: { id: DetailCategory; label: string }[] = [
      { id: "namespaces", label: "네임스페이스" },
      { id: "nodes", label: "노드" },
    ];
    if (infraType === "kubevirt") {
      base.push({ id: "vms", label: "VM" });
    }
    return base;
  }, [infraType]);

  useEffect(() => {
    setCategory(null);
    setSelectedIdx(null);
    setNamespaces([]);
    setNodes([]);
    setVms([]);
    setNamespaceDetail(null);
    setNodeDetail(null);
    setVmDetail(null);
    setError(null);
  }, [clusterName, infraType]);

  useEffect(() => {
    if (category === "vms" && infraType !== "kubevirt") {
      setCategory(null);
      setSelectedIdx(null);
    }
  }, [category, infraType]);

  const clearSelection = useCallback(() => {
    setSelectedIdx(null);
    setNamespaceDetail(null);
    setNodeDetail(null);
    setVmDetail(null);
    setError(null);
  }, []);

  const selectCategory = useCallback(
    (next: DetailCategory) => {
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
        const response = await fetch(
          `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}/${category}`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          throw new Error(await parseError(response, "목록을 불러오지 못했습니다."));
        }
        const data = await response.json();
        if (controller.signal.aborted) {
          return;
        }
        if (category === "namespaces") {
          setNamespaces(data as NamespaceListItem[]);
          setNodes([]);
          setVms([]);
        } else if (category === "nodes") {
          setNodes(data as NodeListItem[]);
          setNamespaces([]);
          setVms([]);
        } else {
          setVms(data as VmListItem[]);
          setNamespaces([]);
          setNodes([]);
        }
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        setNamespaces([]);
        setNodes([]);
        setVms([]);
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
    const requestCategory = category;
    const requestIdx = selectedIdx;
    setIsLoadingDetail(true);
    setError(null);
    void (async () => {
      try {
        const response = await fetch(
          `/api/k8s-infra/shape/clusters/${encodeURIComponent(clusterName)}/${requestCategory}/${requestIdx}`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          throw new Error(await parseError(response, "상세 정보를 불러오지 못했습니다."));
        }
        const data = await response.json();
        if (controller.signal.aborted) {
          return;
        }
        if (requestCategory === "namespaces") {
          setNamespaceDetail(data as NamespaceDetail);
          setNodeDetail(null);
          setVmDetail(null);
        } else if (requestCategory === "nodes") {
          setNodeDetail(data as NodeDetail);
          setNamespaceDetail(null);
          setVmDetail(null);
        } else {
          setVmDetail(data as VmDetail);
          setNamespaceDetail(null);
          setNodeDetail(null);
        }
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        setNamespaceDetail(null);
        setNodeDetail(null);
        setVmDetail(null);
        setError(err instanceof Error ? err.message : "상세 정보를 불러오지 못했습니다.");
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingDetail(false);
        }
      }
    })();
    return () => controller.abort();
  }, [active, clusterName, category, selectedIdx]);

  const listItems = useMemo(() => {
    if (category === "namespaces") {
      return namespaces.map((item) => ({
        idx: item.idx,
        label: item.okd_display_name
          ? `${item.namespace} (${item.okd_display_name})`
          : item.namespace,
      }));
    }
    if (category === "nodes") {
      return nodes.map((item) => ({
        idx: item.idx,
        label: item.node_name,
      }));
    }
    if (category === "vms") {
      return vms.map((item) => ({
        idx: item.idx,
        label: item.namespace ? `${item.namespace}/${item.name}` : item.name,
      }));
    }
    return [];
  }, [category, namespaces, nodes, vms]);

  if (!clusterName) {
    return (
      <section className="flex h-full min-h-0 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
        <h3 className="mb-2 text-xs font-semibold text-slate-300">상세정보</h3>
        <p className="text-xs text-slate-500">클러스터를 선택해 주세요.</p>
      </section>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
      <h3 className="mb-2 shrink-0 text-xs font-semibold text-slate-300">상세정보</h3>

      <div className="mb-2 flex shrink-0 flex-wrap gap-3">
        {categories.map((item) => (
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

      {error ? (
        <div className="mb-2 shrink-0 rounded-md border border-rose-800 bg-rose-950/40 px-2 py-1.5 text-[11px] text-rose-200">
          {error}
        </div>
      ) : null}

      {!category ? (
        <p className="text-xs text-slate-500">네임스페이스 / 노드{infraType === "kubevirt" ? " / VM" : ""}을 선택하세요.</p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="max-h-[28%] shrink-0 overflow-y-auto overscroll-contain border-b border-slate-800 pb-2">
            {isLoadingList ? (
              <p className="text-[11px] text-slate-500">목록 불러오는 중...</p>
            ) : listItems.length === 0 ? (
              <p className="text-[11px] text-slate-500">항목이 없습니다.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {listItems.map((item) => (
                  <button
                    key={item.idx}
                    type="button"
                    onClick={() => setSelectedIdx(item.idx)}
                    className={`rounded px-1.5 py-0.5 text-left text-[11px] transition-colors ${itemButtonClass(selectedIdx === item.idx)}`}
                    title={item.label}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {category === "namespaces" && selectedIdx != null ? (
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <div className="mb-2 shrink-0 border-b border-slate-800 pb-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  네임스페이스 상세
                </p>
                {isLoadingDetail && !namespaceDetail ? (
                  <p className="text-[11px] text-slate-500">불러오는 중...</p>
                ) : namespaceDetail ? (
                  <KeyValueGrid data={namespaceDetail.namespace} keys={NAMESPACE_KEYS} />
                ) : (
                  <p className="text-[11px] text-slate-500">상세 정보가 없습니다.</p>
                )}
              </div>
              <div className="space-y-3">
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Deployments
                  </p>
                  <SimpleTable
                    columns={DEP_COLUMNS}
                    rows={namespaceDetail?.deployments ?? []}
                    emptyLabel="Deployment가 없습니다."
                  />
                </div>
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    PVCs
                  </p>
                  <SimpleTable
                    columns={PVC_COLUMNS}
                    rows={namespaceDetail?.pvcs ?? []}
                    emptyLabel="PVC가 없습니다."
                  />
                </div>
              </div>
            </div>
          ) : null}

          {category === "nodes" && selectedIdx != null ? (
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                노드 상세
              </p>
              {isLoadingDetail && !nodeDetail ? (
                <p className="text-[11px] text-slate-500">불러오는 중...</p>
              ) : nodeDetail ? (
                <KeyValueGrid data={nodeDetail.node} keys={NODE_KEYS} />
              ) : (
                <p className="text-[11px] text-slate-500">상세 정보가 없습니다.</p>
              )}
            </div>
          ) : null}

          {category === "vms" && selectedIdx != null ? (
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <div className="mb-2 border-b border-slate-800 pb-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  VM 상세
                </p>
                {isLoadingDetail && !vmDetail ? (
                  <p className="text-[11px] text-slate-500">불러오는 중...</p>
                ) : vmDetail ? (
                  <KeyValueGrid data={vmDetail.vm} keys={VM_KEYS} />
                ) : (
                  <p className="text-[11px] text-slate-500">상세 정보가 없습니다.</p>
                )}
              </div>
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Volumes
                </p>
                <SimpleTable
                  columns={VOLUME_COLUMNS}
                  rows={vmDetail?.volumes ?? []}
                  emptyLabel="연결된 볼륨이 없습니다."
                />
              </div>
            </div>
          ) : null}

          {category && selectedIdx == null && !isLoadingList ? (
            <p className="text-[11px] text-slate-500">목록에서 항목을 선택하세요.</p>
          ) : null}
        </div>
      )}
    </section>
  );
}
