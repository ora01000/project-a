import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import type { AuthUser } from "../../types/auth";
import type { UserRecord } from "../../types/user";
import { ROLE_ADMIN } from "../../types/user";
import { dateOnlyAfterDays, formatJobDatetime } from "../../utils/datetime";

interface JobCreatePageProps {
  user: AuthUser;
  onCreated?: () => void;
}

interface JobCreateForm {
  job_title: string;
  request_depart: string;
  requester: string;
  requester_email: string;
  completion_request_date: string;
  job_description: string;
  approver: string;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function defaultCompletionDate(): string {
  const date = new Date(`${dateOnlyAfterDays(3)}T12:00:00+09:00`);
  return formatJobDatetime(date);
}

function buildInitialForm(user: AuthUser): JobCreateForm {
  return {
    job_title: "",
    request_depart: user.depart || "",
    requester: user.userid,
    requester_email: user.email || "",
    completion_request_date: defaultCompletionDate(),
    job_description: "",
    approver: "",
  };
}

export function JobCreatePage({ user, onCreated }: JobCreatePageProps) {
  const [form, setForm] = useState<JobCreateForm>(() => buildInitialForm(user));
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadUsers = useCallback(async () => {
    setIsLoadingUsers(true);
    try {
      const response = await fetch(`/api/users?viewer_role=${user.role}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "사용자 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as UserRecord[];
      setUsers(data.filter((entry) => entry.role !== 5));
    } catch (err) {
      setError(err instanceof Error ? err.message : "사용자 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoadingUsers(false);
    }
  }, [user.role]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    setForm(buildInitialForm(user));
  }, [user]);

  const approverOptions = useMemo(() => {
    const options = users.filter((entry) => entry.userid !== user.userid || entry.role === ROLE_ADMIN);
    return options.length > 0 ? options : users;
  }, [users, user.userid]);

  const updateField = <K extends keyof JobCreateForm>(key: K, value: JobCreateForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setSuccess(null);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (
      !form.job_title.trim() ||
      !form.request_depart.trim() ||
      !form.requester.trim() ||
      !form.requester_email.trim() ||
      !form.completion_request_date.trim() ||
      !form.job_description.trim() ||
      !form.approver.trim()
    ) {
      setError("필수 항목을 모두 입력해 주세요.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_date: formatJobDatetime(new Date()),
          job_title: form.job_title.trim(),
          request_depart: form.request_depart.trim(),
          requester: form.requester.trim(),
          requester_email: form.requester_email.trim(),
          completion_request_date: form.completion_request_date.trim(),
          job_description: form.job_description.trim(),
          approver: form.approver.trim(),
          notify_channel: "integrated_chat",
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "작업 생성에 실패했습니다."));
      }
      const created = (await response.json()) as { idx: number; job_title: string; sr_num?: string | null };
      const srLabel = created.sr_num ? `, ${created.sr_num}` : "";
      setSuccess(`작업이 생성되었습니다. (idx=${created.idx}${srLabel}, ${created.job_title})`);
      setForm(buildInitialForm(user));
      onCreated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "작업 생성에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90">
      <header className="shrink-0 border-b border-slate-700 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-200">작업 생성</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          작업 요청서를 작성하면 계획 수립 에이전트로 전달됩니다. 기안자/승인자는 userid로
          저장됩니다.
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {error ? (
          <div className="mb-4 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}
        {success ? (
          <div className="mb-4 rounded-md border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-200">
            {success}
          </div>
        ) : null}

        <form onSubmit={(event) => void handleSubmit(event)} className="mx-auto max-w-2xl space-y-4">
          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">작업 제목</span>
            <input
              type="text"
              value={form.job_title}
              onChange={(event) => updateField("job_title", event.target.value)}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
              maxLength={200}
              required
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-1 text-sm">
              <span className="text-slate-300">기안 조직</span>
              <input
                type="text"
                value={form.request_depart}
                onChange={(event) => updateField("request_depart", event.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
                maxLength={50}
                required
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-slate-300">완료 요청 일시</span>
              <input
                type="text"
                value={form.completion_request_date}
                onChange={(event) => updateField("completion_request_date", event.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-slate-100"
                placeholder="YYYY-MM-DD HH:MM:SS"
                required
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-1 text-sm">
              <span className="text-slate-300">기안자 (userid)</span>
              <input
                type="text"
                value={form.requester}
                readOnly
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-300"
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-slate-300">기안자 이메일</span>
              <input
                type="email"
                value={form.requester_email}
                onChange={(event) => updateField("requester_email", event.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
                maxLength={50}
                required
              />
            </label>
          </div>

          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">승인자 (userid)</span>
            <select
              value={form.approver}
              onChange={(event) => updateField("approver", event.target.value)}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
              disabled={isLoadingUsers}
              required
            >
              <option value="">{isLoadingUsers ? "불러오는 중..." : "승인자를 선택하세요"}</option>
              {approverOptions.map((entry) => (
                <option key={entry.idx} value={entry.userid}>
                  {entry.userid} ({entry.username})
                </option>
              ))}
            </select>
          </label>

          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">작업 내용</span>
            <textarea
              value={form.job_description}
              onChange={(event) => updateField("job_description", event.target.value)}
              className="min-h-[160px] w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
              required
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => {
                setForm(buildInitialForm(user));
                setError(null);
                setSuccess(null);
              }}
              className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              초기화
            </button>
            <button
              type="submit"
              disabled={isSubmitting || isLoadingUsers}
              className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "생성 중..." : "작업 생성"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
