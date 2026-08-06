import { useState } from "react";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

interface JobAiReviewButtonProps {
  jobIdx: number;
  disabled?: boolean;
  onError?: (message: string) => void;
  onSuccess?: () => void;
}

export function JobAiReviewButton({
  jobIdx,
  disabled = false,
  onError,
  onSuccess,
}: JobAiReviewButtonProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleClick = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/jobs/${jobIdx}/ai-review`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "AI 검토 요청에 실패했습니다."));
      }
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "AI 검토 요청에 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <button
      type="button"
      disabled={disabled || isLoading}
      onClick={() => void handleClick()}
      className="rounded-md border border-violet-700 bg-violet-950/60 px-3 py-1.5 text-sm font-medium text-violet-100 hover:bg-violet-900/70 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {isLoading ? "검토 중..." : "AI검토"}
    </button>
  );
}
