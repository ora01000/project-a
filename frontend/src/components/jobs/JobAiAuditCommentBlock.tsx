import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { hasMarkdownSyntax } from "../../utils/markdown";
import { JobBlockField } from "./JobFieldLabel";

const markdownComponents = {
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="mb-2 text-base font-bold text-violet-50">{children}</h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mb-1.5 mt-3 text-sm font-semibold text-violet-50">{children}</h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mb-1 mt-2 text-sm font-semibold text-violet-100">{children}</h3>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-1.5 text-violet-100">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="mb-2 list-disc space-y-0.5 pl-5">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="mb-2 list-decimal space-y-0.5 pl-5">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="text-violet-100">{children}</li>
  ),
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-violet-50">{children}</strong>
  ),
  code: ({ className, children }: { className?: string; children?: ReactNode }) =>
    className ? (
      <code className="block overflow-x-auto rounded bg-violet-950/50 p-2 text-xs text-violet-100">
        {children}
      </code>
    ) : (
      <code className="rounded bg-violet-950/40 px-1 py-0.5 font-mono text-xs text-violet-200">
        {children}
      </code>
    ),
  pre: ({ children }: { children?: ReactNode }) => (
    <pre className="overflow-x-auto rounded bg-violet-950/50 p-2 text-violet-100">{children}</pre>
  ),
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="border-l-4 border-violet-700/60 pl-3 text-violet-200">{children}</blockquote>
  ),
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a href={href} className="text-violet-300 underline" target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
  table: ({ children }: { children?: ReactNode }) => (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: ReactNode }) => (
    <th className="border border-violet-800/50 px-2 py-1 text-left font-semibold text-violet-100">
      {children}
    </th>
  ),
  td: ({ children }: { children?: ReactNode }) => (
    <td className="border border-violet-800/50 px-2 py-1 align-top text-violet-100">{children}</td>
  ),
};

function JobAiAuditCommentContent({ content }: { content: string }) {
  const trimmed = content.trim();
  if (!trimmed) {
    return null;
  }

  if (!hasMarkdownSyntax(trimmed)) {
    return <span className="whitespace-pre-wrap text-violet-100">{trimmed}</span>;
  }

  return (
    <div className="markdown-body space-y-1.5 leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {trimmed}
      </ReactMarkdown>
    </div>
  );
}

function formatAuditDate(value: string): string {
  return value.trim().replace("T", " ");
}

interface JobAiAuditCommentBlockProps {
  comment: string | null | undefined;
  auditCount?: number;
  auditDate?: string | null;
  noteNamePrefix?: string;
  onCopyToNote?: (content: string, noteName?: string) => Promise<void>;
}

export function JobAiAuditCommentBlock({
  comment,
  auditCount = 0,
  auditDate,
  noteNamePrefix,
  onCopyToNote,
}: JobAiAuditCommentBlockProps) {
  const [isCopyingToNote, setIsCopyingToNote] = useState(false);

  if (!comment?.trim()) {
    return null;
  }

  const showMeta = auditCount > 0 || Boolean(auditDate?.trim());
  const trimmedComment = comment.trim();

  const handleCopyToNote = async () => {
    if (!onCopyToNote) {
      return;
    }

    setIsCopyingToNote(true);
    try {
      const prefix = noteNamePrefix?.trim() || "AI 검토";
      const suffix = auditCount > 0 ? ` AI검토 ${auditCount}차` : " AI검토";
      const noteName = `${prefix}${suffix}`.slice(0, 50);
      await onCopyToNote(trimmedComment, noteName);
    } finally {
      setIsCopyingToNote(false);
    }
  };

  return (
    <JobBlockField
      label="AI 검토결과"
      bullet="🤖"
      headerExtra={
        onCopyToNote ? (
          <button
            type="button"
            disabled={isCopyingToNote}
            onClick={() => void handleCopyToNote()}
            className="shrink-0 rounded-md border border-violet-700/80 bg-violet-950/50 px-2 py-1 text-[10px] font-medium text-violet-100 hover:bg-violet-900/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isCopyingToNote ? "복사 중..." : "나의 노트로 복사"}
          </button>
        ) : null
      }
    >
      <div className="rounded-md border border-violet-800/60 bg-violet-950/30 p-3 text-sm text-violet-100">
        {showMeta ? (
          <p className="mb-2 text-xs text-violet-300/90">
            {auditCount > 0 ? `${auditCount}차 검토` : "AI 검토"}
            {auditDate?.trim() ? ` · ${formatAuditDate(auditDate)}` : null}
          </p>
        ) : null}
        <JobAiAuditCommentContent content={comment} />
      </div>
    </JobBlockField>
  );
}
