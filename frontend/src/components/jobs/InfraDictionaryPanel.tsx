import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useTheme } from "../../context/ThemeContext";
import { JobFieldLabel } from "./JobFieldLabel";

interface InfraDictionaryPayload {
  loaded_at: string;
  infra_type: Record<string, string[]>;
  k8s_cluster_nodes: Record<string, string[]>;
  k8s_cluster_namespaces: Record<string, string[]>;
  k8s_cluster_deployments: Record<string, string[]>;
  kubevirt_cluster_nodes: Record<string, string[]>;
  kubevirt_cluster_namespaces: Record<string, string[]>;
  kubevirt_cluster_deployments: Record<string, string[]>;
  kubevirt_cluster_vms: Record<string, string[]>;
  vsphere_cluster_vms: Record<string, string[]>;
}

type InfraTypeKey = "k8s" | "kubevirt" | "vSphere" | "unknown";
type ResourceKind =
  | "nodes"
  | "namespaces"
  | "deployments"
  | "vms"
  | "system_code"
  | "app_service"
  | "ops_owner"
  | "ops_team"
  | "ip"
  | "hostname"
  | "domain";

/** http 모드 필드→fastspell 라벨. 없으면 자동완성 안 함. mock 은 항상 `all`. */
const FASTSPELL_FIELD_LABEL: Partial<Record<ResourceKind, string>> = {
  app_service: "project",
  ops_owner: "manager",
  ops_team: "department",
  ip: "ip",
  hostname: "hostname",
};

function resolveFastspellLabel(
  kind: ResourceKind | null,
  runtimeMode: string,
): string | null {
  if (!kind || !(kind in FASTSPELL_FIELD_LABEL)) {
    return null;
  }
  if (runtimeMode === "http") {
    return FASTSPELL_FIELD_LABEL[kind] ?? null;
  }
  return "all";
}

/** Which level's candidates are currently shown (left → right). */
type ActiveLevel = "type" | "cluster" | "resource" | "value";

const TYPE_OPTIONS: { key: InfraTypeKey; label: string; ready: boolean }[] = [
  { key: "k8s", label: "OKD(k8s)", ready: true },
  { key: "kubevirt", label: "KubeVirt(VM)", ready: true },
  { key: "vSphere", label: "vSphere(VM)", ready: true },
  { key: "unknown", label: "모름", ready: true },
];

const K8S_RESOURCE_OPTIONS: { key: ResourceKind; label: string }[] = [
  { key: "nodes", label: "클러스터 노드" },
  { key: "namespaces", label: "프로젝트" },
  { key: "deployments", label: "디플로이먼트" },
];

const KUBEVIRT_RESOURCE_OPTIONS: { key: ResourceKind; label: string }[] = [
  { key: "nodes", label: "클러스터 노드" },
  { key: "namespaces", label: "프로젝트" },
  { key: "deployments", label: "디플로이먼트" },
  { key: "vms", label: "VM" },
];

const VSPHERE_RESOURCE_OPTIONS: { key: ResourceKind; label: string }[] = [
  { key: "vms", label: "VM" },
];

const UNKNOWN_RESOURCE_OPTIONS: { key: ResourceKind; label: string }[] = [
  { key: "system_code", label: "시스템코드" },
  { key: "app_service", label: "애플리케이션 서비스명" },
  { key: "ops_owner", label: "운영담당자" },
  { key: "ops_team", label: "운영팀" },
  { key: "ip", label: "IP" },
  { key: "hostname", label: "호스트명" },
  { key: "domain", label: "도메인명" },
];

/** Types that pick a cluster from redis before resource category. */
const CLUSTER_TYPES = new Set<InfraTypeKey>(["k8s", "kubevirt", "vSphere"]);

const ROOT_LABEL = "인프라 형태";
const CLUSTER_PLACEHOLDER = "클러스터";
const RESOURCE_PLACEHOLDER = "대상";

