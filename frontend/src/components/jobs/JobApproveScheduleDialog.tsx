import { useMemo, useState } from "react";

import { todayDateOnly } from "../../utils/datetime";

const DEFAULT_PLAN_TIME = "21:00:00";

function buildDefaultDate(): string {
  return todayDateOnly();
}

function buildScheduledAt(date: string, time: string): string {
  const normalizedDate = date.trim();
  const normalizedTime = time.trim() || DEFAULT_PLAN_TIME;
  const pieces = normalizedTime.split(":");
  const hour = pieces[0]?.padStart(2, "0") ?? "21";
  const minute = pieces[1]?.padStart(2, "0") ?? "00";
  const second = (pieces[2] ?? "00").padStart(2, "0").slice(0, 2);
  return `${normalizedDate} ${hour}:${minute}:${second}`;
}

interface JobApproveScheduleDialogProps {
  srnum: string;
  title?: string;
  message?: string;
  confirmLabel?: string;
  onConfirm: (payload: { isScheduled: boolean; scheduledAt: string | null }) => void;
  onCancel: () => void;
}

export function JobApproveScheduleDialog({
  srnum,
  title = "작업 승인",
  message,
  confirmLabel = "승인",
  onConfirm,
  onCancel,
}: JobApproveScheduleDialogProps) {
  const [isScheduled, setIsScheduled] = useState(false);
  const [planDate, setPlanDate] = useState(buildDefaultDate);
  const [planTime, setPlanTime] = useState(DEFAULT_PLAN_TIME);
  const [localError, setLocalError] = useState<string | null>(null);

  const preview = useMemo(
    () => (isScheduled ? buildScheduledAt(planDate, planTime) : null),
    [isScheduled, planDate, planTime],
  );

  const handleConfirm = () => {
    if (isScheduled) {
      if (!planDate.trim()) {
        setLocalError("계획 일자를 선택하세요.");
        return;
      }
      onConfirm({ isScheduled: true, scheduledAt: buildScheduledAt(planDate, planTime) });
      return;
    }
    onConfirm({ isScheduled: false, scheduledAt: null });
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="job-approve-schedule-title"
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="job-approve-schedule-title" className="text-base font-semibold text-slate-100">
          {title}
        </h2>
        <p className="mt-2 text-sm text-slate-300">
          {message ?? `${srnum} 작업을 승인하시겠습니까?`}
        </p>

        <div className="mt-4 space-y-3 rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
          <label className="flex items-center justify-between gap-3 text-sm text-slate-200">
            <span>계획 작업</span>
            <button
              type="button"
              role="switch"
              aria-checked={isScheduled}
              onClick={() => {
                setIsScheduled((current) => !current);
                setLocalError(null);
              }}
              className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                isScheduled ? "bg-sky-600" : "bg-slate-600"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                  isScheduled ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </label>

          {isScheduled ? (
            <div className="space-y-2 border-t border-slate-700/70 pt-3">
              <label className="block text-xs text-slate-400">
                계획 일자
                <input
                  type="date"
                  value={planDate}
                  onChange={(event) => {
                    setPlanDate(event.target.value);
                    setLocalError(null);
                  }}
                  className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                />
              </label>
              <label className="block text-xs text-slate-400">
                계획 시각 (기본 21:00:00)
                <input
                  type="time"
                  step={1}
                  value={planTime.slice(0, 8)}
                  onChange={(event) => {
                    const value = event.target.value;
                    setPlanTime(value.length === 5 ? `${value}:00` : value);
                    setLocalError(null);
                  }}
                  className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100"
                />
              </label>
              {preview ? (
                <p className="text-xs text-slate-400">
                  예정: <span className="font-medium text-slate-200">{preview}</span>
                </p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-slate-500">즉시 처리됩니다.</p>
          )}
        </div>

        {localError ? <p className="mt-3 text-sm text-rose-300">{localError}</p> : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            아니오
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
