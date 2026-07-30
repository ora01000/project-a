import { MOCK_RUNTIME_UNAVAILABLE_MESSAGE } from "../utils/runtimeCapabilities";

interface RuntimeModeNoticeProps {
  className?: string;
}

export function RuntimeModeNotice({ className = "" }: RuntimeModeNoticeProps) {
  return (
    <div
      className={`rounded-lg border border-amber-700/50 bg-amber-950/40 px-4 py-3 text-sm text-amber-100 ${className}`}
      role="status"
    >
      {MOCK_RUNTIME_UNAVAILABLE_MESSAGE}
    </div>
  );
}
