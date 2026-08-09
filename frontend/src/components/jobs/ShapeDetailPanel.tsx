import { useCallback, useEffect, useMemo, useState } from "react";

type DetailCategory = "namespaces" | "nodes" | "vms";

interface NamespaceListItem {
  idx: number;
  namespace: string;
  okd_display_name: string | null;
  resource_quota_cpu_limit: number | null;
  resource_quota_mem_limit: number | null;
  resource_quota_pod_limit: number | null;
  okd_egressip1: string | null;
  okd_egressip2: string | null;
  using_egressip: string | null;
  egressip_assigned_node: string | null;
}

interface NodeListItem {
  idx: number;
  node_name: string;
  node_cpu: number | null;
  node_mem: number | null;
  node_os: string | null;
  node_k8s_ver: string | null;
  node_role: string | null;
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
  pods: Record<string, unknown>[];
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

function tableRowClass(isSelected: boolean): string {
  if (isSelected) {
    return "bg-sky-950/60 text-sky-100";
  }
  return "text-slate-200 hover:bg-sky-950/40";
}

function buildNamespaceSummary(rows: NamespaceListItem[]): Record<string, unknown> | null {
  if (rows.length === 0) {
    return null;
  }
  let cpuTotal = 0;
  let memTotal = 0;
  let podTotal = 0;
  let hasCpu = false;
  let hasMem = false;
  let hasPod = false;

  for (const row of rows) {
    const cpu = toNumber(row.resource_quota_cpu_limit);
    if (cpu !== null) {
      cpuTotal += cpu;
      hasCpu = true;
    }
    const mem = toNumber(row.resource_quota_mem_limit);
    if (mem !== null) {
      memTotal += mem;
      hasMem = true;
    }
    const pods = toNumber(row.resource_quota_pod_limit);
    if (pods !== null) {
      podTotal += pods;
      hasPod = true;
    }
  }

  return {
    namespace: `Σ summary (${rows.length})`,
    okd_display_name: "",
    resource_quota_cpu_limit: hasCpu ? cpuTotal : null,
    resource_quota_mem_limit: hasMem ? memTotal : null,
    resource_quota_pod_limit: hasPod ? podTotal : null,
    okd_egressip1: "",
    okd_egressip2: "",
    egressip_assigned_node: "",
  };
}

function isActiveEgressIp(ip: unknown, usingEgressIp: unknown): boolean {
  const ipText = typeof ip === "string" ? ip.trim() : "";
  const usingText = typeof usingEgressIp === "string" ? usingEgressIp.trim() : "";
  return Boolean(ipText && usingText && ipText === usingText);
}

function EgressIpCell({
  ip,
  usingEgressIp,
}: {
  ip: unknown;
  usingEgressIp: unknown;
}) {
  const text = displayValue(ip);
  if (text === "-") {
    return <span>-</span>;
  }
  if (isActiveEgressIp(ip, usingEgressIp)) {
    return (
      <span
        className="inline-flex max-w-full truncate rounded border border-emerald-700/60 bg-emerald-950/50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-100"
        title={`using egressIP: ${text}`}
      >
        {text}
      </span>
    );
  }
  return <span className="truncate">{text}</span>;
}

function SelectableNamespaceTable({
  rows,
  selectedIdx,
  onSelect,
}: {
  rows: NamespaceListItem[];
  selectedIdx: number | null;
  onSelect: (idx: number) => void;
}) {
  const summary = useMemo(() => buildNamespaceSummary(rows), [rows]);
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">항목이 없습니다.</p>;
  }

  const renderCell = (row: Record<string, unknown>, key: string) => {
    if (
      key === "resource_quota_cpu_limit" ||
      key === "resource_quota_mem_limit" ||
      key === "resource_quota_pod_limit"
    ) {
      return formatMetric(toNumber(row[key]));
    }
    return displayValue(row[key]);
  };

