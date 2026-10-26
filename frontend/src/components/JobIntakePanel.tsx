import { useState } from "react";

import type { AuthUser } from "../types/auth";
import { ConfirmDialog } from "./ConfirmDialog";
import { InfraDictionaryPanel } from "./jobs/InfraDictionaryPanel";
import { JobFieldLabel } from "./jobs/JobFieldLabel";
import { requestJobWorkflowRefresh } from "../utils/jobWorkflowRefresh";

interface JobIntakeResponse {
  idx: number;
  srnum: string;
  status_code: number;
  received_at: string;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function buildManualMessageId(userid: string): string {
  return `chat-${userid}-${Date.now()}`;
}

const ACTION_BUTTON_BASE =
  "rounded-md px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50";

const CHIP =
  "rounded-md border border-slate-600 bg-slate-900 px-2 py-1 text-[11px] text-slate-200 hover:border-sky-500 hover:text-sky-200 disabled:cursor-not-allowed disabled:opacity-50";
const CHIP_ACTIVE = "border-sky-500 text-sky-200";

const JOB_KIND_OPTIONS = ["정보 조회", "상태 및 성능 조회", "수평 확장", "수직 확장"] as const;

type JobKind = (typeof JOB_KIND_OPTIONS)[number];

function buildHelperMessage(infraContext: string, jobKind: JobKind): string {
  const infra = infraContext.trim();
  const kindToken = `작업종류=${jobKind}`;
  return infra ? `${infra} | ${kindToken}` : kindToken;
}

interface JobIntakePanelProps {
  user: AuthUser;
}

export function JobIntakePanel({ user }: JobIntakePanelProps) {
  const [jobTitle, setJobTitle] = useState("");
  const [jobContent, setJobContent] = useState("");
  const [infraContext, setInfraContext] = useState("");
  const [selectedJobKind, setSelectedJobKind] = useState<JobKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isHelping, setIsHelping] = useState(false);
  const [confirmSubmitOpen, setConfirmSubmitOpen] = useState(false);
  const [confirmResetOpen, setConfirmResetOpen] = useState(false);

