import { isValidElement, lazy, memo, Suspense, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

import { parseFossflowCompactJson } from "../types/fossflow";
import type { FossflowCompactDiagram } from "../types/fossflow";
import { embedFossflowJsonFences, parseEmbeddedFossflowJson } from "../utils/fossflowExtract";
import { hasMarkdownSyntax } from "../utils/markdown";
import { D2Diagram } from "./D2Diagram";
import { MermaidDiagram } from "./MermaidDiagram";

const FossFlowDiagram = lazy(() =>
  import("./FossFlowDiagram").then((module) => ({ default: module.FossFlowDiagram })),
);

function FossFlowDiagramPreview({ diagram }: { diagram: FossflowCompactDiagram | string }) {
  return (
    <Suspense fallback={<p className="text-xs text-slate-400">다이어그램을 불러오는 중...</p>}>
      <div className="my-2 flex h-[28rem] min-h-[16rem] w-full flex-col">
        <FossFlowDiagram diagram={diagram} />
      </div>
    </Suspense>
  );
}

interface AssistantMessageContentProps {
  content: string;
}

/** Collapse 3+ consecutive newlines to a single blank line (display only). */
function normalizeExcessiveNewlines(content: string): string {
  return content.replace(/\n{3,}/g, "\n\n");
}

function isDiagramElement(child: unknown): boolean {
  return (
    isValidElement(child) &&
    (child.type === MermaidDiagram || child.type === D2Diagram || child.type === FossFlowDiagramPreview)
  );
}

const MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => <p>{children}</p>,
  h1: ({ children }) => <h1 className="text-lg font-bold text-slate-50">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-bold text-slate-50">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold text-slate-50">{children}</h3>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  code: ({ className, children }) => {
    const language = /language-(\w+)/.exec(className || "")?.[1];
    const text = String(children).replace(/\n$/, "");

    if (language === "mermaid") {
      return <MermaidDiagram chart={text} />;
    }

    if (language === "d2") {
      return <D2Diagram chart={text} />;
    }

    const compact = parseFossflowCompactJson(text);
    if (compact) {
      return <FossFlowDiagramPreview diagram={compact} />;
    }
    if (language === "fossflow" || language === "isoflow") {
      return <p className="text-xs text-amber-300">FossFLOW compact JSON을 해석하지 못했습니다.</p>;
    }

    if (className) {
      return (
        <code className={`block overflow-x-auto rounded bg-slate-950 p-2 text-xs ${className}`}>
          {children}
        </code>
      );
    }

    return (
      <code className="rounded bg-slate-950 px-1 py-0.5 text-xs text-sky-200">{children}</code>
    );
  },
  pre: ({ children }) => {
    if (isDiagramElement(children)) {
      return <div className="my-2">{children}</div>;
    }
    return <pre className="overflow-x-auto rounded bg-slate-950 p-2">{children}</pre>;
  },
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
};

function AssistantMessageContentInner({ content }: AssistantMessageContentProps) {
  const displayContent = useMemo(() => {
    const normalized = normalizeExcessiveNewlines(content);
    return embedFossflowJsonFences(normalized);
  }, [content]);

  if (!content) {
    return null;
  }

  const compactMessage = parseEmbeddedFossflowJson(content);
  if (compactMessage) {
    return <FossFlowDiagramPreview diagram={compactMessage} />;
  }

  if (!hasMarkdownSyntax(displayContent)) {
    return <span className="whitespace-pre-wrap">{displayContent}</span>;
  }

  return (
    <div className="markdown-body space-y-1.5 text-sm leading-relaxed text-slate-100">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
        {displayContent}
      </ReactMarkdown>
    </div>
  );
}

export const AssistantMessageContent = memo(AssistantMessageContentInner);
