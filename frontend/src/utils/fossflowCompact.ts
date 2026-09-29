import type { FossflowCompactDiagram, FossflowScene, FossflowSceneNode } from "../types/fossflow";
import { isFossflowCompactDiagram } from "../types/fossflow";
import { lookupFossflowIconUrl } from "./fossflowIcons";

export function compactToFossflowScene(compactModel: FossflowCompactDiagram): FossflowScene {
  if (!isFossflowCompactDiagram(compactModel)) {
    throw new Error("FossFLOW compact JSON이 아닙니다.");
  }

  const items = Array.isArray(compactModel.i) ? compactModel.i : [];
  const views = Array.isArray(compactModel.v) ? compactModel.v : [];
  const firstView = views[0] as unknown[] | undefined;
  const positions = Array.isArray(firstView?.[0]) ? (firstView[0] as number[][]) : [];
  const connections = Array.isArray(firstView?.[1]) ? (firstView[1] as number[][]) : [];

  const tileByIndex = new Map<number, { x: number; y: number }>();
  for (const pos of positions) {
    const index = pos[0];
    if (typeof index !== "number") {
      continue;
    }
    tileByIndex.set(index, { x: pos[1] ?? 0, y: pos[2] ?? 0 });
  }

  const nodes: FossflowSceneNode[] = items.map((item, index) => {
    const name = String(item[0] ?? "");
    const icon = String(item[1] || "block");
    const description = String(item[2] ?? "");
    const tile = tileByIndex.get(index) ?? { x: 0, y: 0 };
    return {
      index,
      name,
      icon,
      description,
      tile,
      iconUrl: lookupFossflowIconUrl(icon) || lookupFossflowIconUrl("block"),
    };
  });

  const connectors = connections
    .filter((conn) => typeof conn[0] === "number" && typeof conn[1] === "number" && conn[0] >= 0 && conn[1] >= 0)
    .map((conn) => ({
      fromIndex: conn[0],
      toIndex: conn[1],
    }));

  return {
    title: String(compactModel.t ?? "Untitled"),
    nodes,
    connectors,
  };
}
