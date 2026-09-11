import { useCallback, useEffect, useRef, useState } from "react";

const VISIBLE_COUNT = 5;
/** Row height (h-9) + gap-2 between rows. */
const MAX_HEIGHT = `calc(${VISIBLE_COUNT} * 2.25rem + ${(VISIBLE_COUNT - 1) * 0.5}rem)`;

interface TemplateVariableInputsProps {
  varNames: string[];
  values: Record<string, string>;
  locked?: boolean;
  onChange: (varName: string, value: string) => void;
}

export function TemplateVariableInputs({
  varNames,
  values,
  locked = false,
  onChange,
}: TemplateVariableInputsProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollUp, setCanScrollUp] = useState(false);
  const [canScrollDown, setCanScrollDown] = useState(false);
  const needsScroll = varNames.length > VISIBLE_COUNT;

  const updateScrollHints = useCallback(() => {
    const el = scrollRef.current;
    if (!el || !needsScroll) {
      setCanScrollUp(false);
      setCanScrollDown(false);
      return;
    }
    const { scrollTop, scrollHeight, clientHeight } = el;
    setCanScrollUp(scrollTop > 1);
    setCanScrollDown(scrollTop + clientHeight < scrollHeight - 1);
  }, [needsScroll]);

  useEffect(() => {
    updateScrollHints();
    const el = scrollRef.current;
    if (!el) {
      return;
    }
    const observer = new ResizeObserver(() => {
      updateScrollHints();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [updateScrollHints, varNames.length]);

  if (varNames.length === 0) {
    return null;
  }

  return (
    <div className="relative mt-1">
      {canScrollUp ? (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-center bg-gradient-to-b from-slate-950 via-slate-950/90 to-transparent pb-3 pt-0.5"
        >
          <span className="rounded-full border border-slate-600/80 bg-slate-900/90 px-2 py-0.5 text-[10px] text-slate-300 shadow">
            ▲ 위에 더 있음
          </span>
        </div>
      ) : null}

      <div
        ref={scrollRef}
        onScroll={updateScrollHints}
        className={`grid gap-2 overscroll-contain ${needsScroll ? "overflow-y-auto pr-0.5" : ""}`}
        style={needsScroll ? { maxHeight: MAX_HEIGHT } : undefined}
      >
        {varNames.map((varName) => (
          <label
            key={varName}
            className="flex h-9 items-center gap-2 text-xs text-slate-400"
          >
            <span
              className="w-28 shrink-0 truncate font-medium text-slate-300"
              title={varName}
            >
              {varName}
            </span>
            <input
              value={values[varName] ?? ""}
              onChange={(event) => {
                onChange(varName, event.target.value);
              }}
              readOnly={locked}
              disabled={locked}
              placeholder={`{${varName}}`}
              className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100 disabled:opacity-80"
            />
          </label>
        ))}
      </div>

      {canScrollDown ? (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-end justify-center bg-gradient-to-t from-slate-950 via-slate-950/90 to-transparent pb-0.5 pt-3"
        >
          <span className="rounded-full border border-slate-600/80 bg-slate-900/90 px-2 py-0.5 text-[10px] text-slate-300 shadow">
            ▼ 아래에 더 있음
          </span>
        </div>
      ) : null}
    </div>
  );
}
