import { useLayoutEffect, useRef, useState } from "react";

import { formatResponseTimestamp } from "../utils/messageIndex";

interface CollapsibleUserMessageProps {
  content: string;
  createdAt: string;
}

export function CollapsibleUserMessage({ content, createdAt }: CollapsibleUserMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isOverflowing, setIsOverflowing] = useState(false);

  useLayoutEffect(() => {
    const node = contentRef.current;
    if (!node) {
      return;
    }

    if (isExpanded) {
      // While expanded, keep overflow flag from previously measured collapsed state.
      return;
    }

    setIsOverflowing(node.scrollHeight > node.clientHeight + 1);
  }, [content, isExpanded]);

  const canToggle = isOverflowing || isExpanded;

  return (
    <div className="rounded-md border border-sky-700/40 bg-sky-950/45 px-2 py-1.5 text-sky-100">
      <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] leading-tight text-sky-300/80">
        <span className="rounded-full border border-sky-700/50 bg-sky-950/60 px-2 py-0.5 text-sky-200">
          User
        </span>
        <span>{formatResponseTimestamp(new Date(createdAt))}</span>
      </div>
      <div
        ref={contentRef}
        role={canToggle ? "button" : undefined}
        tabIndex={canToggle ? 0 : undefined}
        aria-expanded={canToggle ? isExpanded : undefined}
        title={canToggle ? (isExpanded ? "접기" : "펼치기") : undefined}
        onClick={() => {
          if (!canToggle) {
            return;
          }
          setIsExpanded((current) => !current);
        }}
        onKeyDown={(event) => {
          if (!canToggle) {
            return;
          }
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setIsExpanded((current) => !current);
          }
        }}
        className={`whitespace-pre-wrap break-words text-sm ${
          !isExpanded ? "line-clamp-3" : ""
        } ${canToggle ? "cursor-pointer select-text" : ""}`}
      >
        {content}
      </div>
      {canToggle ? (
        <div className="mt-1 text-[10px] text-sky-400/80">
          {isExpanded ? "클릭하여 접기" : "클릭하여 펼치기"}
        </div>
      ) : null}
    </div>
  );
}
