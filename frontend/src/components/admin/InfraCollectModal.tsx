import { useCallback, useEffect, useState } from "react";

import { ROLE_ADMIN } from "../../types/user";

interface K8sCollectorCluster {
  agent_id: string;
  display_name: string;
  last_update: string | null;
  operation_status: string;
  operation_detail: string | null;
}

interface InfraCollectModalProps {
  viewerRole: number;
  onClose: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function InfraCollectModal({ viewerRole, onClose }: InfraCollectModalProps) {
  const [clusters, setClusters] = useState<K8sCollectorCluster[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [collectingIds, setCollectingIds] = useState<Set<string>>(new Set());
  const [rowMessages, setRowMessages] = useState<Record<string, string>>({});

  const loadClusters = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/k8s-collector/clusters?viewer_role=${viewerRole}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "클러스터 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as K8sCollectorCluster[];
      setClusters(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "클러스터 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [viewerRole]);

  useEffect(() => {
    void loadClusters();
  }, [loadClusters]);

  const handleCollect = async (clusterId: string) => {
    if (viewerRole !== ROLE_ADMIN) {
      setError("관리자만 수집을 실행할 수 있습니다.");
      return;
    }
    setCollectingIds((current) => new Set(current).add(clusterId));
    setRowMessages((current) => ({ ...current, [clusterId]: "수집 중..." }));
    setError(null);
    try {
      const response = await fetch(`/api/k8s-collector/clusters/${encodeURIComponent(clusterId)}/collect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ viewer_role: viewerRole }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "수집에 실패했습니다."));
      }
      const result = (await response.json()) as {
        last_update: string | null;
        counts: Record<string, number>;
      };
      const summary = [
        result.counts.nodes != null ? `nodes=${result.counts.nodes}` : null,
        result.counts.namespaces != null ? `ns=${result.counts.namespaces}` : null,
        result.counts.pods != null ? `pods=${result.counts.pods}` : null,
      ]
        .filter(Boolean)
        .join(", ");
      setRowMessages((current) => ({
        ...current,
        [clusterId]: summary ? `완료 (${summary})` : "완료",
      }));
      await loadClusters();
    } catch (err) {
      const message = err instanceof Error ? err.message : "수집에 실패했습니다.";
      setRowMessages((current) => ({ ...current, [clusterId]: message }));
      setError(message);
    } finally {
      setCollectingIds((current) => {
        const next = new Set(current);
        next.delete(clusterId);
        return next;
      });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="infra-collect-title"
        className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
          <div>
            <h2 id="infra-collect-title" className="text-sm font-semibold text-slate-100">
              인프라 정보 수집
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              일반 Kubernetes 에이전트 인벤토리를 수동으로 수집합니다. (기동/스케줄 자동 수집은 중지됨)
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </header>

        {error ? (
          <div className="mx-4 mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <p className="text-sm text-slate-500">목록을 불러오는 중...</p>
          ) : (
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-slate-400">
                  <th className="px-3 py-2">에이전트 ID</th>
                  <th className="px-3 py-2">이름</th>
                  <th className="px-3 py-2">최근 수집</th>
                  <th className="px-3 py-2">상태</th>
                  <th className="px-3 py-2 text-right">수집</th>
                </tr>
              </thead>
              <tbody>
                {clusters.map((cluster) => {
                  const isCollecting = collectingIds.has(cluster.agent_id);
                  return (
                    <tr key={cluster.agent_id} className="border-b border-slate-800 text-slate-200">
                      <td className="px-3 py-2 font-mono text-xs">{cluster.agent_id}</td>
                      <td className="px-3 py-2">{cluster.display_name}</td>
                      <td className="px-3 py-2 text-slate-400">
                        {cluster.last_update ?? "-"}
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-400">
                        {rowMessages[cluster.agent_id]
                          ?? cluster.operation_detail
                          ?? cluster.operation_status}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          disabled={isCollecting}
                          onClick={() => void handleCollect(cluster.agent_id)}
                          className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700"
                        >
                          {isCollecting ? "수집 중..." : "수집"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
