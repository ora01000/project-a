import type { JobNotification } from "../../types/job";
import { JOB_NOTIFICATION_REVIEW } from "../../types/job";

interface JobNotificationCardProps {
  notification: JobNotification;
  onReview: (jobIdx: number) => void;
  onApprove: (jobIdx: number) => void;
  onPending: (jobIdx: number) => void;
  onReject: (jobIdx: number) => void;
  isProcessing: boolean;
}

export function JobNotificationCard({
  notification,
  onReview,
  onApprove,
  onPending,
  onReject,
  isProcessing,
}: JobNotificationCardProps) {
  const isReviewRequest = notification.notification_type === JOB_NOTIFICATION_REVIEW;

  return (
    <div className="rounded-md border border-amber-700/50 bg-amber-950/20 px-3 py-3 text-slate-100">
      <div className="mb-2 inline-flex rounded-full border border-amber-600/50 bg-amber-900/40 px-2 py-0.5 text-[11px] font-medium text-amber-200">
        {notification.title}
      </div>
      <p className="text-sm text-slate-200">{notification.message}</p>

      {isReviewRequest ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onReview(notification.job_idx)}
            className="rounded-md border border-sky-700 px-2 py-1 text-xs text-sky-200 hover:bg-sky-950/40 disabled:text-slate-500"
          >
            검토
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onApprove(notification.job_idx)}
            className="rounded-md border border-emerald-700 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-950/40 disabled:text-slate-500"
          >
            승인
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onPending(notification.job_idx)}
            className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:text-slate-500"
          >
            보류
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onReject(notification.job_idx)}
            className="rounded-md border border-rose-700 px-2 py-1 text-xs text-rose-200 hover:bg-rose-950/40 disabled:text-slate-500"
          >
            반려
          </button>
        </div>
      ) : null}
    </div>
  );
}
