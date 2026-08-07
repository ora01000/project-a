import { useCallback, useEffect, useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface K8sClusterRow {
  idx: number | null;
  cluster_name: string;
  last_update: string | null;
  /** true when row was added with "+" and not yet saved */
  isDraft?: boolean;
  /** local key for React list (drafts without idx) */
  localKey: string;
}

interface K8sInfraConfigModalProps {
  viewerRole: number;
  onClose: () => void;
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

let draftSeq = 0;
function nextDraftKey(): string {
  draftSeq += 1;
  return `draft-${draftSeq}`;
}

export function K8sInfraConfigModal({ viewerRole, onClose }: K8sInfraConfigModalProps) {
  const [rows, setRows] = useState<K8sClusterRow[]>([]);
  const [isEditMode, setIsEditMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [collectingIds, setCollectingIds] = useState<Set<number>>(new Set());
  const [rowMessages, setRowMessages] = useState<Record<string, string>>({});

  const loadClusters = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/k8s-infra/clusters");
      if (!response.ok) {
        throw new Error(await parseError(response, "클러스터 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as Array<{
        idx: number;
        cluster_name: string;
        last_update: string | null;
      }>;
      setRows(
        data.map((item) => ({
          idx: item.idx,
          cluster_name: item.cluster_name,
          last_update: item.last_update,
          isDraft: false,
          localKey: `idx-${item.idx}`,
        })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "클러스터 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadClusters();
  }, [loadClusters]);

  const handleAddDraftRow = () => {
    setRows((current) => [
      ...current,
      {
        idx: null,
        cluster_name: "",
        last_update: null,
        isDraft: true,
        localKey: nextDraftKey(),
      },
    ]);
  };

  const handleRemoveLastDraft = () => {
    setRows((current) => {
      const lastDraftIndex = [...current]
        .map((row, index) => ({ row, index }))
        .reverse()
        .find((entry) => entry.row.isDraft)?.index;
      if (lastDraftIndex == null) {
        return current;
      }
      return current.filter((_, index) => index !== lastDraftIndex);
    });
  };

  const handleDeleteRow = (localKey: string) => {
    setRows((current) => current.filter((row) => row.localKey !== localKey));
  };

  const handleSave = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 저장할 수 있습니다.");
      return;
    }
    const payload = rows.map((row) => ({
      idx: row.idx,
      cluster_name: row.cluster_name.trim(),
    }));
    if (payload.some((item) => !item.cluster_name)) {
      setError("클러스터 이름을 입력해 주세요.");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch("/api/k8s-infra/clusters/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clusters: payload }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "저장에 실패했습니다."));
      }
      const data = (await response.json()) as Array<{
        idx: number;
        cluster_name: string;
        last_update: string | null;
      }>;
      setRows(
        data.map((item) => ({
          idx: item.idx,
          cluster_name: item.cluster_name,
          last_update: item.last_update,
          isDraft: false,
          localKey: `idx-${item.idx}`,
        })),
      );
      setIsEditMode(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCollect = async (clusterIdx: number, localKey: string) => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 수집을 실행할 수 있습니다.");
      return;
    }
    setCollectingIds((current) => new Set(current).add(clusterIdx));
    setRowMessages((current) => ({ ...current, [localKey]: "수집 중..." }));
    setError(null);
    try {
      const response = await fetch(`/api/k8s-infra/clusters/${clusterIdx}/collect`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "수집에 실패했습니다."));
      }
      const result = (await response.json()) as {
        last_update: string | null;
        counts: Record<string, number>;
        backup_tables: string[];
      };
      const summary = [
        result.counts.nodes != null ? `nodes=${result.counts.nodes}` : null,
        result.counts.namespaces != null ? `ns=${result.counts.namespaces}` : null,
        result.counts.deployments != null ? `deploy=${result.counts.deployments}` : null,
        result.counts.pvcs != null ? `pvc=${result.counts.pvcs}` : null,
      ]
        .filter(Boolean)
        .join(", ");
      setRowMessages((current) => ({
        ...current,
        [localKey]: summary ? `완료 (${summary})` : "완료",
      }));
      await loadClusters();
    } catch (err) {
      const message = err instanceof Error ? err.message : "수집에 실패했습니다.";
      setRowMessages((current) => ({ ...current, [localKey]: message }));
      setError(message);
    } finally {
      setCollectingIds((current) => {
        const next = new Set(current);
        next.delete(clusterIdx);
        return next;
      });
    }
  };

  const handleEnterEdit = () => {
    setIsEditMode(true);
    setError(null);
  };

  const handleCancelEdit = () => {
    setIsEditMode(false);
    setError(null);
    void loadClusters();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="k8s-infra-config-title"
        className="flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
          <div>
            <h2 id="k8s-infra-config-title" className="text-sm font-semibold text-slate-100">
              K8S 인프라 구성
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              클러스터 목록을 관리하고 수동으로 인프라 정보를 수집합니다.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isEditMode ? (
              <>
                <button
                  type="button"
                  onClick={handleAddDraftRow}
                  className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
                  title="입력 row 추가"
                >
                  +
                </button>
                <button
                  type="button"
                  onClick={handleRemoveLastDraft}
                  className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
                  title="추가된 입력 row 삭제"
                >
                  −
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={handleEnterEdit}
                className="rounded-md border border-sky-700 bg-sky-950/40 px-3 py-1.5 text-sm text-sky-100 hover:bg-sky-900/50"
              >
                편집
              </button>
            )}
          </div>
        </header>

        {error ? (
          <div className="mx-4 mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <p className="text-sm text-slate-500">목록을 불러오는 중...</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-slate-500">등록된 클러스터가 없습니다.</p>
          ) : (
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-slate-400">
                  <th className="px-3 py-2">idx</th>
                  <th className="px-3 py-2">cluster_name</th>
                  <th className="px-3 py-2">last_update</th>
                  <th className="px-3 py-2">상태</th>
                  <th className="px-3 py-2 text-right">{isEditMode ? "삭제" : "수집"}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isCollecting = row.idx != null && collectingIds.has(row.idx);
                  return (
                    <tr key={row.localKey} className="border-b border-slate-800 text-slate-200">
                      <td className="px-3 py-2 font-mono text-xs text-slate-400">
                        {row.idx ?? "-"}
                      </td>
                      <td className="px-3 py-2">
                        {isEditMode ? (
                          <input
                            type="text"
                            value={row.cluster_name}
                            maxLength={50}
                            onChange={(event) => {
                              const value = event.target.value;
                              setRows((current) =>
                                current.map((item) =>
                                  item.localKey === row.localKey
                                    ? { ...item, cluster_name: value }
                                    : item,
                                ),
                              );
                            }}
                            className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-100 focus:border-sky-600 focus:outline-none"
                          />
                        ) : (
                          <span className="font-mono text-xs">{row.cluster_name}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-400">{row.last_update ?? "-"}</td>
                      <td className="px-3 py-2 text-xs text-slate-400">
                        {rowMessages[row.localKey] ?? "-"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {isEditMode ? (
                          <button
                            type="button"
                            onClick={() => handleDeleteRow(row.localKey)}
                            className="rounded-md border border-rose-800 px-3 py-1.5 text-sm text-rose-200 hover:bg-rose-950/40"
                          >
                            삭제
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={row.idx == null || isCollecting}
                            onClick={() => {
                              if (row.idx != null) {
                                void handleCollect(row.idx, row.localKey);
                              }
                            }}
                            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700"
                          >
                            {isCollecting ? "수집 중..." : "수집"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-slate-700 px-4 py-3">
          {isEditMode ? (
            <>
              <button
                type="button"
                disabled={isSaving}
                onClick={() => void handleSave()}
                className="rounded-md border border-sky-700 bg-sky-950/40 px-4 py-2 text-sm text-sky-100 hover:bg-sky-900/50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? "저장 중…" : "저장"}
              </button>
              <button
                type="button"
                onClick={handleCancelEdit}
                className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              >
                닫기
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
            >
              닫기
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
