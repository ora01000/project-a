import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ReleaseNotesModalProps {
  onClose: () => void;
}

export function ReleaseNotesModal({ onClose }: ReleaseNotesModalProps) {
  const [content, setContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/release-notes");
        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(payload?.detail ?? "변경이력을 불러오지 못했습니다.");
        }
        const data = (await response.json()) as { content: string };
        if (!cancelled) {
          setContent(data.content ?? "");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "변경이력을 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-notes-title"
        className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id="release-notes-title" className="text-lg font-semibold text-slate-100">
            변경이력
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        {isLoading ? <p className="mt-4 text-sm text-slate-400">불러오는 중…</p> : null}
        {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}

        {!isLoading && !error ? (
          <div className="markdown-body mt-4 min-h-0 flex-1 overflow-y-auto rounded-md border border-slate-800 bg-slate-950/40 p-4 text-sm leading-relaxed text-slate-100">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => (
                  <h1 className="mb-3 text-xl font-bold text-slate-50">{children}</h1>
                ),
                h2: ({ children }) => (
                  <h2 className="mb-2 mt-6 border-b border-slate-800 pb-1 text-lg font-semibold text-slate-50">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="mb-1.5 mt-4 text-base font-semibold text-slate-100">{children}</h3>
                ),
                p: ({ children }) => <p className="mb-2 text-slate-200">{children}</p>,
                ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>,
                ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>,
                li: ({ children }) => <li className="text-slate-200">{children}</li>,
                hr: () => <hr className="my-4 border-slate-700" />,
                strong: ({ children }) => <strong className="font-semibold text-slate-50">{children}</strong>,
                code: ({ className, children }) =>
                  className ? (
                    <code className="block overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-200">
                      {children}
                    </code>
                  ) : (
                    <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs text-sky-200">
                      {children}
                    </code>
                  ),
                table: ({ children }) => (
                  <div className="my-3 overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-xs">{children}</table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-slate-700 bg-slate-800 px-2 py-1.5 font-medium text-slate-200">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border border-slate-800 px-2 py-1.5 text-slate-300">{children}</td>
                ),
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sky-300 underline-offset-2 hover:underline"
                  >
                    {children}
                  </a>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        ) : null}
      </div>
    </div>
  );
}
