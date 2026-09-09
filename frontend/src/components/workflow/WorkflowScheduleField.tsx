import { useMemo } from "react";

export const DEFAULT_WORKFLOW_CRON_EXPR = "0 9 * * *";

export type SchedulePreset = "once" | "daily" | "weekdays" | "weekly" | "monthly";

export type ScheduleDraft = {
  enabled: boolean;
  preset: SchedulePreset;
  hour: number;
  minute: number;
  weekday: number; // 0=Sun .. 6=Sat
  monthDay: number; // 1..28 (or day-of-month for once)
  month: number; // 1..12 for once
};

const WEEKDAY_LABELS = ["일", "월", "화", "수", "목", "금", "토"] as const;
const SEOUL_TZ = "Asia/Seoul";

function clampInt(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.trunc(value)));
}

/** Calendar parts in Asia/Seoul for one-shot (당일) schedules. */
export function seoulCalendarParts(date: Date = new Date()): {
  month: number;
  day: number;
} {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: SEOUL_TZ,
    month: "numeric",
    day: "numeric",
  }).formatToParts(date);
  const month = Number(parts.find((part) => part.type === "month")?.value ?? 1);
  const day = Number(parts.find((part) => part.type === "day")?.value ?? 1);
  return {
    month: clampInt(month, 1, 12, 1),
    day: clampInt(day, 1, 31, 1),
  };
}

export function buildCronExpr(draft: Omit<ScheduleDraft, "enabled">): string {
  const minute = clampInt(draft.minute, 0, 59, 0);
  const hour = clampInt(draft.hour, 0, 23, 9);
  if (draft.preset === "once") {
    const today = seoulCalendarParts();
    const month = clampInt(draft.month || today.month, 1, 12, today.month);
    const day = clampInt(draft.monthDay || today.day, 1, 31, today.day);
    return `${minute} ${hour} ${day} ${month} *`.slice(0, 20);
  }
  if (draft.preset === "weekdays") {
    return `${minute} ${hour} * * 1-5`.slice(0, 20);
  }
  if (draft.preset === "weekly") {
    const weekday = clampInt(draft.weekday, 0, 6, 1);
    return `${minute} ${hour} * * ${weekday}`.slice(0, 20);
  }
  if (draft.preset === "monthly") {
    const day = clampInt(draft.monthDay, 1, 28, 1);
    return `${minute} ${hour} ${day} * *`.slice(0, 20);
  }
  return `${minute} ${hour} * * *`.slice(0, 20);
}

export function parseCronExpr(cronExpr: string | null | undefined): Omit<ScheduleDraft, "enabled"> {
  const today = seoulCalendarParts();
  const parts = (cronExpr || DEFAULT_WORKFLOW_CRON_EXPR).trim().split(/\s+/);
  const minute = clampInt(Number(parts[0] ?? 0), 0, 59, 0);
  const hour = clampInt(Number(parts[1] ?? 9), 0, 23, 9);
  const day = parts[2] ?? "*";
  const month = parts[3] ?? "*";
  const weekday = parts[4] ?? "*";

  // One-shot: specific day + month (당일 시각 1회)
  if (/^\d+$/.test(day) && /^\d+$/.test(month) && weekday === "*") {
    return {
      preset: "once",
      hour,
      minute,
      weekday: 1,
      monthDay: clampInt(Number(day), 1, 31, today.day),
      month: clampInt(Number(month), 1, 12, today.month),
    };
  }
  if (month === "*" && day !== "*" && /^\d+$/.test(day) && weekday === "*") {
    return {
      preset: "monthly",
      hour,
      minute,
      weekday: 1,
      monthDay: clampInt(Number(day), 1, 28, 1),
      month: today.month,
    };
  }
  if (month === "*" && day === "*" && weekday === "1-5") {
    return {
      preset: "weekdays",
      hour,
      minute,
      weekday: 1,
      monthDay: 1,
      month: today.month,
    };
  }
  if (month === "*" && day === "*" && /^\d+$/.test(weekday)) {
    return {
      preset: "weekly",
      hour,
      minute,
      weekday: clampInt(Number(weekday), 0, 6, 1),
      monthDay: 1,
      month: today.month,
    };
  }
  return {
    preset: "daily",
    hour,
    minute,
    weekday: 1,
    monthDay: 1,
    month: today.month,
  };
}

export function describeCronExpr(cronExpr: string | null | undefined): string {
  const draft = parseCronExpr(cronExpr);
  const time = `${String(draft.hour).padStart(2, "0")}:${String(draft.minute).padStart(2, "0")}`;
  if (draft.preset === "once") {
    return `1회 ${time}`;
  }
  if (draft.preset === "weekdays") {
    return `평일 ${time}`;
  }
  if (draft.preset === "weekly") {
    return `매주 ${WEEKDAY_LABELS[draft.weekday] ?? "?"} ${time}`;
  }
  if (draft.preset === "monthly") {
    return `매월 ${draft.monthDay}일 ${time}`;
  }
  return `매일 ${time}`;
}

