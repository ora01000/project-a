interface OpenAiBillingConfirmDialogProps {
  prompt: string;
  model?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function OpenAiBillingConfirmDialog({
  prompt,
  model,
  onConfirm,
  onCancel,
}: OpenAiBillingConfirmDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="openai-billing-dialog-title"
        className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="openai-billing-dialog-title" className="text-base font-semibold text-slate-100">
          OpenAI API 호출 확인
        </h2>
        <p className="mt-2 text-sm text-slate-300">
          OpenAI API 호출 시 과금이 발생합니다. 아래 질의로 계속 진행하시겠습니까?
        </p>
        {model ? (
          <p className="mt-2 text-xs text-slate-400">모델: {model}</p>
        ) : null}
        <div className="mt-3 max-h-48 overflow-y-auto rounded-md border border-slate-700 bg-slate-950/70 p-3">
          <p className="mb-1 text-xs font-medium text-slate-400">질의 내용</p>
          <pre className="whitespace-pre-wrap break-words text-sm text-slate-100">{prompt}</pre>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            호출
          </button>
        </div>
      </div>
    </div>
  );
}
