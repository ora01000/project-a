export const DISPLAY_TIMEZONE = "Asia/Seoul";

type DateTimeParts = {
  year: string;
  month: string;
  day: string;
  hour: string;
  minute: string;
  second: string;
};

function getDateTimeParts(date: Date, timeZone = DISPLAY_TIMEZONE): DateTimeParts {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(
    formatter.formatToParts(date).map(({ type, value }) => [type, value]),
  ) as Record<string, string>;
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour,
    minute: parts.minute,
    second: parts.second,
  };
}

function getDateParts(date: Date, timeZone = DISPLAY_TIMEZONE): { year: string; month: string; day: string } {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const parts = Object.fromEntries(
    formatter.formatToParts(date).map(({ type, value }) => [type, value]),
  ) as Record<string, string>;
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
  };
}

export function formatResponseTimestamp(date: Date): string {
  const { year, month, day, hour, minute, second } = getDateTimeParts(date);
  return `${year}년 ${month}월 ${day}일 ${hour}:${minute}:${second}`;
}

export function formatMessageIndex(num: number, date: Date): string {
  return `${formatResponseTimestamp(date)}-#${num}`;
}

export function formatCurrentTime(date: Date): string {
  return formatResponseTimestamp(date);
}

export function formatLocaleDateTime(
  date: Date,
  options?: Intl.DateTimeFormatOptions,
): string {
  return date.toLocaleString("ko-KR", {
    timeZone: DISPLAY_TIMEZONE,
    ...options,
  });
}

export function formatJobDatetime(date: Date): string {
  const { month, day, hour, minute, second } = getDateTimeParts(date);
  const { year } = getDateParts(date);
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

export function toDatetimeLocalValue(date: Date): string {
  const { month, day, hour, minute } = getDateTimeParts(date);
  const { year } = getDateParts(date);
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

export function todayDateOnly(): string {
  const { year, month, day } = getDateParts(new Date());
  return `${year}-${month}-${day}`;
}

export function dateOnlyAfterDays(days: number, base = new Date()): string {
  const { year, month, day } = getDateParts(base);
  const shifted = new Date(`${year}-${month}-${day}T12:00:00+09:00`);
  shifted.setDate(shifted.getDate() + days);
  const next = getDateParts(shifted);
  return `${next.year}-${next.month}-${next.day}`;
}
