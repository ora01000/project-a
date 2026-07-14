import { useState } from "react";

import type { JobNotification } from "../../types/job";
import {
  JOB_NOTIFICATION_FAILURE,
  JOB_NOTIFICATION_RESULT,
  JOB_NOTIFICATION_REVIEW,
} from "../../types/job";
import { ConfirmDialog } from "../ConfirmDialog";

interface JobNotificationCardProps {
  notification: JobNotification;
  onReview: (jobIdx: number) => void;
  onApprove: (jobIdx: number) => void;
  onPending: (jobIdx: number) => void;
  onReject: (jobIdx: number) => void;
  onDismiss?: (notificationIdx: number) => void;
  onRetry?: (jobIdx: number, notificationIdx: number) => void;
  isProcessing: boolean;
}

type JobAction = "review" | "approve" | "pending" | "reject";
type FailureAction = "dismiss" | "retry";

const ACTION_CONFIRM: Record<
  JobAction,
  { title: string; message: string; confirmLabel: string }
> = {
  review: {
    title: "검토",
    message: "이 작업을 검토하시겠습니까?",
    confirmLabel: "예",
  },
  approve: {
    title: "승인",
    message: "이 작업을 승인하시겠습니까?",
    confirmLabel: "예",
  },
  pending: {
    title: "보류",
    message: "이 작업을 보류하시겠습니까?",
    confirmLabel: "예",
  },
  reject: {
    title: "반려",
    message: "이 작업을 반려하시겠습니까?",
    confirmLabel: "예",
  },
};

const FAILURE_CONFIRM: Record<
  FailureAction,
  { title: string; message: string; confirmLabel: string }
> = {
  dismiss: {
    title: "해제",
    message: "작업 실패 알림을 해제하시겠습니까?",
    confirmLabel: "예",
  },
  retry: {
    title: "재작업",
    message: "작업을 다시 수행하시겠습니까?",
    confirmLabel: "예",
  },
};

export function JobNotificationCard({
  notification,
  onReview,
  onApprove,
  onPending,
  onReject,
  onDismiss,
  onRetry,
  isProcessing,
}: JobNotificationCardProps) {
  const [pendingAction, setPendingAction] = useState<JobAction | null>(null);
  const [pendingFailureAction, setPendingFailureAction] = useState<FailureAction | null>(null);

  const isReviewRequest = notification.notification_type === JOB_NOTIFICATION_REVIEW;
  const isExecutionResult = notification.notification_type === JOB_NOTIFICATION_RESULT;
  const isExecutionFailure = notification.notification_type === JOB_NOTIFICATION_FAILURE;

  const handleConfirm = () => {
    if (!pendingAction) {
      return;
    }
    const jobIdx = notification.job_idx;
    const action = pendingAction;
    setPendingAction(null);
    if (action === "review") {
      onReview(jobIdx);
    } else if (action === "approve") {
      onApprove(jobIdx);
    } else if (action === "pending") {
      onPending(jobIdx);
    } else {
      onReject(jobIdx);
    }
  };

  const handleFailureConfirm = () => {
    if (!pendingFailureAction) {
      return;
    }
    const action = pendingFailureAction;
    setPendingFailureAction(null);
    if (action === "dismiss") {
      onDismiss?.(notification.idx);
      return;
    }
    onRetry?.(notification.job_idx, notification.idx);
  };

  const confirmCopy = pendingAction ? ACTION_CONFIRM[pendingAction] : null;
  const failureConfirmCopy = pendingFailureAction ? FAILURE_CONFIRM[pendingFailureAction] : null;

  return (
    <>
      <div
        className={`rounded-md px-3 py-3 text-slate-100 ${
          isExecutionFailure
            ? "border border-rose-700/50 bg-rose-950/20"
            : "border border-amber-700/50 bg-amber-950/20"
        }`}
      >
        <div
          className={`mb-2 inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${
            isExecutionFailure
              ? "border border-rose-600/50 bg-rose-900/40 text-rose-200"
              : "border border-amber-600/50 bg-amber-900/40 text-amber-200"
          }`}
        >
          {notification.title}
        </div>
        <p className="whitespace-pre-wrap text-sm text-slate-200">{notification.message}</p>

        {isReviewRequest ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={isProcessing}
              onClick={() => setPendingAction("review")}
              className="rounded-md border border-sky-700 px-2 py-1 text-xs text-sky-200 hover:bg-sky-950/40 disabled:text-slate-500"
            >
              검토
            </button>
            <button
              type="button"
              disabled={isProcessing}
              onClick={() => setPendingAction("approve")}
              className="rounded-md border border-emerald-700 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-950/40 disabled:text-slate-500"
            >
              승인
            </button>
            <button
              type="button"
              disabled={isProcessing}
              onClick={() => setPendingAction("pending")}
              className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:text-slate-500"
            >
              보류
            </button>
            <button
              type="button"
              disabled={isProcessing}
              onClick={() => setPendingAction("reject")}
              className="rounded-md border border-rose-700 px-2 py-1 text-xs text-rose-200 hover:bg-rose-950/40 disabled:text-slate-500"
            >
              반려
            </button>
          </div>
        ) : null}

        {isExecutionResult && onDismiss ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={isProcessing}
              onClick={() => onDismiss(notification.idx)}
              className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:text-slate-500"
            >
              해제
            </button>
          </div>
        ) : null}

        {isExecutionFailure ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={isProcessing || !onDismiss}
              onClick={() => setPendingFailureAction("dismiss")}
              className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:text-slate-500"
            >
              해제
            </button>
            <button
              type="button"
              disabled={isProcessing || !onRetry}
              onClick={() => setPendingFailureAction("retry")}
              className="rounded-md border border-sky-700 px-2 py-1 text-xs text-sky-200 hover:bg-sky-950/40 disabled:text-slate-500"
            >
              재작업
            </button>
          </div>
        ) : null}
      </div>

      {confirmCopy ? (
        <ConfirmDialog
          title={confirmCopy.title}
          message={confirmCopy.message}
          confirmLabel={confirmCopy.confirmLabel}
          cancelLabel="아니오"
          onCancel={() => setPendingAction(null)}
          onConfirm={handleConfirm}
        />
      ) : null}

      {failureConfirmCopy ? (
        <ConfirmDialog
          title={failureConfirmCopy.title}
          message={failureConfirmCopy.message}
          confirmLabel={failureConfirmCopy.confirmLabel}
          cancelLabel="아니오"
          onCancel={() => setPendingFailureAction(null)}
          onConfirm={handleFailureConfirm}
        />
      ) : null}
    </>
  );
}