  const submitJobIntake = async () => {
    const trimmedTitle = jobTitle.trim();
    const trimmedContent = jobContent.trim();
    if (!trimmedTitle || !trimmedContent) {
      setError("작업 제목과 작업 내용을 입력해 주세요.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_title: trimmedTitle,
          job_content: trimmedContent,
          requester_name: user.username,
          requester_email: user.email,
          requester_depart: user.depart,
          request_date: new Date().toISOString(),
          madang_id: user.userid,
          team_id: "manual",
          channel_id: "integrated-chat",
          message_id: buildManualMessageId(user.userid),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 접수에 실패했습니다."));
      }
      const data = (await response.json()) as JobIntakeResponse;
      setJobTitle("");
      setJobContent("");
      setInfraContext("");
      setSelectedJobKind(null);
      requestJobWorkflowRefresh();
      window.alert(`${data.srnum} 작업이 접수되었습니다.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 접수에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedTitle = jobTitle.trim();
    const trimmedContent = jobContent.trim();
    if (!trimmedTitle || !trimmedContent) {
      setError("작업 제목과 작업 내용을 입력해 주세요.");
      return;
    }
    setError(null);
    setConfirmSubmitOpen(true);
  };

  const handleConfirmSubmit = () => {
    setConfirmSubmitOpen(false);
    void submitJobIntake();
  };

  const handleReset = () => {
    setConfirmResetOpen(true);
  };

  const handleConfirmReset = () => {
    setConfirmResetOpen(false);
    setJobTitle("");
    setJobContent("");
    setInfraContext("");
    setSelectedJobKind(null);
    setError(null);
  };

  const handleInfraPick = (token: string) => {
    setInfraContext((prev) => {
      const trimmed = prev.trimEnd();
      return trimmed ? `${trimmed}\n${token}` : token;
    });
  };

  const handleJobKindSelect = async (jobKind: JobKind) => {
    if (isSubmitting || isHelping) {
      return;
    }
    setSelectedJobKind(jobKind);
    setIsHelping(true);
    setError(null);
    const message = buildHelperMessage(infraContext, jobKind);
    try {
      const response = await fetch("/api/job-request-helper/invoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 요청서 작성에 실패했습니다."));
      }
      const payload = (await response.json()) as {
        content?: string;
        title?: string;
        form?: string;
      };
      const title = (payload.title || "").trim();
      const form = (payload.form || "").trim();
      if (!title && !form) {
        throw new Error("작업 요청서 결과가 비어 있습니다.");
      }
      if (title) {
        setJobTitle(title.slice(0, 300));
      }
      if (form) {
        setJobContent(form);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 요청서 작성에 실패했습니다.");
    } finally {
      setIsHelping(false);
    }
  };

  const busy = isSubmitting || isHelping;

  return (
    <>
      <form
        onSubmit={handleSubmit}
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain p-3"
      >
        <div className="space-y-2 text-xs text-slate-400">
          <div>
            <JobFieldLabel bullet="👤">요청자</JobFieldLabel>
            <p className="mt-1 text-slate-300">
              {user.username} ({user.email})
            </p>
          </div>
          <div>
            <JobFieldLabel bullet="🏢">부서</JobFieldLabel>
            <p className="mt-1 text-slate-300">{user.depart}</p>
          </div>
        </div>

        <label className="flex flex-col gap-1.5">
          <JobFieldLabel bullet="📋">작업 제목</JobFieldLabel>
          <input
            type="text"
            value={jobTitle}
            onChange={(event) => setJobTitle(event.target.value)}
            disabled={busy}
            maxLength={300}
            placeholder="작업 제목을 입력하세요"
            className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500 disabled:opacity-50"
          />
        </label>

        <InfraDictionaryPanel onPick={handleInfraPick} />

        {infraContext.trim() ? (
          <p className="whitespace-pre-wrap break-words rounded-md border border-slate-800 bg-slate-950/50 px-2 py-1.5 font-mono text-[11px] text-slate-400">
            {infraContext}
          </p>
        ) : null}

        <div className="w-full shrink-0">
          <div className="mb-1">
            <JobFieldLabel bullet="🗂️">작업 종류</JobFieldLabel>
          </div>
          <div className="flex flex-wrap gap-1.5 rounded-md border border-slate-700 bg-slate-950/70 p-2">
            {JOB_KIND_OPTIONS.map((kind) => (
              <button
                key={kind}
                type="button"
                disabled={busy}
                className={`${CHIP} ${selectedJobKind === kind ? CHIP_ACTIVE : ""}`}
                onClick={() => void handleJobKindSelect(kind)}
              >
                {kind}
              </button>
            ))}
            {isHelping ? (
              <span className="self-center text-[11px] text-slate-500">요청서 작성 중…</span>
            ) : null}
          </div>
        </div>

        <label className="flex min-h-0 flex-1 flex-col gap-1.5">
          <JobFieldLabel bullet="📝">작업 내용</JobFieldLabel>
          <textarea
            value={jobContent}
            onChange={(event) => setJobContent(event.target.value)}
            disabled={busy}
            placeholder="작업 종류를 선택하면 요청서가 여기에 작성됩니다"
            className="min-h-[8rem] flex-1 resize-none rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500 disabled:opacity-50"
          />
        </label>

        {error ? <p className="text-sm text-rose-300">{error}</p> : null}

        <div className="flex w-full shrink-0 items-center gap-2">
          <button
            type="submit"
            disabled={busy || !jobTitle.trim() || !jobContent.trim()}
            className={`${ACTION_BUTTON_BASE} min-w-0 flex-1 bg-sky-600 text-white hover:bg-sky-500 disabled:bg-slate-700`}
          >
            {isSubmitting ? "접수 중..." : "작업 접수"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={handleReset}
            className={`${ACTION_BUTTON_BASE} shrink-0 border border-slate-600 bg-slate-800/80 text-slate-200 hover:bg-slate-700`}
          >
            초기화
          </button>
        </div>
      </form>

      {confirmSubmitOpen ? (
        <ConfirmDialog
          title="작업 접수"
          message="작업을 접수하시겠습니까?"
          confirmLabel="접수"
          onConfirm={handleConfirmSubmit}
          onCancel={() => setConfirmSubmitOpen(false)}
        />
      ) : null}

      {confirmResetOpen ? (
        <ConfirmDialog
          title="초기화"
          message="작업접수 패널에 작성한 내용을 초기화하시겠습니까?"
          confirmLabel="초기화"
          onConfirm={handleConfirmReset}
          onCancel={() => setConfirmResetOpen(false)}
        />
      ) : null}
    </>
  );
}
