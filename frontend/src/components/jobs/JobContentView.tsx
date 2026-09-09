import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { JOB_TYPE_WORKFLOW } from "../../types/job";
import { hasMarkdownSyntax } from "../../utils/markdown";

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="mb-2 text-base font-bold text-slate-50">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-1.5 mt-3 text-sm font-semibold text-slate-50">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-semibold text-slate-100">{children}</h3>,
  p: ({ children }) => <p className="mb-1.5 text-slate-200">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-5 text-slate-200">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-0.5 pl-5 text-slate-200">{children}</ol>,
  li: ({ children }) => <li className="text-slate-200">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-slate-50">{children}</strong>,
  code: ({ className, children }) =>
    className ? (
      <code className="block overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-100">
        {children}
      </code>
    ) : (
      <code className="rounded bg-slate-950 px-1 py-0.5 font-mono text-xs text-sky-200">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="mb-2 overflow-x-auto rounded bg-slate-950 p-2 text-slate-100">{children}</pre>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-slate-600 pl-3 text-slate-300">{children}</blockquote>
  ),
  a: ({ href, children }) => (
    <a href={href} className="text-sky-300 underline" target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-slate-700 px-2 py-1 text-left font-semibold text-slate-100">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-700 px-2 py-1 align-top text-slate-200">{children}</td>
  ),
};

function looksLikeHtml(content: string): boolean {
  return /<\/?[a-z][\s\S]*>/i.test(content);
}

function shouldRenderMarkdown(content: string, jobType?: number): boolean {
  if (jobType === JOB_TYPE_WORKFLOW) {
    return true;
  }
  if (looksLikeHtml(content)) {
    return false;
  }
  return hasMarkdownSyntax(content);
}

interface JobContentViewProps {
  content: string;
  jobType?: number;
  className?: string;
}

export function JobContentView({
  content,
  jobType,
  className = "job-content-html rounded-md border border-slate-700 bg-slate-950/60 p-3 text-sm text-slate-200",
}: JobContentViewProps) {
  const trimmed = (content || "").trim();
  if (!trimmed) {
    return <div className={className} />;
  }

  if (shouldRenderMarkdown(trimmed, jobType)) {
    return (
      <div className={className}>
        <div className="markdown-body space-y-1.5 leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {trimmed}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  if (looksLikeHtml(trimmed)) {
    return <div className={className} dangerouslySetInnerHTML={{ __html: trimmed }} />;
  }

  return (
    <div className={className}>
      <span className="whitespace-pre-wrap">{trimmed}</span>
    </div>
  );
}
