import { useLayoutEffect, useMemo, useRef, useState } from "react";

type ScriptCodeEditorProps = {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  className?: string;
};

const LINE_HEIGHT_PX = 20; // matches leading-5 + text-[11px] mono
const GUTTER_PAD_Y_PX = 16; // py-2 top+bottom

function countLines(value: string): number {
  if (!value) {
    return 1;
  }
  let lines = 1;
  for (let i = 0; i < value.length; i += 1) {
    if (value.charCodeAt(i) === 10) {
      lines += 1;
    }
  }
  return lines;
}

/** Lightweight monospace editor with a scroll-synced line-number gutter. */
export function ScriptCodeEditor({
  value,
  disabled = false,
  onChange,
  className = "",
}: ScriptCodeEditorProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const [visibleLineCapacity, setVisibleLineCapacity] = useState(1);
  const contentLineCount = useMemo(() => countLines(value), [value]);
  const displayLineCount = Math.max(contentLineCount, visibleLineCapacity);
  const gutterWidthCh = Math.max(2, String(displayLineCount).length);

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    const updateCapacity = () => {
      const height = root.clientHeight || root.getBoundingClientRect().height;
      const usable = Math.max(0, height - GUTTER_PAD_Y_PX);
      const next = Math.max(1, Math.ceil(usable / LINE_HEIGHT_PX) + 1);
      setVisibleLineCapacity((current) => (current === next ? current : next));
    };
    updateCapacity();
    const frame = window.requestAnimationFrame(updateCapacity);
    const observer = new ResizeObserver(updateCapacity);
    observer.observe(root);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  const syncGutterScroll = () => {
    const textarea = textareaRef.current;
    const gutter = gutterRef.current;
    if (!textarea || !gutter) {
      return;
    }
    gutter.scrollTop = textarea.scrollTop;
  };

  return (
    <div
      ref={rootRef}
      className={`flex h-full min-h-0 w-full flex-1 overflow-hidden bg-slate-950/40 ${className}`.trim()}
    >
      <div
        ref={gutterRef}
        aria-hidden
        className="h-full shrink-0 self-stretch overflow-hidden border-r border-slate-700/80 bg-slate-950/70 py-2 text-right font-mono text-[11px] leading-5 text-slate-500 select-none"
        style={{ width: `calc(${gutterWidthCh}ch + 1.25rem)` }}
      >
        <div style={{ height: Math.max(displayLineCount * LINE_HEIGHT_PX, visibleLineCapacity * LINE_HEIGHT_PX) }}>
          {Array.from({ length: displayLineCount }, (_, index) => (
            <div key={index + 1} className="px-2" style={{ height: LINE_HEIGHT_PX }}>
              {index + 1}
            </div>
          ))}
        </div>
      </div>
      <textarea
        ref={textareaRef}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onScroll={syncGutterScroll}
        spellCheck={false}
        wrap="off"
        className="h-full min-h-0 min-w-0 flex-1 resize-none overflow-auto bg-transparent px-3 py-2 font-mono text-[11px] leading-5 text-slate-200 outline-none disabled:opacity-70"
        style={{ lineHeight: `${LINE_HEIGHT_PX}px` }}
      />
    </div>
  );
}
