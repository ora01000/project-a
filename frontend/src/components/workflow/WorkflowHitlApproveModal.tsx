import { useCallback, useEffect, useState } from "react";

interface HitlInfo {
  job_idx: number;
  workflow_uuid: string;
  work_uuid: string;
  work_name: string;
  upload: boolean;
  upload_path: string;
  approver_userid: string;
  files: string[];
}

interface WorkflowHitlApproveModalProps {
  jobIdx: number;
  actorUserid: string;
  onClose: () => void;
  onDone: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

export function WorkflowHitlApproveModal({
  jobIdx,
  actorUserid,
  onClose,
  onDone,
}: WorkflowHitlApproveModalProps) {
  const [info, setInfo] = useState<HitlInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/workflow-jobs/${jobIdx}/hitl`);
      if (!response.ok) {
        throw new Error(await parseError(response, "승인 정보를 불러오지 못했습니다."));
      }
      setInfo((await response.json()) as HitlInfo);
    } catch (err) {
      setInfo(null);
      setError(err instanceof Error ? err.message : "승인 정보를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [jobIdx]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleUpload = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const body = new FormData();
      Array.from(fileList).forEach((file) => body.append("files", file));
      const response = await fetch(`/api/workflow-jobs/${jobIdx}/attachments`, {
        method: "POST",
        body,
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "파일 업로드에 실패했습니다."));
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "파일 업로드에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApprove = async () => {
    if (info?.upload && (!info.files || info.files.length === 0)) {
      setError("승인 전에 파일을 업로드해야 합니다.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${jobIdx}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor_userid: actorUserid }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "승인에 실패했습니다."));
      }
      onDone();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "승인에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      setError("반려 사유를 입력하세요.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${jobIdx}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor_userid: actorUserid,
          drop_reason: rejectReason.trim(),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "반려에 실패했습니다."));
      }
      onDone();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "반려에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-lg border border-slate-700 bg-slate-950 p-4 shadow-xl">
        <header className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-100">작업 워크플로우 승인</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-600 px-2 py-0.5 text-[11px] text-slate-300 hover:bg-slate-800"
          >
            닫기
          </button>
        </header>
        {isLoading ? <p className="text-[11px] text-slate-500">불러오는 중…</p> : null}
        {error ? <p className="mb-2 text-[11px] text-rose-300">{error}</p> : null}
        {info ? (
          <div className="space-y-3 text-[11px] text-slate-300">
            <p>
              <span className="text-slate-500">승인 단계</span> {info.work_name || info.work_uuid}
            </p>
            {info.upload ? (
              <div className="space-y-2 rounded border border-slate-700 bg-slate-900/60 p-2">
                <p className="font-medium text-amber-200">파일 업로드 필수 (텍스트만)</p>
                <input
                  type="file"
                  multiple
                  disabled={isSubmitting}
                  onChange={(event) => void handleUpload(event.target.files)}
                  className="block w-full text-[11px] text-slate-300"
                />
                {info.files.length > 0 ? (
                  <ul className="list-disc pl-4 text-slate-400">
                    {info.files.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-500">아직 업로드된 파일이 없습니다.</p>
                )}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => void handleApprove()}
                className="rounded bg-emerald-700 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                승인
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => void handleReject()}
                className="rounded bg-rose-800 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-rose-700 disabled:opacity-50"
              >
                반려
              </button>
            </div>
            <textarea
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              rows={2}
              placeholder="반려 사유 (반려 시 필수)"
              className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-200"
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
