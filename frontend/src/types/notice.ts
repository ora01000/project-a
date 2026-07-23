import { dateOnlyAfterDays, todayDateOnly } from "../utils/datetime";

export interface NoticeRecord {
  idx: number;
  writer: string;
  writer_name?: string | null;
  write_date: string;
  from_date: string;
  until_date: string;
  title: string;
  notice: string;
  welcome_popup: boolean;
}

export interface NoticeFormValues {
  writer: string;
  from_date: string;
  until_date: string;
  title: string;
  notice: string;
  welcome_popup: boolean;
}


export function emptyNoticeForm(writer: string): NoticeFormValues {
  const fromDate = todayDateOnly();
  const untilDate = dateOnlyAfterDays(7);
  return {
    writer,
    from_date: `${fromDate} 00:00:00`,
    until_date: `${untilDate} 00:00:00`,
    title: "",
    notice: "",
    welcome_popup: false,
  };
}

export function splitNoticeDateTime(value: string): { date: string; time: string } {
  const normalized = (value || "").trim().replace("T", " ");
  if (!normalized) {
    return { date: todayDateOnly(), time: "00:00:00" };
  }
  const [datePart, timePart = "00:00:00"] = normalized.split(/\s+/);
  let time = timePart.trim();
  if (/^\d{2}:\d{2}$/.test(time)) {
    time = `${time}:00`;
  }
  if (!/^\d{2}:\d{2}:\d{2}$/.test(time)) {
    time = "00:00:00";
  }
  return {
    date: datePart.slice(0, 10),
    time,
  };
}

export function joinNoticeDateTime(date: string, time: string): string {
  let nextTime = (time || "").trim() || "00:00:00";
  if (/^\d{2}:\d{2}$/.test(nextTime)) {
    nextTime = `${nextTime}:00`;
  }
  if (!/^\d{2}:\d{2}:\d{2}$/.test(nextTime)) {
    nextTime = "00:00:00";
  }
  return `${date.slice(0, 10)} ${nextTime}`;
}

export type NoticeScheduleStatus = "scheduled" | "active" | "expired";

function parseNoticeDateTime(value: string): number | null {
  const { date, time } = splitNoticeDateTime(value);
  const parsed = Date.parse(`${date}T${time}`);
  return Number.isNaN(parsed) ? null : parsed;
}

/** Compare notice period against now: before from -> scheduled, after until -> expired. */
export function noticeScheduleStatus(
  notice: Pick<NoticeRecord, "from_date" | "until_date">,
  now = Date.now(),
): NoticeScheduleStatus {
  const fromMs = parseNoticeDateTime(notice.from_date);
  const untilMs = parseNoticeDateTime(notice.until_date);
  if (fromMs != null && now < fromMs) {
    return "scheduled";
  }
  if (untilMs != null && now > untilMs) {
    return "expired";
  }
  return "active";
}
