import { useEffect, useState } from "react";

import { ROLE_ADMIN } from "../../types/user";

interface MockLlmOption {
  id: "local" | "openai";
  label: string;
  base_url: string;
  model: string;
}

interface MockLlmOpenAiSettings {
  label: string;
  base_url: string;
  model: string;
  configured: boolean;
  api_key_masked: string;
  available_models: string[];
}

interface MockLlmState {
  provider: "local" | "openai";
  options: MockLlmOption[];
  local: { label: string; base_url: string; model: string };
  openai: MockLlmOpenAiSettings;
}

interface MockLlmSelectModalProps {
  viewerRole: number;
  onClose: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function MockLlmSelectModal({ viewerRole, onClose }: MockLlmSelectModalProps) {
  const [state, setState] = useState<MockLlmState | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<"local" | "openai">("local");
  const [openaiApiKey, setOpenaiApiKey] = useState("");
  const [openaiModel, setOpenaiModel] = useState("gpt-4o-mini");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadState = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/debug/mock-llm");
        if (!response.ok) {
          throw new Error(await parseError(response, "목업 LLM 설정을 불러오지 못했습니다."));
        }
        const data = (await response.json()) as MockLlmState;
        if (!cancelled) {
          setState(data);
          setSelectedProvider(data.provider);
          setOpenaiModel(data.openai.model);
          setOpenaiApiKey("");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "목업 LLM 설정을 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadState();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleApply = async () => {
    if (viewerRole !== ROLE_ADMIN) {
      setError("관리자만 변경할 수 있습니다.");
      return;
    }

    if (selectedProvider === "openai") {
      const hasExistingKey = state?.openai.configured === true;
      if (!openaiApiKey.trim() && !hasExistingKey) {
        setError("OpenAI API key를 입력해 주세요.");
        return;
      }
      if (!openaiModel.trim()) {
        setError("OpenAI model을 선택해 주세요.");
        return;
      }
    }

    setIsSaving(true);
    setError(null);
    try {
      const body: {
        viewer_role: number;
        provider: "local" | "openai";
        openai_api_key?: string;
        openai_model?: string;
      } = {
        viewer_role: viewerRole,
        provider: selectedProvider,
      };

      if (selectedProvider === "openai") {
        body.openai_model = openaiModel.trim();
        if (openaiApiKey.trim()) {
          body.openai_api_key = openaiApiKey.trim();
        }
      }

      const response = await fetch("/api/debug/mock-llm", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "목업 LLM 변경에 실패했습니다."));
      }
      const data = (await response.json()) as MockLlmState;
      setState(data);
      setSelectedProvider(data.provider);
      setOpenaiModel(data.openai.model);
      setOpenaiApiKey("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "목업 LLM 변경에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  const modelOptions = state?.openai.available_models ?? ["gpt-4o-mini"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="mock-llm-dialog-title"
        className="w-full max-w-xl rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id="mock-llm-dialog-title" className="text-lg font-semibold text-slate-100">
            (목업) LLM 변경
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <p className="mt-2 text-sm text-slate-400">
          목업 환경에서 에이전트가 사용할 LLM을 선택합니다. 변경 즉시 이후 호출부터 적용됩니다.
        </p>

        {isLoading ? (
          <p className="mt-4 text-sm text-slate-500">설정을 불러오는 중…</p>
        ) : (
          <div className="mt-4 space-y-3">
            {(state?.options ?? []).map((option) => (
              <label
                key={option.id}
                className={`flex cursor-pointer gap-3 rounded-md border px-3 py-3 ${
                  selectedProvider === option.id
                    ? "border-sky-600 bg-sky-950/30"
                    : "border-slate-700 bg-slate-950/40"
                }`}
              >
                <input
                  type="radio"
                  name="mock-llm-provider"
                  value={option.id}
                  checked={selectedProvider === option.id}
                  onChange={() => setSelectedProvider(option.id)}
                  className="mt-1"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-slate-100">{option.label}</span>
                  <span className="mt-1 block font-mono text-xs text-slate-400">{option.base_url}</span>
                  {option.id === "local" ? (
                    <span className="mt-1 block text-xs text-slate-500">model: {option.model}</span>
                  ) : null}
                </span>
              </label>
            ))}

            {selectedProvider === "openai" ? (
              <div className="space-y-3 rounded-md border border-slate-700 bg-slate-950/50 p-3">
                <div>
                  <label className="block text-sm font-medium text-slate-200" htmlFor="openai-api-key">
                    API Key
                  </label>
                  <input
                    id="openai-api-key"
                    type="password"
                    value={openaiApiKey}
                    onChange={(event) => setOpenaiApiKey(event.target.value)}
                    placeholder={
                      state?.openai.configured
                        ? `기존 키 유지 (${state.openai.api_key_masked})`
                        : "sk-proj-..."
                    }
                    autoComplete="off"
                    className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-600 focus:outline-none"
                  />
                  {state?.openai.configured ? (
                    <p className="mt-1 text-xs text-slate-500">
                      비워두면 저장된 키({state.openai.api_key_masked})를 그대로 사용합니다.
                    </p>
                  ) : null}
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-200" htmlFor="openai-model">
                    Model
                  </label>
                  <select
                    id="openai-model"
                    value={openaiModel}
                    onChange={(event) => setOpenaiModel(event.target.value)}
                    className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-sky-600 focus:outline-none"
                  >
                    {modelOptions.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            ) : null}
          </div>
        )}

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

        <div className="mt-5 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleApply()}
            disabled={isLoading || isSaving}
            className="rounded-md border border-sky-700 bg-sky-950/40 px-4 py-2 text-sm text-sky-100 hover:bg-sky-900/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? "적용 중…" : "적용"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
