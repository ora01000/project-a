import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { NoticeFormValues, NoticeRecord } from "../../types/notice";
import {
  emptyNoticeForm,
  joinNoticeDateTime,
  splitNoticeDateTime,
} from "../../types/notice";

interface NoticeFormModalProps {
  mode: "create" | "edit";
  notice?: NoticeRecord;
  writerUserid: string;
  writerUsername: string;
  onClose: () => void;
  onSave: (values: NoticeFormValues) => Promise<void>;
}

const markdownComponents = {
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="mb-3 text-xl font-bold text-slate-50">{children}</h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mb-2 mt-4 border-b border-slate-800 pb-1 text-lg font-semibold text-slate-50">
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mb-1.5 mt-3 text-base font-semibold text-slate-100">{children}</h3>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-2 text-slate-200">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="text-slate-200">{children}</li>
  ),
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-slate-50">{children}</strong>
  ),
  code: ({ className, children }: { className?: string; children?: ReactNode }) =>
    className ? (
      <code className="block overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-200">
        {children}
      </code>
    ) : (
      <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs text-sky-200">
        {children}
      </code>
    ),
};

export function NoticeFormModal({
  mode,
  notice,
  writerUserid,
  writerUsername,
  onClose,
  onSave,
}: NoticeFormModalProps) {
  const [values, setValues] = useState<NoticeFormValues>(() => emptyNoticeForm(writerUserid));
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (mode === "edit" && notice) {
      setValues({
        writer: notice.writer,
        from_date: notice.from_date,
        until_date: notice.until_date,
        title: notice.title,
        notice: notice.notice,
        welcome_popup: notice.welcome_popup,
      });
      return;
    }
    setValues(emptyNoticeForm(writerUserid));
  }, [mode, notice, writerUserid]);

  const displayWriterName =
    mode === "edit" && notice
      ? notice.writer_name?.trim() || notice.writer
      : writerUsername;

  const fromParts = splitNoticeDateTime(values.from_date);
  const untilParts = splitNoticeDateTime(values.until_date);

  const updateField = <K extends keyof NoticeFormValues>(key: K, value: NoticeFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!values.title.trim() || !values.from_date.trim() || !values.until_date.trim()) {
      setError("제목, 공지시작, 공지기한을 입력해 주세요.");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await onSave({
        ...values,
        writer: mode === "create" ? writerUserid : values.writer,
        from_date: joinNoticeDateTime(fromParts.date, fromParts.time),
        until_date: joinNoticeDateTime(untilParts.date, untilParts.time),
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-slate-100">
          {mode === "create" ? "공지사항 추가" : "공지사항 수정"}
        </h2>

        <form onSubmit={(event) => void handleSubmit(event)} className="mt-4 space-y-3">
          <label className="block space-y-1 text-sm text-slate-300">
            <span>제목</span>
            <input
              value={values.title}
              onChange={(event) => updateField("title", event.target.value)}
              disabled={isSaving}
              maxLength={100}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm text-slate-300">
            <span>작성자</span>
            <input
              value={displayWriterName}
              disabled
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-500"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1 text-sm text-slate-300">
              <span>공지시작</span>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="date"
                  value={fromParts.date}
                  onChange={(event) =>
                    updateField("from_date", joinNoticeDateTime(event.target.value, fromParts.time))
                  }
                  disabled={isSaving}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
                <input
                  type="time"
                  step={1}
                  value={fromParts.time}
                  onChange={(event) =>
                    updateField("from_date", joinNoticeDateTime(fromParts.date, event.target.value))
                  }
                  disabled={isSaving}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-slate-100 outline-none focus:border-sky-500"
                />
              </div>
            </div>
            <div className="space-y-1 text-sm text-slate-300">
              <span>공지기한</span>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="date"
                  value={untilParts.date}
                  onChange={(event) =>
                    updateField(
                      "until_date",
                      joinNoticeDateTime(event.target.value, untilParts.time),
                    )
                  }
                  disabled={isSaving}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
                <input
                  type="time"
                  step={1}
                  value={untilParts.time}
                  onChange={(event) =>
                    updateField(
                      "until_date",
                      joinNoticeDateTime(untilParts.date, event.target.value),
                    )
                  }
                  disabled={isSaving}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-slate-100 outline-none focus:border-sky-500"
                />
              </div>
            </div>
          </div>

          <div className="space-y-2 text-sm text-slate-300">
            <span>공지 내용 (Markdown)</span>
            <textarea
              value={values.notice}
              onChange={(event) => updateField("notice", event.target.value)}
              disabled={isSaving}
              placeholder={"# 제목\n\n**강조** 와 목록을 사용할 수 있습니다."}
              className="min-h-[140px] w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-sky-500"
            />
            <div className="rounded-md border border-slate-800 bg-slate-950/50 p-3">
              <p className="mb-2 text-xs text-slate-500">미리보기</p>
              <div className="markdown-body min-h-[80px] text-sm leading-relaxed text-slate-100">
                {values.notice.trim() ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {values.notice}
                  </ReactMarkdown>
                ) : (
                  <p className="text-slate-500">내용을 입력하면 여기에 표시됩니다.</p>
                )}
              </div>
            </div>
          </div>

          <label className="flex items-center gap-3 text-sm text-slate-300">
            <span>웰컴백 팝업 표시</span>
            <button
              type="button"
              role="switch"
              aria-checked={values.welcome_popup}
              disabled={isSaving}
              onClick={() => updateField("welcome_popup", !values.welcome_popup)}
              className={`relative h-6 w-11 rounded-full transition ${
                values.welcome_popup ? "bg-sky-500" : "bg-slate-700"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition ${
                  values.welcome_popup ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </label>

          {error ? (
            <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
              {error}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSaving}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              닫기
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:bg-slate-700"
            >
              {isSaving ? "저장 중..." : "저장"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
