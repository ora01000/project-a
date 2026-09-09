import {
  Children,
  cloneElement,
  isValidElement,
  useMemo,
  type ReactNode,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

export const TEMPLATE_VARIABLE_TOKEN = /\{([^{}\n]+)\}/g;

/** Unique variable names in first-appearance order. */
export function extractTemplateVariableNames(content: string): string[] {
  const names: string[] = [];
  const seen = new Set<string>();
  for (const match of content.matchAll(TEMPLATE_VARIABLE_TOKEN)) {
    const name = match[1]?.trim() ?? "";
    if (!name || seen.has(name)) {
      continue;
    }
    seen.add(name);
    names.push(name);
  }
  return names;
}

/** Replace `{name}` tokens with values (unmatched tokens left as-is). */
export function applyTemplateVariables(
  content: string,
  values: Record<string, string>,
): string {
  return content.replace(TEMPLATE_VARIABLE_TOKEN, (token, name: string) => {
    const key = name.trim();
    if (!(key in values)) {
      return token;
    }
    return values[key] ?? "";
  });
}

const VARIABLE_PATTERN = /(\{[^{}\n]+\})/g;

function highlightTemplateVariables(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === "string") {
      const parts = child.split(VARIABLE_PATTERN);
      if (parts.length === 1) {
        return child;
      }
      return parts.map((part, index) => {
        if (/^\{[^{}\n]+\}$/.test(part)) {
          return (
            <strong
              key={`var-${index}-${part}`}
              className="rounded px-1 font-bold text-white"
              style={{ backgroundColor: "#dc2626" }}
            >
              {part}
            </strong>
          );
        }
        return part;
      });
    }
    if (isValidElement<{ children?: ReactNode }>(child) && child.props.children != null) {
      return cloneElement(child, {
        ...child.props,
        children: highlightTemplateVariables(child.props.children),
      });
    }
    return child;
  });
}

const TEMPLATE_MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => (
    <p className="my-1 leading-5 text-slate-200">{highlightTemplateVariables(children)}</p>
  ),
  h1: ({ children }) => (
    <h1 className="mb-1 mt-2 text-sm font-bold text-slate-50 first:mt-0">
      {highlightTemplateVariables(children)}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-1 mt-2 text-[13px] font-bold text-slate-50 first:mt-0">
      {highlightTemplateVariables(children)}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1 mt-1.5 text-xs font-semibold text-slate-100 first:mt-0">
      {highlightTemplateVariables(children)}
    </h3>
  ),
  ul: ({ children }) => <ul className="my-1 list-disc space-y-0.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 list-decimal space-y-0.5 pl-5">{children}</ol>,
  li: ({ children }) => (
    <li className="leading-5 text-slate-200">{highlightTemplateVariables(children)}</li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-50">{highlightTemplateVariables(children)}</strong>
  ),
  em: ({ children }) => <em>{highlightTemplateVariables(children)}</em>,
  code: ({ children }) => (
    <code className="rounded bg-slate-900 px-1 py-0.5 text-[11px] text-sky-200">
      {children}
    </code>
  ),
};

interface WorkflowTemplateMarkdownProps {
  content: string;
  className?: string;
}

export function WorkflowTemplateMarkdown({ content, className }: WorkflowTemplateMarkdownProps) {
  const normalized = useMemo(() => content.replace(/\n{3,}/g, "\n\n"), [content]);

  if (!normalized.trim()) {
    return (
      <div className={className}>
        <p className="text-xs text-slate-500">양식을 선택하세요.</p>
      </div>
    );
  }

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={TEMPLATE_MARKDOWN_COMPONENTS}>
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