/** Strip trailing " (display)" so redis hash field (raw cluster_name) can be used. */
function clusterLookupKey(label: string): string {
  const trimmed = label.trim();
  const open = trimmed.lastIndexOf(" (");
  if (open > 0 && trimmed.endsWith(")")) {
    return trimmed.slice(0, open);
  }
  return trimmed;
}

const CHIP =
  "rounded border border-slate-600 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-200 hover:border-sky-500 hover:text-sky-200 disabled:cursor-not-allowed disabled:opacity-40";
const CHIP_ACTIVE = "border-sky-500 bg-sky-950/60 text-sky-200";

/** input / ghost 공통 타이포 — 높이·baseline 맞춤 */
const FIELD_TYPE =
  "box-border px-2 text-[11px] leading-4";
const INPUT_CLASS =
  `relative z-10 h-7 w-full rounded border border-transparent bg-transparent py-0 text-slate-100 outline-none ${FIELD_TYPE}`;
const GHOST_LAYER_CLASS =
  `pointer-events-none absolute inset-0 flex items-center overflow-hidden ${FIELD_TYPE}`;

interface InfraDictionaryPanelProps {
  onPick: (token: string) => void;
}

type FastspellPayload = { q?: string; r?: string[] };

/** Top fastspell hit for the current query; discarded when response ``q`` mismatches. */
async function fetchFastspellSuggestion(
  query: string,
  label: string,
  signal: AbortSignal,
): Promise<string | null> {
  const trimmed = query.trim();
  if (!trimmed || !label) {
    return null;
  }
  const params = new URLSearchParams({ q: trimmed, l: label, n: "1" });
  const url = `/api/fastspell/search?${params.toString()}`;
  try {
    const response = await fetch(url, { signal });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as FastspellPayload;
    if (payload.q !== trimmed) {
      return null;
    }
    const first = payload.r?.[0];
    return typeof first === "string" && first.length > 0 ? first : null;
  } catch {
    if (signal.aborted) {
      return null;
    }
    return null;
  }
}

interface FastspellGhostInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder: string;
  /** null 이면 자동완성 비활성 (일반 입력) */
  label: string | null;
}

/** 마지막 공백 이후 토큰만 제시어 질의 대상으로 분리. */
function splitTrailingToken(value: string): { prefix: string; token: string } {
  const match = /^(.*(?:\s+))?(\S*)$/.exec(value);
  if (!match) {
    return { prefix: "", token: value };
  }
  return { prefix: match[1] ?? "", token: match[2] ?? "" };
}

function FastspellGhostInput({
  value,
  onChange,
  onSubmit,
  placeholder,
  label,
}: FastspellGhostInputProps) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  const { token } = splitTrailingToken(value);

  useEffect(() => {
    abortRef.current?.abort();
    if (!label || !token) {
      setSuggestion(null);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    const timer = window.setTimeout(() => {
      void fetchFastspellSuggestion(token, label, controller.signal)
        .then((hit) => {
          if (
            !controller.signal.aborted &&
            splitTrailingToken(valueRef.current).token === token
          ) {
            setSuggestion(hit);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setSuggestion(null);
          }
        });
    }, 80);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [token, label]);

  const applySuggestion = () => {
    if (!suggestion) {
      return false;
    }
    const current = splitTrailingToken(valueRef.current);
    onChange(`${current.prefix}${suggestion}`);
    setSuggestion(null);
    return true;
  };

  const lowerToken = token.toLowerCase();
  const lowerSuggestion = suggestion?.toLowerCase() ?? "";
  const isPrefix =
    Boolean(suggestion) && lowerSuggestion.startsWith(lowerToken) && token.length > 0;
  const hasGhost = Boolean(suggestion && token);
  // 밝은 테마: 흰색에 가까운 옅은 회색. 어두운 테마: slate-500.
  const ghostClass = isLight ? "text-slate-200" : "text-slate-500";

  return (
    <div className="relative h-7 min-w-[10rem] flex-1 rounded border border-slate-600 bg-slate-900 focus-within:border-sky-500">
      {hasGhost && suggestion ? (
        <div aria-hidden className={GHOST_LAYER_CLASS}>
          {isPrefix ? (
            <>
              <span className="invisible whitespace-pre">{value}</span>
              <span className={ghostClass}>
                {suggestion.slice(token.length)}
                <span className="ml-0.5 text-[9px] opacity-70">⇥</span>
              </span>
            </>
          ) : (
            <>
              {/* 초성 등 접두 불일치: 입력 글자와 겹치지 않게 오른쪽에만 제시 */}
              <span className="invisible whitespace-pre">{value}</span>
              <span className={`${ghostClass} opacity-90`}>
                {" "}
                {suggestion}
                <span className="ml-0.5 text-[9px] opacity-70">⇥</span>
              </span>
            </>
          )}
        </div>
      ) : null}
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Tab" && suggestion) {
            event.preventDefault();
            applySuggestion();
            return;
          }
          if (event.key === "Enter") {
            event.preventDefault();
            onSubmit();
          }
        }}
        placeholder={hasGhost ? undefined : placeholder}
        className={INPUT_CLASS}
        autoComplete="off"
        spellCheck={false}
      />
    </div>
  );
}

