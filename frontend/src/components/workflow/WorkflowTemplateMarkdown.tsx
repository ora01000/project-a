import {
  Children,
  cloneElement,
  isValidElement,
  useEffect,
  useMemo,
  useRef,
  useState,
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
  emptyLabel?: string;
}

export function WorkflowTemplateMarkdown({
  content,
  className,
  emptyLabel = "양식을 선택하세요.",
}: WorkflowTemplateMarkdownProps) {
  const normalized = useMemo(() => content.replace(/\n{3,}/g, "\n\n"), [content]);

  if (!normalized.trim()) {
    return (
      <div className={className}>
        <p className="text-xs text-slate-500">{emptyLabel}</p>
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

const PROMPT_FIELD_BOX =
  "min-h-[9rem] w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-xs disabled:opacity-80";

interface WorkflowTemplatePromptFieldProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  /** Start in edit mode (e.g. clarify answer flow). */
  defaultEditing?: boolean;
  /** Force edit mode while true (resets when becoming false). */
  forceEditing?: boolean;
  placeholder?: string;
  rows?: number;
  "aria-label"?: string;
}

/** Single box: markdown preview with `{}` highlights, click to edit source text. */
export function WorkflowTemplatePromptField({
  value,
  onChange,
  disabled = false,
  defaultEditing = false,
  forceEditing = false,
  placeholder = "양식을 선택하거나 클릭하여 편집하세요",
  rows = 8,
  "aria-label": ariaLabel = "다이어그램 생성 프롬프트",
}: WorkflowTemplatePromptFieldProps) {
  const [isEditing, setIsEditing] = useState(defaultEditing || forceEditing);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (disabled) {
      setIsEditing(false);
      return;
    }
    if (forceEditing) {
      setIsEditing(true);
    }
  }, [disabled, forceEditing]);

  useEffect(() => {
    if (!isEditing || disabled) {
      return;
    }
    const node = textareaRef.current;
    if (!node) {
      return;
    }
    const focusId = window.requestAnimationFrame(() => {
      node.focus();
      const cursor = node.value.length;
      node.setSelectionRange(cursor, cursor);
      node.scrollTop = node.scrollHeight;
    });
    return () => window.cancelAnimationFrame(focusId);
  }, [isEditing, disabled, forceEditing]);

  if (disabled || !isEditing) {
    return (
      <div
        role={disabled ? undefined : "button"}
        tabIndex={disabled ? -1 : 0}
        onClick={() => {
          if (!disabled) {
            setIsEditing(true);
          }
        }}
        onKeyDown={(event) => {
          if (disabled) {
            return;
          }
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setIsEditing(true);
          }
        }}
        className={`${PROMPT_FIELD_BOX} max-h-64 overflow-y-auto ${
          disabled ? "cursor-default opacity-80" : "cursor-text hover:border-slate-500"
        }`}
        title={disabled ? undefined : "클릭하여 편집"}
        aria-label={ariaLabel}
      >
        <WorkflowTemplateMarkdown content={value} emptyLabel={placeholder} />
        {!disabled ? (
          <p className="mt-2 text-[10px] text-slate-500">클릭하여 편집 · 포커스 해제 시 미리보기</p>
        ) : null}
      </div>
    );
  }

  return (
    <textarea
      ref={textareaRef}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={() => {
        if (!forceEditing) {
          setIsEditing(false);
        }
      }}
      rows={rows}
      spellCheck={false}
      placeholder={placeholder}
      className={`${PROMPT_FIELD_BOX} max-h-64 resize-y font-mono text-[12px] leading-5 text-slate-200`}
      aria-label={ariaLabel}
    />
  );
}
