import type { ReactNode } from "react";

const LABEL_CLASS = "shrink-0 text-[13px] font-bold text-slate-200 underline decoration-slate-500 underline-offset-2";

interface JobFieldLabelProps {
  children: ReactNode;
  bullet?: string;
  className?: string;
}

export function JobFieldLabel({ children, bullet = "📌", className = "" }: JobFieldLabelProps) {
  return (
    <span className={`${LABEL_CLASS} ${className}`.trim()}>
      {bullet} {children}
    </span>
  );
}

interface JobInlineFieldProps {
  label: string;
  children: ReactNode;
  bullet?: string;
  className?: string;
  valueClassName?: string;
}

/** 레이블 오른쪽에 내용을 붙여 표시 (처리 결과 제외 대부분 필드) */
export function JobInlineField({
  label,
  children,
  bullet,
  className = "",
  valueClassName = "text-sm text-slate-200",
}: JobInlineFieldProps) {
  return (
    <div className={`flex items-baseline gap-2 ${className}`.trim()}>
      <JobFieldLabel bullet={bullet}>{label}</JobFieldLabel>
      <div className={`min-w-0 flex-1 ${valueClassName}`.trim()}>{children}</div>
    </div>
  );
}

interface JobBlockFieldProps {
  label: string;
  children: ReactNode;
  bullet?: string;
  className?: string;
  headerExtra?: ReactNode;
}

/** 레이블 아래에 내용을 표시 (처리 결과 등) */
export function JobBlockField({
  label,
  children,
  bullet,
  className = "",
  headerExtra,
}: JobBlockFieldProps) {
  return (
    <div className={className}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <JobFieldLabel bullet={bullet}>{label}</JobFieldLabel>
        {headerExtra}
      </div>
      <div className="mt-2">{children}</div>
    </div>
  );
}
