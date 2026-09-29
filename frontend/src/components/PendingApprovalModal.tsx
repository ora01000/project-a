interface PendingApprovalModalProps {
  onClose: () => void;
}

const ADMIN_CONTACT = "IT플랫폼운영팀 윤인수";

export function PendingApprovalModal({ onClose }: PendingApprovalModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-slate-100">승인 대기 중</h2>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          가입 승인 대기 상태입니다. 관리자 승인 후 로그인할 수 있습니다.
          <br />
          문의가 필요하면 아래 담당자에게 연락해 주세요.
        </p>
        <p className="mt-4 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-medium text-sky-300">
          {ADMIN_CONTACT}
        </p>
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
