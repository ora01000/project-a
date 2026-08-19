import { lazy, Suspense } from "react";

import sampleDiagram from "../../data/fossflow/diagram-sample-nuca-vms.json";
import type { FossflowCompactDiagram } from "../../types/fossflow";

const FossFlowDiagram = lazy(() =>
  import("../FossFlowDiagram").then((module) => ({ default: module.FossFlowDiagram })),
);

export function FossFlowTab() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-3">
      <Suspense fallback={<p className="p-4 text-xs text-slate-400">다이어그램을 불러오는 중...</p>}>
        <FossFlowDiagram diagram={sampleDiagram as FossflowCompactDiagram} />
      </Suspense>
    </div>
  );
}
