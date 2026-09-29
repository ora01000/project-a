import { useState } from "react";

interface JobCancelReasonModalProps {
  defaultReason: string;
  onClose: () => void;
  onSave: (reason: string) => void;
}

export function JobCancelReasonModal({
  defaultReason,
  onClose,
  onSave,
}: JobCancelReasonModalProps) {
  const [reason, setReason] = useState(defaultReason.slice(0, 200));
  const [error, setError] = useState<string | null>(null);

  const handleSave = () => {
    const normalized = reason.trim();
    if (!normalized) {
      setError("취소 사유를 입력해 주세요.");
      return;
    }
    onSave(normalized.slice(0, 200));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-base font-semibold text-slate-100">작업 취소 사유</h2>
        <p className="mt-1 text-xs text-slate-400">처리 결과 내용이 기본으로 입력됩니다. 필요 시 수정하세요.</p>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value.slice(0, 200))}
          rows={5}
          maxLength={200}
          className="mt-3 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500"
          placeholder="취소 사유를 입력해 주세요."
        />
        <p className="mt-1 text-right text-[10px] text-slate-500">{reason.length}/200</p>
        {error ? <p className="mt-2 text-sm text-rose-300">{error}</p> : null}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-500"
          >
            작업 취소
          </button>
        </div>
      </div>
    </div>
  );
}
