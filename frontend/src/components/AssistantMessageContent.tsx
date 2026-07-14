import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { hasMarkdownSyntax } from "../utils/markdown";

interface AssistantMessageContentProps {
  content: string;
}

/** Collapse 3+ consecutive newlines to a single blank line (display only). */
function normalizeExcessiveNewlines(content: string): string {
  return content.replace(/\n{3,}/g, "\n\n");
}

export function AssistantMessageContent({ content }: AssistantMessageContentProps) {
  if (!content) {
    return null;
  }

  const displayContent = normalizeExcessiveNewlines(content);

  if (!hasMarkdownSyntax(displayContent)) {
    return <span className="whitespace-pre-wrap">{displayContent}</span>;
  }

  return (
    <div className="markdown-body space-y-1.5 text-sm leading-relaxed text-slate-100">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{children}</p>,
          h1: ({ children }) => <h1 className="text-lg font-bold text-slate-50">{children}</h1>,
          h2: ({ children }) => <h2 className="text-base font-bold text-slate-50">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold text-slate-50">{children}</h3>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          code: ({ className, children }) =>
            className ? (
              <code className={`block overflow-x-auto rounded bg-slate-950 p-2 text-xs ${className}`}>
                {children}
              </code>
            ) : (
              <code className="rounded bg-slate-950 px-1 py-0.5 text-xs text-sky-200">{children}</code>
            ),
          pre: ({ children }) => <pre className="overflow-x-auto rounded bg-slate-950 p-2">{children}</pre>,
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-slate-950">{children}</thead>,
          th: ({ children }) => (
            <th className="border border-slate-700 px-2 py-1 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border border-slate-700 px-2 py-1 align-top">{children}</td>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-slate-600 pl-3 text-slate-300">{children}</blockquote>
          ),
          a: ({ href, children }) => (
            <a href={href} className="text-sky-300 underline" target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          strong: ({ children }) => <strong className="font-semibold text-slate-50">{children}</strong>,
        }}
      >
        {displayContent}
      </ReactMarkdown>
    </div>
  );
}
