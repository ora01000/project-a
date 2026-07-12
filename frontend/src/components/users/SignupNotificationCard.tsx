import { useState } from "react";

import { ConfirmDialog } from "../ConfirmDialog";
import type { SignupNotification } from "../../types/signup";

interface SignupNotificationCardProps {
  notification: SignupNotification;
  onApprove: (userIdx: number) => void;
  onReject: (userIdx: number, reason: string) => void;
  onHold: (notificationIdx: number) => void;
  isProcessing: boolean;
}

interface RejectReasonModalProps {
  onClose: () => void;
  onSave: (reason: string) => void;
}

function RejectReasonModal({ onClose, onSave }: RejectReasonModalProps) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSave = () => {
    if (!reason.trim()) {
      setError("반려 사유를 입력해 주세요.");
      return;
    }
    onSave(reason.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-base font-semibold text-slate-100">반려 사유 입력</h2>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={5}
          className="mt-3 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500"
          placeholder="반려 사유를 입력해 주세요."
        />
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
            저장
          </button>
        </div>
      </div>
    </div>
  );
}

export function SignupNotificationCard({
  notification,
  onApprove,
  onReject,
  onHold,
  isProcessing,
}: SignupNotificationCardProps) {
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [showRejectConfirm, setShowRejectConfirm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  return (
    <>
      <div className="rounded-md border border-violet-700/50 bg-violet-950/20 px-3 py-3 text-slate-100">
        <div className="mb-2 inline-flex rounded-full border border-violet-600/50 bg-violet-900/40 px-2 py-0.5 text-[11px] font-medium text-violet-200">
          {notification.title}
        </div>
        <pre className="whitespace-pre-wrap text-sm text-slate-200">{notification.message}</pre>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => setShowApproveConfirm(true)}
            className="rounded-md border border-emerald-700 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-950/40 disabled:text-slate-500"
          >
            승인
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => setShowRejectModal(true)}
            className="rounded-md border border-rose-700 px-2 py-1 text-xs text-rose-200 hover:bg-rose-950/40 disabled:text-slate-500"
          >
            반려
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onHold(notification.idx)}
            className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:text-slate-500"
          >
            보류
          </button>
        </div>
      </div>

      {showRejectModal ? (
        <RejectReasonModal
          onClose={() => setShowRejectModal(false)}
          onSave={(reason) => {
            setRejectReason(reason);
            setShowRejectModal(false);
            setShowRejectConfirm(true);
          }}
        />
      ) : null}

      {showApproveConfirm ? (
        <ConfirmDialog
          title="가입 승인"
          message="이 가입 신청을 승인하시겠습니까?"
          onCancel={() => setShowApproveConfirm(false)}
          onConfirm={() => {
            setShowApproveConfirm(false);
            onApprove(notification.user_idx);
          }}
        />
      ) : null}

      {showRejectConfirm ? (
        <ConfirmDialog
          title="가입 반려"
          message="입력한 사유로 가입 신청을 반려하시겠습니까?"
          onCancel={() => {
            setShowRejectConfirm(false);
            setRejectReason("");
          }}
          onConfirm={() => {
            setShowRejectConfirm(false);
            onReject(notification.user_idx, rejectReason);
            setRejectReason("");
          }}
        />
      ) : null}
    </>
  );
}
