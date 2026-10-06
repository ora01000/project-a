import { memo, useMemo } from "react";

import { parseWhatapJson } from "../types/whatapJson";
import { downloadDiagramSvg } from "../utils/diagramExport";
import { renderWhatapJsonSvg } from "../utils/whatapJsonSvg";

interface WhatapJsonChartProps {
  raw: string;
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden="true">
      <path d="M12 3v12m0 0l4-4m-4 4l-4-4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" />
    </svg>
  );
}

function WhatapJsonChartInner({ raw }: WhatapJsonChartProps) {
  const chart = useMemo(() => parseWhatapJson(raw), [raw]);
  const svg = useMemo(() => (chart ? renderWhatapJsonSvg(chart) : null), [chart]);

  if (!chart || !svg) {
    return <p className="text-xs text-amber-300">whatap-json 시계열 데이터를 해석하지 못했습니다.</p>;
  }

  const title = [chart.metric, chart.unit ? `(${chart.unit})` : ""].filter(Boolean).join(" ") || "whatap chart";

  return (
    <div className="whatap-json-chart relative w-full overflow-hidden rounded border border-slate-300 bg-white">
      <div className="absolute right-2 top-2 z-10">
        <button
          type="button"
          className="rounded border border-slate-300 bg-white/90 p-1.5 text-slate-600 hover:bg-slate-100"
          title="SVG 다운로드"
          aria-label={`${title} SVG 다운로드`}
          onClick={() => downloadDiagramSvg(svg, "whatap-json-chart")}
        >
          <DownloadIcon />
        </button>
      </div>
      <div
        className="w-full overflow-x-auto p-2"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );
}

export const WhatapJsonChart = memo(WhatapJsonChartInner);
