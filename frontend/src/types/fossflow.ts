export type FossflowCompactItem = [name: string, icon: string, description?: string];

export type FossflowCompactPosition = [itemIndex: number, x: number, y: number];

export type FossflowCompactConnection = [fromIndex: number, toIndex: number];

export type FossflowCompactView = [FossflowCompactPosition[], FossflowCompactConnection[]];

export interface FossflowCompactDiagram {
  t?: string;
  i?: FossflowCompactItem[] | string[][];
  v?: FossflowCompactView[] | number[][][][];
  _?: {
    f?: string;
    v?: string;
  };
}

export interface FossflowSceneNode {
  index: number;
  name: string;
  icon: string;
  description: string;
  tile: { x: number; y: number };
  iconUrl: string;
}

export interface FossflowSceneConnector {
  fromIndex: number;
  toIndex: number;
}

export interface FossflowScene {
  title: string;
  nodes: FossflowSceneNode[];
  connectors: FossflowSceneConnector[];
}

export function isFossflowCompactDiagram(value: unknown): value is FossflowCompactDiagram {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as { _?: { f?: unknown }; i?: unknown; v?: unknown };
  return record._?.f === "compact" && Array.isArray(record.i) && Array.isArray(record.v);
}

export function parseFossflowCompactJson(text: string): FossflowCompactDiagram | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return isFossflowCompactDiagram(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
