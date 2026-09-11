import { useEffect, useState } from "react";

import { JOB_TYPE_WORKFLOW } from "../../types/job";
import { JobContentView } from "../jobs/JobContentView";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

/** Idle-state guide: renders ``docs/workflow_front/workflow_front.md``. */
export function WorkflowFrontGuidePanel() {
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/workflow-front");
        if (!response.ok) {
          throw new Error(await parseError(response, "안내 문서를 불러오지 못했습니다."));
        }
        const payload = (await response.json()) as { content?: string };
        if (!cancelled) {
          setContent(payload.content || "");
        }
      } catch (err) {
        if (!cancelled) {
          setContent("");
          setError(err instanceof Error ? err.message : "안내 문서를 불러오지 못했습니다.");
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
    <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner">
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">안내 문서를 불러오는 중…</p>
        ) : null}
        {error ? <p className="text-sm text-rose-300">{error}</p> : null}
        {!isLoading && !error ? (
          content ? (
            <JobContentView
              content={content}
              jobType={JOB_TYPE_WORKFLOW}
              className="rounded-md border border-slate-700/80 bg-slate-950/50 p-4 text-sm text-slate-200"
            />
          ) : (
            <p className="text-sm text-slate-500">
              작업 워크플로우를 선택하거나 새로 만드세요.
            </p>
          )
        ) : null}
      </div>
    </section>
  );
}
