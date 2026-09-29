import { useMemo } from "react";

import { WorkflowIcon } from "./WorkflowIcon";

export const DEFAULT_WORK_NODE_CRON_EXPR = "0 9 * * *";

export type WorkNodeScheduleDraft = {
  enabled: boolean;
  hour: number;
  minute: number;
};

function clampInt(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(value)));
}

/** One-shot clock time stored as 5-field cron (`M H * * *`). */
export function buildWorkNodeCronExpr(draft: Omit<WorkNodeScheduleDraft, "enabled">): string {
  const minute = clampInt(draft.minute, 0, 59, 0);
  const hour = clampInt(draft.hour, 0, 23, 9);
  return `${minute} ${hour} * * *`.slice(0, 20);
}

export function parseWorkNodeCronExpr(
  cronExpr: string | null | undefined,
): Omit<WorkNodeScheduleDraft, "enabled"> {
  const parts = (cronExpr || DEFAULT_WORK_NODE_CRON_EXPR).trim().split(/\s+/);
  const minuteRaw = parts[0] ?? "0";
  const hourRaw = parts[1] ?? "9";
  return {
    hour: clampInt(Number(hourRaw === "*" ? 9 : hourRaw), 0, 23, 9),
    minute: clampInt(Number(minuteRaw === "*" ? 0 : minuteRaw), 0, 59, 0),
  };
}

export function describeWorkNodeCronExpr(cronExpr: string | null | undefined): string {
  const draft = parseWorkNodeCronExpr(cronExpr);
  return `${String(draft.hour).padStart(2, "0")}:${String(draft.minute).padStart(2, "0")} (1회)`;
}

type WorkNodeScheduleFieldProps = {
  enabled: boolean;
  cronExpr: string;
  readOnly?: boolean;
  onChange: (next: { enabled: boolean; cronExpr: string }) => void;
};

export function WorkNodeScheduleField({
  enabled,
  cronExpr,
  readOnly = false,
  onChange,
}: WorkNodeScheduleFieldProps) {
  const draft = useMemo(() => parseWorkNodeCronExpr(cronExpr), [cronExpr]);

  const emit = (
    patch: Partial<Omit<WorkNodeScheduleDraft, "enabled">> & { enabled?: boolean },
  ) => {
    const next = {
      ...draft,
      ...patch,
      enabled: patch.enabled ?? enabled,
    };
    onChange({
      enabled: next.enabled,
      cronExpr: buildWorkNodeCronExpr(next),
    });
  };

  return (
    <div className="grid gap-2 text-xs text-slate-400">
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5">
          <WorkflowIcon name="history" size="xs" />
          스케줄링
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          disabled={readOnly}
          onClick={() => emit({ enabled: !enabled })}
          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition disabled:cursor-not-allowed disabled:opacity-60 ${
            enabled ? "border-sky-500/80 bg-sky-700/70" : "border-slate-600 bg-slate-800"
          }`}
          title={enabled ? "스케줄 ON" : "스케줄 OFF"}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
              enabled ? "translate-x-5" : "translate-x-1"
            }`}
          />
        </button>
      </div>

      {enabled ? (
        <div className="rounded-lg border border-slate-700 bg-slate-950/70 p-3">
          <p className="inline-flex items-center gap-1.5 text-[11px] text-slate-400">
            <WorkflowIcon name="run" size="xs" />
            실행 시각 (1회)
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <select
              value={draft.hour}
              disabled={readOnly}
              onChange={(event) => emit({ hour: Number(event.target.value) })}
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 disabled:opacity-70"
              aria-label="시"
            >
              {Array.from({ length: 24 }, (_, hour) => (
                <option key={hour} value={hour}>
                  {String(hour).padStart(2, "0")}시
                </option>
              ))}
            </select>
            <select
              value={draft.minute}
              disabled={readOnly}
              onChange={(event) => emit({ minute: Number(event.target.value) })}
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 disabled:opacity-70"
              aria-label="분"
            >
              {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((minute) => (
                <option key={minute} value={minute}>
                  {String(minute).padStart(2, "0")}분
                </option>
              ))}
            </select>
          </div>
          <p className="mt-3 text-[11px] text-slate-300">
            {describeWorkNodeCronExpr(buildWorkNodeCronExpr(draft))}
            <span className="ml-2 text-slate-500">({buildWorkNodeCronExpr(draft)})</span>
          </p>
        </div>
      ) : null}
    </div>
  );
}