  return (
    <div className="overflow-auto">
      <table className="w-full min-w-[520px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-700 text-slate-500">
            {NAMESPACE_TABLE_COLUMNS.map((column) => (
              <th key={column.key} className="px-1.5 py-1 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.idx}
              className={`cursor-pointer border-b border-slate-800/80 transition-colors ${tableRowClass(selectedIdx === row.idx)}`}
              onClick={() => onSelect(row.idx)}
            >
              {NAMESPACE_TABLE_COLUMNS.map((column) => {
                if (column.key === "okd_egressip1" || column.key === "okd_egressip2") {
                  const ip =
                    column.key === "okd_egressip1" ? row.okd_egressip1 : row.okd_egressip2;
                  return (
                    <td key={column.key} className="max-w-[140px] px-1.5 py-1 font-mono">
                      <EgressIpCell ip={ip} usingEgressIp={row.using_egressip} />
                    </td>
                  );
                }
                const text = renderCell(
                  row as unknown as Record<string, unknown>,
                  column.key,
                );
                return (
                  <td
                    key={column.key}
                    className="max-w-[140px] truncate px-1.5 py-1 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
          {summary ? (
            <tr className="border-t border-slate-600 bg-slate-900/70 font-semibold text-sky-100">
              {NAMESPACE_TABLE_COLUMNS.map((column) => {
                const text = renderCell(summary, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[140px] truncate px-1.5 py-1.5 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function buildNodeSummary(rows: NodeListItem[]): Record<string, unknown> | null {
  if (rows.length === 0) {
    return null;
  }
  let cpuTotal = 0;
  let memTotal = 0;
  let hasCpu = false;
  let hasMem = false;

  for (const row of rows) {
    const cpu = toNumber(row.node_cpu);
    if (cpu !== null) {
      cpuTotal += cpu;
      hasCpu = true;
    }
    const mem = toNumber(row.node_mem);
    if (mem !== null) {
      memTotal += mem;
      hasMem = true;
    }
  }

  return {
    node_name: `Σ summary (${rows.length})`,
    node_role: "",
    node_cpu: hasCpu ? cpuTotal : null,
    node_mem: hasMem ? memTotal : null,
    node_os: "",
    node_k8s_ver: "",
  };
}

function NodeTable({
  rows,
  selectedIdx,
  onSelect,
}: {
  rows: NodeListItem[];
  selectedIdx: number | null;
  onSelect: (idx: number) => void;
}) {
  const summary = useMemo(() => buildNodeSummary(rows), [rows]);
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">항목이 없습니다.</p>;
  }

  const renderCell = (row: Record<string, unknown>, key: string) => {
    if (key === "node_cpu" || key === "node_mem") {
      return formatMetric(toNumber(row[key]));
    }
    return displayValue(row[key]);
  };

  return (
    <div className="overflow-auto">
      <table className="w-full min-w-[420px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-700 text-slate-500">
            {NODE_TABLE_COLUMNS.map((column) => (
              <th key={column.key} className="px-1.5 py-1 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.idx}
              className={`cursor-pointer border-b border-slate-800/80 transition-colors ${tableRowClass(selectedIdx === row.idx)}`}
              onClick={() => onSelect(row.idx)}
            >
              {NODE_TABLE_COLUMNS.map((column) => {
                const text = renderCell(
                  row as unknown as Record<string, unknown>,
                  column.key,
                );
                return (
                  <td
                    key={column.key}
                    className="max-w-[160px] truncate px-1.5 py-1 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
          {summary ? (
            <tr className="border-t border-slate-600 bg-slate-900/70 font-semibold text-sky-100">
              {NODE_TABLE_COLUMNS.map((column) => {
                const text = renderCell(summary, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[160px] truncate px-1.5 py-1.5 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function buildPodsOnNodeSummary(rows: Record<string, unknown>[]): Record<string, unknown> | null {
  if (rows.length === 0) {
    return null;
  }
  let cpuReq = 0;
  let cpuLim = 0;
  let memReq = 0;
  let memLim = 0;
  let hasCpuReq = false;
  let hasCpuLim = false;
  let hasMemReq = false;
  let hasMemLim = false;

  for (const row of rows) {
    const cr = toNumber(row.cpu_request);
    if (cr !== null) {
      cpuReq += cr;
      hasCpuReq = true;
    }
    const cl = toNumber(row.cpu_limit);
    if (cl !== null) {
      cpuLim += cl;
      hasCpuLim = true;
    }
    const mr = toNumber(row.mem_request);
    if (mr !== null) {
      memReq += mr;
      hasMemReq = true;
    }
    const ml = toNumber(row.mem_limit);
    if (ml !== null) {
      memLim += ml;
      hasMemLim = true;
    }
  }

  return {
    namespace: `Σ summary (${rows.length})`,
    pod_name: "",
    cpu_request: hasCpuReq ? cpuReq : null,
    cpu_limit: hasCpuLim ? cpuLim : null,
    mem_request: hasMemReq ? memReq : null,
    mem_limit: hasMemLim ? memLim : null,
    age: "",
  };
}

function PodsOnNodeTable({ rows }: { rows: Record<string, unknown>[] }) {
  const summary = useMemo(() => buildPodsOnNodeSummary(rows), [rows]);
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">노드에 파드가 없습니다.</p>;
  }

  const renderCell = (row: Record<string, unknown>, key: string) => {
    if (
      key === "cpu_request" ||
      key === "cpu_limit" ||
      key === "mem_request" ||
      key === "mem_limit"
    ) {
      return formatMetric(toNumber(row[key]));
    }
    return displayValue(row[key]);
  };

  return (
    <div className="overflow-auto">
      <table className="w-full min-w-[480px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-700 text-slate-500">
            {PODS_ON_NODE_COLUMNS.map((column) => (
              <th key={column.key} className="px-1.5 py-1 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-slate-800/80 text-slate-200">
              {PODS_ON_NODE_COLUMNS.map((column) => {
                const text = renderCell(row, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[140px] truncate px-1.5 py-1 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
          {summary ? (
            <tr className="border-t border-slate-600 bg-slate-900/70 font-semibold text-sky-100">
              {PODS_ON_NODE_COLUMNS.map((column) => {
                const text = renderCell(summary, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[140px] truncate px-1.5 py-1.5 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
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

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatMetric(value: number | null, digits = 2): string {
  if (value === null) {
    return "-";
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function buildDeploymentSummary(rows: Record<string, unknown>[]): Record<string, unknown> | null {
  if (rows.length === 0) {
    return null;
  }
  let replicasTotal = 0;
  let readyTotal = 0;
  let cpuReqTotal = 0;
  let memReqTotal = 0;
  let cpuLimTotal = 0;
  let memLimTotal = 0;
  let hasCpuReq = false;
  let hasMemReq = false;
  let hasCpuLim = false;
  let hasMemLim = false;
  let hasReady = false;

  for (const row of rows) {
    const replicas = toNumber(row.replicas) ?? 0;
    replicasTotal += replicas;

    const ready = toNumber(row.readyreplicas);
    if (ready !== null) {
      readyTotal += ready;
      hasReady = true;
    }

    const cpuReq = toNumber(row.resource_cpu_request);
    if (cpuReq !== null) {
      cpuReqTotal += cpuReq * replicas;
      hasCpuReq = true;
    }
    const memReq = toNumber(row.resource_mem_request);
    if (memReq !== null) {
      memReqTotal += memReq * replicas;
      hasMemReq = true;
    }
    const cpuLim = toNumber(row.resource_cpu_limit);
    if (cpuLim !== null) {
      cpuLimTotal += cpuLim * replicas;
      hasCpuLim = true;
    }
    const memLim = toNumber(row.resource_mem_limit);
    if (memLim !== null) {
      memLimTotal += memLim * replicas;
      hasMemLim = true;
    }
  }

  return {
    name: "Σ summary",
    type: "",
    replicas: replicasTotal,
    readyreplicas: hasReady ? readyTotal : null,
    resource_cpu_request: hasCpuReq ? cpuReqTotal : null,
    resource_mem_request: hasMemReq ? memReqTotal : null,
    resource_cpu_limit: hasCpuLim ? cpuLimTotal : null,
    resource_mem_limit: hasMemLim ? memLimTotal : null,
    containers_cnt: "",
  };
}

function DeploymentTable({ rows }: { rows: Record<string, unknown>[] }) {
  const summary = useMemo(() => buildDeploymentSummary(rows), [rows]);
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">Deployment가 없습니다.</p>;
  }

  const renderCell = (row: Record<string, unknown>, key: string) => {
    if (
      key === "resource_cpu_request" ||
      key === "resource_mem_request" ||
      key === "resource_cpu_limit" ||
      key === "resource_mem_limit" ||
      key === "replicas" ||
      key === "readyreplicas"
    ) {
      return formatMetric(toNumber(row[key]));
    }
    return displayValue(row[key]);
  };

  return (
    <div className="overflow-auto">
      <table className="w-full min-w-[360px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-700 text-slate-500">
            {DEP_COLUMNS.map((column) => (
              <th key={column.key} className="px-1.5 py-1 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-slate-800/80 text-slate-200">
              {DEP_COLUMNS.map((column) => {
                const text = renderCell(row, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[120px] truncate px-1.5 py-1 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
          {summary ? (
            <tr className="border-t border-slate-600 bg-slate-900/70 font-semibold text-sky-100">
              {DEP_COLUMNS.map((column) => {
                const text = renderCell(summary, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[120px] truncate px-1.5 py-1.5 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function buildPvcSummary(rows: Record<string, unknown>[]): Record<string, unknown> | null {
  if (rows.length === 0) {
    return null;
  }
  let capacityTotal = 0;
  let usedTotal = 0;
  let hasCapacity = false;
  let hasUsed = false;

  for (const row of rows) {
    const capacity = toNumber(row.capacity);
    if (capacity !== null) {
      capacityTotal += capacity;
      hasCapacity = true;
    }
    const used = toNumber(row.used);
    if (used !== null) {
      usedTotal += used;
      hasUsed = true;
    }
  }

  return {
    name: "Σ summary",
    storage_class: "",
    capacity: hasCapacity ? capacityTotal : null,
    used: hasUsed ? usedTotal : null,
    access_mode: "",
  };
}

function PvcTable({ rows }: { rows: Record<string, unknown>[] }) {
  const summary = useMemo(() => buildPvcSummary(rows), [rows]);
  if (rows.length === 0) {
    return <p className="text-[11px] text-slate-500">PVC가 없습니다.</p>;
  }

  const renderCell = (row: Record<string, unknown>, key: string) => {
    if (key === "capacity" || key === "used") {
      return formatMetric(toNumber(row[key]));
    }
    return displayValue(row[key]);
  };

  return (
    <div className="overflow-auto">
      <table className="w-full min-w-[280px] border-collapse text-left text-[11px]">
        <thead>
          <tr className="border-b border-slate-700 text-slate-500">
            {PVC_COLUMNS.map((column) => (
              <th key={column.key} className="px-1.5 py-1 font-medium">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-slate-800/80 text-slate-200">
              {PVC_COLUMNS.map((column) => {
                const text = renderCell(row, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[120px] truncate px-1.5 py-1 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
          {summary ? (
            <tr className="border-t border-slate-600 bg-slate-900/70 font-semibold text-sky-100">
              {PVC_COLUMNS.map((column) => {
                const text = renderCell(summary, column.key);
                return (
                  <td
                    key={column.key}
                    className="max-w-[120px] truncate px-1.5 py-1.5 font-mono"
                    title={text}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

const NAMESPACE_TABLE_COLUMNS = [
  { key: "namespace", label: "namespace" },
  { key: "okd_display_name", label: "display name" },
  { key: "resource_quota_cpu_limit", label: "CPU quota" },
  { key: "resource_quota_mem_limit", label: "Mem quota (Gi)" },
  { key: "resource_quota_pod_limit", label: "Pod quota" },
  { key: "okd_egressip1", label: "egressIP1" },
  { key: "okd_egressip2", label: "egressIP2" },
  { key: "egressip_assigned_node", label: "egressIP node" },
];

const NODE_TABLE_COLUMNS = [
  { key: "node_name", label: "node" },
  { key: "node_role", label: "role" },
  { key: "node_cpu", label: "CPU" },
  { key: "node_mem", label: "Mem (Gi)" },
  { key: "node_os", label: "OS" },
  { key: "node_k8s_ver", label: "K8s ver" },
];

const PODS_ON_NODE_COLUMNS = [
  { key: "namespace", label: "namespace" },
  { key: "pod_name", label: "pod" },
  { key: "cpu_request", label: "cpu req" },
  { key: "cpu_limit", label: "cpu lim" },
  { key: "mem_request", label: "mem req (Gi)" },
  { key: "mem_limit", label: "mem lim (Gi)" },
  { key: "age", label: "age" },
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
  { key: "readyreplicas", label: "ready" },
  { key: "resource_cpu_request", label: "cpu req" },
  { key: "resource_mem_request", label: "mem req" },
  { key: "resource_cpu_limit", label: "cpu lim" },
  { key: "resource_mem_limit", label: "mem lim" },
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
    if (category === "vms") {
      return vms.map((item) => ({
        idx: item.idx,
        label: item.namespace ? `${item.namespace}/${item.name}` : item.name,
      }));
    }
    return [];
  }, [category, vms]);

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
          {category === "namespaces" ? (
            <>
              <div className="max-h-[45%] shrink-0 overflow-y-auto overscroll-contain border-b border-slate-800 pb-2">
                {isLoadingList ? (
                  <p className="text-[11px] text-slate-500">목록 불러오는 중...</p>
                ) : (
                  <SelectableNamespaceTable
                    rows={namespaces}
                    selectedIdx={selectedIdx}
                    onSelect={setSelectedIdx}
                  />
                )}
              </div>
              {selectedIdx != null ? (
                <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain">
                  {isLoadingDetail && !namespaceDetail ? (
                    <p className="text-[11px] text-slate-500">불러오는 중...</p>
                  ) : (
                    <>
                      <div>
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                          Deployments
                        </p>
                        <DeploymentTable rows={namespaceDetail?.deployments ?? []} />
                      </div>
                      <div>
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                          PVCs
                        </p>
                        <PvcTable rows={namespaceDetail?.pvcs ?? []} />
                      </div>
                    </>
                  )}
                </div>
              ) : !isLoadingList ? (
                <p className="text-[11px] text-slate-500">표에서 네임스페이스를 선택하세요.</p>
              ) : null}
            </>
          ) : category === "nodes" ? (
            <>
              <div className="max-h-[45%] shrink-0 overflow-y-auto overscroll-contain border-b border-slate-800 pb-2">
                {isLoadingList ? (
                  <p className="text-[11px] text-slate-500">목록 불러오는 중...</p>
                ) : (
                  <NodeTable
                    rows={nodes}
                    selectedIdx={selectedIdx}
                    onSelect={setSelectedIdx}
                  />
                )}
              </div>
              {selectedIdx != null ? (
                <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Pods on node
                  </p>
                  {isLoadingDetail && !nodeDetail ? (
                    <p className="text-[11px] text-slate-500">불러오는 중...</p>
                  ) : (
                    <PodsOnNodeTable rows={nodeDetail?.pods ?? []} />
                  )}
                </div>
              ) : !isLoadingList ? (
                <p className="text-[11px] text-slate-500">표에서 노드를 선택하세요.</p>
              ) : null}
            </>
          ) : (
            <>
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

              {category === "vms" && selectedIdx == null && !isLoadingList ? (
                <p className="text-[11px] text-slate-500">목록에서 항목을 선택하세요.</p>
              ) : null}
            </>
          )}
        </div>
      )}
    </section>
  );
}
