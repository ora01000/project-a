import { formatMessageIndex } from "../utils/messageIndex";

interface MessageIndexLabelProps {
  num: number;
  createdAt: string;
}

export function MessageIndexLabel({ num, createdAt }: MessageIndexLabelProps) {
  return (
    <div className="mb-1 text-[10px] leading-tight text-slate-400">
      {formatMessageIndex(num, new Date(createdAt))}
    </div>
  );
}
