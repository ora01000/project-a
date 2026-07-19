import { useEffect, useMemo, useState } from "react";

interface JobTestSample {
  sample_id: string;
  job_title: string;
  job_description: string;
  request_depart: string;
  requester: string;
  requester_email: string;
  approver: string;
  target_agent_family: string;
  notes: string;
}

interface TestJobSendForm {
  sample_id: string;
  request_depart: string;
  requester: string;
  approver: string;
  job_title: string;
  job_description: string;
}

interface TestJobSendModalProps {
  onClose: () => void;
}

const APPROVER_OPTIONS: { userid: string; label: string }[] = [
  { userid: "isyun", label: "isyun (윤인수)" },
  { userid: "loadan", label: "loadan (안세훈)" },
];

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

function toForm(sample: JobTestSample): TestJobSendForm {
  return {
    sample_id: sample.sample_id,
    request_depart: sample.request_depart,
    requester: sample.requester,
    approver: sample.approver,
    job_title: sample.job_title,
    job_description: sample.job_description,
  };
}

export function TestJobSendModal({ onClose }: TestJobSendModalProps) {
  const [samples, setSamples] = useState<JobTestSample[]>([]);
  const [form, setForm] = useState<TestJobSendForm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadSamples = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/jobs/test-samples");
        if (!response.ok) {
          throw new Error(await parseError(response, "테스트 샘플을 불러오지 못했습니다."));
        }
        const data = (await response.json()) as JobTestSample[];
        if (cancelled) {
          return;
        }
        setSamples(data);
        if (data.length > 0) {
          setForm(toForm(data[0]));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "테스트 샘플을 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadSamples();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedSample = useMemo(
    () => samples.find((sample) => sample.sample_id === form?.sample_id) ?? null,
    [samples, form?.sample_id],
  );

  const updateField = <K extends keyof TestJobSendForm>(key: K, value: TestJobSendForm[K]) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  };

  const handleSelectSample = (sampleId: string) => {
    const sample = samples.find((item) => item.sample_id === sampleId);
    if (!sample) {
      return;
    }
    setError(null);
    setForm(toForm(sample));
  };

  const handleSend = async () => {
    if (!form) {
      return;
    }
    if (
      !form.request_depart.trim() ||
      !form.requester.trim() ||
      !form.approver.trim() ||
      !form.job_title.trim() ||
      !form.job_description.trim()
    ) {
      setError("필수 항목을 모두 입력해 주세요.");
      return;
    }

    setIsSending(true);
    setError(null);
    try {
      const response = await fetch("/api/jobs/test-samples/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sample_id: form.sample_id,
          request_depart: form.request_depart.trim(),
          requester: form.requester.trim(),
          approver: form.approver.trim(),
          job_title: form.job_title.trim(),
          job_description: form.job_description.trim(),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "테스트 작업 발송에 실패했습니다."));
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "테스트 작업 발송에 실패했습니다.");
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="test-job-send-title"
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="test-job-send-title" className="text-lg font-semibold text-slate-100">
          테스트 작업 발송
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          샘플 작업 요청서를 선택한 뒤 내용을 수정하고 &quot;작업 분석/계획&quot; 에이전트로 발송합니다.
        </p>

        {isLoading ? (
          <p className="mt-4 text-sm text-slate-500">샘플을 불러오는 중...</p>
        ) : form ? (
          <div className="mt-4 space-y-3">
            <label className="block space-y-1 text-sm text-slate-300">
              <span>샘플 선택</span>
              <select
                value={form.sample_id}
                onChange={(event) => handleSelectSample(event.target.value)}
                disabled={isSending}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
              >
                {samples.map((sample) => (
                  <option key={sample.sample_id} value={sample.sample_id}>
                    {sample.sample_id} · {sample.job_title}
                  </option>
                ))}
              </select>
            </label>

            {selectedSample ? (
              <p className="text-xs text-slate-500">
                대상 에이전트: {selectedSample.target_agent_family} · {selectedSample.notes}
              </p>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block space-y-1 text-sm text-slate-300">
                <span>기안조직</span>
                <input
                  value={form.request_depart}
                  onChange={(event) => updateField("request_depart", event.target.value)}
                  disabled={isSending}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
              </label>

              <label className="block space-y-1 text-sm text-slate-300">
                <span>기안자 (userid)</span>
                <input
                  value={form.requester}
                  onChange={(event) => updateField("requester", event.target.value)}
                  disabled={isSending}
                  placeholder="예: isyun"
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                />
              </label>

              <label className="block space-y-1 text-sm text-slate-300 sm:col-span-2">
                <span>작업승인자 (userid)</span>
                <select
                  value={form.approver}
                  onChange={(event) => updateField("approver", event.target.value)}
                  disabled={isSending}
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
                >
                  {!APPROVER_OPTIONS.some((option) => option.userid === form.approver) ? (
                    <option value={form.approver}>{form.approver}</option>
                  ) : null}
                  {APPROVER_OPTIONS.map((option) => (
                    <option key={option.userid} value={option.userid}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="block space-y-1 text-sm text-slate-300">
              <span>작업제목</span>
              <input
                value={form.job_title}
                onChange={(event) => updateField("job_title", event.target.value)}
                disabled={isSending}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
              />
            </label>

            <label className="block space-y-1 text-sm text-slate-300">
              <span>작업요청내용</span>
              <textarea
                value={form.job_description}
                onChange={(event) => updateField("job_description", event.target.value)}
                disabled={isSending}
                rows={10}
                className="w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
              />
            </label>
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500">등록된 테스트 샘플이 없습니다.</p>
        )}

        {error ? (
          <div className="mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isSending}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={isSending || !form}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:bg-slate-700"
          >
            {isSending ? "발송 중..." : "발송"}
          </button>
        </div>
      </div>
    </div>
  );
}