type WorkflowScheduleFieldProps = {
  enabled: boolean;
  cronExpr: string;
  readOnly?: boolean;
  onChange: (next: { enabled: boolean; cronExpr: string }) => void;
};

const PRESET_OPTIONS: { value: SchedulePreset; label: string }[] = [
  { value: "once", label: "1회" },
  { value: "daily", label: "매일" },
  { value: "weekdays", label: "평일" },
  { value: "weekly", label: "매주" },
  { value: "monthly", label: "매월" },
];

export function WorkflowScheduleField({
  enabled,
  cronExpr,
  readOnly = false,
  onChange,
}: WorkflowScheduleFieldProps) {
  const draft = useMemo(() => parseCronExpr(cronExpr), [cronExpr]);

  const emit = (patch: Partial<Omit<ScheduleDraft, "enabled">> & { enabled?: boolean }) => {
    const base = { ...draft, ...patch };
    // Selecting / editing "1회" always stamps today's Seoul date into the expression.
    if ((patch.preset ?? draft.preset) === "once") {
      const today = seoulCalendarParts();
      base.month = today.month;
      base.monthDay = today.day;
      base.preset = "once";
    }
    const next = {
      ...base,
      enabled: patch.enabled ?? enabled,
    };
    onChange({
      enabled: next.enabled,
      cronExpr: buildCronExpr(next),
    });
  };

  return (
    <div className="grid gap-2 text-xs text-slate-400">
      <div className="flex items-center justify-between gap-3">
        <span>스케줄링</span>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          disabled={readOnly}
          onClick={() => emit({ enabled: !enabled })}
          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition disabled:cursor-not-allowed disabled:opacity-60 ${
            enabled
              ? "border-sky-500/80 bg-sky-700/70"
              : "border-slate-600 bg-slate-800"
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
          <div className="flex flex-wrap gap-1.5">
            {PRESET_OPTIONS.map((option) => {
              const isActive = draft.preset === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  disabled={readOnly}
                  onClick={() => emit({ preset: option.value })}
                  className={`rounded-md border px-2.5 py-1 text-[11px] font-medium disabled:opacity-60 ${
                    isActive
                      ? "border-sky-500 bg-sky-950/70 text-sky-100"
                      : "border-slate-600 bg-slate-900 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1">
              <span>시각</span>
              <div className="flex items-center gap-1.5">
                <select
                  value={draft.hour}
                  disabled={readOnly}
                  onChange={(event) => emit({ hour: Number(event.target.value) })}
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 disabled:opacity-70"
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
                >
                  {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((minute) => (
                    <option key={minute} value={minute}>
                      {String(minute).padStart(2, "0")}분
                    </option>
                  ))}
                </select>
              </div>
            </label>

            {draft.preset === "weekly" ? (
              <label className="grid gap-1">
                <span>요일</span>
                <div className="flex flex-wrap gap-1">
                  {WEEKDAY_LABELS.map((label, index) => {
                    const isActive = draft.weekday === index;
                    return (
                      <button
                        key={label}
                        type="button"
                        disabled={readOnly}
                        onClick={() => emit({ weekday: index })}
                        className={`h-7 w-7 rounded-md border text-[11px] font-medium disabled:opacity-60 ${
                          isActive
                            ? "border-sky-500 bg-sky-950/70 text-sky-100"
                            : "border-slate-600 bg-slate-900 text-slate-300 hover:bg-slate-800"
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </label>
            ) : null}

            {draft.preset === "monthly" ? (
              <label className="grid gap-1">
                <span>일자</span>
                <select
                  value={draft.monthDay}
                  disabled={readOnly}
                  onChange={(event) => emit({ monthDay: Number(event.target.value) })}
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 disabled:opacity-70"
                >
                  {Array.from({ length: 28 }, (_, index) => {
                    const day = index + 1;
                    return (
                      <option key={day} value={day}>
                        {day}일
                      </option>
                    );
                  })}
                </select>
              </label>
            ) : null}
          </div>

          <p className="mt-3 text-[11px] text-slate-300">
            {draft.preset === "once" ? (
              <>
                당일 {String(draft.hour).padStart(2, "0")}:
                {String(draft.minute).padStart(2, "0")} 1회
              </>
            ) : (
              describeCronExpr(buildCronExpr({ ...draft }))
            )}
            <span className="ml-2 text-slate-500">({buildCronExpr(draft)})</span>
          </p>
        </div>
      ) : null}
    </div>
  );
}
