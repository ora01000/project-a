import { useEffect, useRef } from "react";

export type MonitorAreaPreset = "FHD" | "QHD" | "4K";

export const MONITOR_AREA_PRESETS: Record<
  MonitorAreaPreset,
  { label: string; width: number; height: number }
> = {
  FHD: { label: "FHD", width: 1920, height: 1080 },
  QHD: { label: "QHD", width: 2560, height: 1440 },
  "4K": { label: "4K", width: 3840, height: 2160 },
};

const AUTO_HIDE_MS = 2500;

interface MonitorAreaOverlayProps {
  preset: MonitorAreaPreset;
  onDone: () => void;
}

export function MonitorAreaOverlay({ preset, onDone }: MonitorAreaOverlayProps) {
  const { label, width, height } = MONITOR_AREA_PRESETS[preset];
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      onDoneRef.current();
    }, AUTO_HIDE_MS);
    return () => window.clearTimeout(timer);
  }, [preset]);

  return (
    <div className="pointer-events-none fixed inset-0 z-[100] overflow-visible" aria-hidden>
      <div
        className="absolute box-border border-2 border-amber-400/90 shadow-[0_0_0_1px_rgba(15,23,42,0.55)]"
        style={{
          left: 0,
          top: 0,
          width,
          height,
        }}
      >
        <div className="absolute left-2 top-2 rounded bg-slate-950/80 px-2 py-1 font-mono text-[11px] font-medium text-amber-100">
          모니터 영역 · {label} ({width}×{height})
        </div>
      </div>
    </div>
  );
}