export function InfraDictionaryPanel({ onPick }: InfraDictionaryPanelProps) {
  const [data, setData] = useState<InfraDictionaryPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [runtimeMode, setRuntimeMode] = useState("mock");

  const [typeLabel, setTypeLabel] = useState(ROOT_LABEL);
  const [typeKey, setTypeKey] = useState<InfraTypeKey | null>(null);
  const [clusterLabel, setClusterLabel] = useState<string | null>(null);
  const [clusterName, setClusterName] = useState<string | null>(null);
  const [resourceLabel, setResourceLabel] = useState<string | null>(null);
  const [resourceKind, setResourceKind] = useState<ResourceKind | null>(null);
  const [resourceFieldLabel, setResourceFieldLabel] = useState<string | null>(null);
  const [activeLevel, setActiveLevel] = useState<ActiveLevel | null>(null);
  const [manualValue, setManualValue] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/infra-dictionary");
      if (!response.ok) {
        throw new Error("인프라 사전을 불러오지 못했습니다.");
      }
      const payload = (await response.json()) as InfraDictionaryPayload;
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "인프라 사전 로드 실패");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/health");
        if (!response.ok) {
          return;
        }
        const health = (await response.json()) as { runtime_mode?: string };
        if (!cancelled) {
          setRuntimeMode((health.runtime_mode || "mock").trim().toLowerCase());
        }
      } catch {
        /* keep default mock */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const fastspellLabel = useMemo(
    () => resolveFastspellLabel(resourceKind, runtimeMode),
    [resourceKind, runtimeMode],
  );

  const resetAll = () => {
    setTypeLabel(ROOT_LABEL);
    setTypeKey(null);
    setClusterLabel(null);
    setClusterName(null);
    setResourceLabel(null);
    setResourceKind(null);
    setResourceFieldLabel(null);
    setActiveLevel(null);
    setManualValue("");
  };

  const isUnknown = typeKey === "unknown";

  const resourceOptions = useMemo(() => {
    if (typeKey === "kubevirt") {
      return KUBEVIRT_RESOURCE_OPTIONS;
    }
    if (typeKey === "vSphere") {
      return VSPHERE_RESOURCE_OPTIONS;
    }
    if (typeKey === "unknown") {
      return UNKNOWN_RESOURCE_OPTIONS;
    }
    return K8S_RESOURCE_OPTIONS;
  }, [typeKey]);

  const clusters = useMemo(() => {
    if (!data || !typeKey || !CLUSTER_TYPES.has(typeKey)) {
      return [];
    }
    return data.infra_type[typeKey] ?? [];
  }, [data, typeKey]);

  const values = useMemo(() => {
    if (!data || !clusterName || !resourceKind || !typeKey) {
      return [];
    }
    if (typeKey === "k8s") {
      if (resourceKind === "nodes") {
        return data.k8s_cluster_nodes[clusterName] ?? [];
      }
      if (resourceKind === "namespaces") {
        return data.k8s_cluster_namespaces[clusterName] ?? [];
      }
      if (resourceKind === "deployments") {
        return data.k8s_cluster_deployments[clusterName] ?? [];
      }
      return [];
    }
    if (typeKey === "kubevirt") {
      if (resourceKind === "nodes") {
        return data.kubevirt_cluster_nodes?.[clusterName] ?? [];
      }
      if (resourceKind === "namespaces") {
        return data.kubevirt_cluster_namespaces?.[clusterName] ?? [];
      }
      if (resourceKind === "deployments") {
        return data.kubevirt_cluster_deployments?.[clusterName] ?? [];
      }
      if (resourceKind === "vms") {
        return data.kubevirt_cluster_vms?.[clusterName] ?? [];
      }
    }
    if (typeKey === "vSphere" && resourceKind === "vms") {
      return data.vsphere_cluster_vms?.[clusterName] ?? [];
    }
    return [];
  }, [data, clusterName, resourceKind, typeKey]);

  const selectType = (key: InfraTypeKey, label: string, ready: boolean) => {
    if (!ready) {
      return;
    }
    setTypeLabel(label);
    setTypeKey(key);
    setClusterLabel(CLUSTER_TYPES.has(key) ? CLUSTER_PLACEHOLDER : null);
    setClusterName(null);
    setResourceLabel(key === "unknown" ? RESOURCE_PLACEHOLDER : null);
    setResourceKind(null);
    setResourceFieldLabel(null);
    setManualValue("");
    if (CLUSTER_TYPES.has(key)) {
      setActiveLevel("cluster");
    } else if (key === "unknown") {
      setActiveLevel("resource");
    } else {
      setActiveLevel(null);
    }
  };

  const selectCluster = (label: string) => {
    setClusterLabel(label);
    setClusterName(clusterLookupKey(label));
    setResourceLabel(RESOURCE_PLACEHOLDER);
    setResourceKind(null);
    setResourceFieldLabel(null);
    setManualValue("");
    setActiveLevel("resource");
  };

  const selectResource = (kind: ResourceKind, label: string) => {
    setResourceLabel(label);
    setResourceKind(kind);
    setResourceFieldLabel(label);
    setManualValue("");
    setActiveLevel("value");
  };

  const pickValue = (value: string) => {
    setResourceLabel(value);
    // 인프라 형태=OKD(k8s) | 클러스터=dprv-k8s (표시명) | 클러스터 노드=worker-1
    const level3Label = resourceFieldLabel || RESOURCE_PLACEHOLDER;
    const token = [
      `${ROOT_LABEL}=${typeLabel}`,
      `${CLUSTER_PLACEHOLDER}=${clusterLabel ?? clusterName ?? ""}`,
      `${level3Label}=${value}`,
    ].join(" | ");
    onPick(token);
    setActiveLevel(null);
  };

  const submitManualValue = () => {
    const trimmed = manualValue.trim();
    if (!trimmed || !resourceFieldLabel) {
      return;
    }
    setResourceLabel(trimmed);
    // 모름: "모름 /" 없이 구분값=입력값만 (예: 운영담당자=홍길동)
    onPick(`${resourceFieldLabel}=${trimmed}`);
    setManualValue("");
    setActiveLevel(null);
  };

  return (
    <div className="w-full shrink-0">
      <div className="mb-1 flex items-center justify-between gap-2">
        <JobFieldLabel bullet="📚">인프라 사전</JobFieldLabel>
        {data?.loaded_at ? (
          <span className="truncate text-[10px] text-slate-500">갱신 {data.loaded_at}</span>
        ) : null}
      </div>
      <div className="h-[100px] w-full overflow-y-auto rounded-md border border-slate-700 bg-slate-950/70 p-2">
        {loading ? (
          <p className="text-xs text-slate-500">불러오는 중...</p>
        ) : error ? (
          <div className="space-y-2">
            <p className="text-xs text-rose-300">{error}</p>
            <button type="button" className={CHIP} onClick={() => void load()}>
              다시 시도
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                className={`${CHIP} ${activeLevel === "type" || typeKey ? CHIP_ACTIVE : ""}`}
                onClick={() => {
                  setTypeLabel(ROOT_LABEL);
                  setTypeKey(null);
                  setClusterLabel(null);
                  setClusterName(null);
                  setResourceLabel(null);
                  setResourceKind(null);
                  setResourceFieldLabel(null);
                  setManualValue("");
                  setActiveLevel("type");
                }}
              >
                {typeLabel}
              </button>
              {clusterLabel !== null ? (
                <button
                  type="button"
                  className={`${CHIP} ${activeLevel === "cluster" || clusterName ? CHIP_ACTIVE : ""}`}
                  onClick={() => {
                    setClusterLabel(CLUSTER_PLACEHOLDER);
                    setClusterName(null);
                    setResourceLabel(null);
                    setResourceKind(null);
                    setResourceFieldLabel(null);
                    setManualValue("");
                    setActiveLevel("cluster");
                  }}
                >
                  {clusterLabel}
                </button>
              ) : null}
              {resourceLabel !== null ? (
                <button
                  type="button"
                  className={`${CHIP} ${activeLevel === "resource" || activeLevel === "value" || resourceKind ? CHIP_ACTIVE : ""}`}
                  onClick={() => {
                    setResourceLabel(RESOURCE_PLACEHOLDER);
                    setResourceKind(null);
                    setResourceFieldLabel(null);
                    setManualValue("");
                    setActiveLevel("resource");
                  }}
                >
                  {resourceLabel}
                </button>
              ) : null}
              {(typeKey || activeLevel) && (
                <button type="button" className={CHIP} onClick={resetAll}>
                  초기화
                </button>
              )}
            </div>

            {activeLevel === null && !typeKey ? (
              <p className="text-[11px] text-slate-500">
                「인프라 형태」를 눌러 대상 인프라를 고르세요. 최종 값은 작업 내용에 삽입됩니다.
              </p>
            ) : null}

            {activeLevel === "type" ? (
              <div className="flex flex-wrap gap-1.5">
                {TYPE_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    disabled={!option.ready}
                    title={option.ready ? undefined : "준비 중"}
                    className={CHIP}
                    onClick={() => selectType(option.key, option.label, option.ready)}
                  >
                    {option.label}
                    {!option.ready ? " (준비중)" : ""}
                  </button>
                ))}
              </div>
            ) : null}

            {activeLevel === "cluster" ? (
              <div className="flex flex-wrap gap-1.5">
                {clusters.length === 0 ? (
                  <p className="text-[11px] text-slate-500">
                    등록된 {typeKey} 클러스터가 없습니다.
                  </p>
                ) : (
                  clusters.map((name) => (
                    <button
                      key={name}
                      type="button"
                      className={CHIP}
                      onClick={() => selectCluster(name)}
                    >
                      {name}
                    </button>
                  ))
                )}
              </div>
            ) : null}

            {activeLevel === "resource" ? (
              <div className="flex flex-wrap gap-1.5">
                {resourceOptions.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className={CHIP}
                    onClick={() => selectResource(option.key, option.label)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            ) : null}

            {activeLevel === "value" && isUnknown ? (
              <div className="flex flex-wrap items-center gap-1.5">
                <FastspellGhostInput
                  value={manualValue}
                  onChange={setManualValue}
                  onSubmit={submitManualValue}
                  placeholder={resourceFieldLabel ? `${resourceFieldLabel} 입력` : "값 입력"}
                  label={fastspellLabel}
                />
                <button
                  type="button"
                  className={CHIP}
                  disabled={!manualValue.trim()}
                  onClick={submitManualValue}
                >
                  삽입
                </button>
              </div>
            ) : null}

            {activeLevel === "value" && !isUnknown ? (
              <div className="flex flex-wrap gap-1.5">
                {values.length === 0 ? (
                  <p className="text-[11px] text-slate-500">항목이 없습니다.</p>
                ) : (
                  values.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={CHIP}
                      onClick={() => pickValue(value)}
                      title="작업 내용에 삽입"
                    >
                      {value}
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
