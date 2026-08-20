import type { FossflowScene, FossflowSceneNode } from "../types/fossflow";

type Coords = { x: number; y: number };
type Size = { width: number; height: number };

const UNPROJECTED_TILE_SIZE = 100;
const PROJECTED_TILE = {
  width: UNPROJECTED_TILE_SIZE * 1.415,
  height: UNPROJECTED_TILE_SIZE * 0.819,
};
const ISO_MATRIX = { a: 0.707, b: -0.409, c: 0.707, d: 0.409, e: 0, f: -0.816 };
const ICON_WIDTH = PROJECTED_TILE.width * 0.8;
const ICON_HEIGHT = ICON_WIDTH * 0.623;
const CONNECTOR_SEARCH_OFFSET = { x: 1, y: 1 };
const CONNECTOR_WIDTH = 10;
const CONNECTOR_STROKE = "#5c88df";
const DIAGRAM_BG = "#f6faff";
const LABEL_HEIGHT = 80;
const LABEL_MAX_WIDTH = 250;
const GRID_PADDING_TILES = 3;
const PADDING = 48;
const FONT_FAMILY = "Roboto, Arial, sans-serif";

export interface FossflowNodeHitbox {
  index: number;
  name: string;
  description: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FossflowSvgRender {
  svg: string;
  width: number;
  height: number;
  nodes: FossflowNodeHitbox[];
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function wrapText(text: string, maxChars: number, maxLines: number): string[] {
  const trimmed = text.trim();
  if (!trimmed) {
    return [];
  }
  const words = trimmed.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxChars) {
      current = next;
      continue;
    }
    if (current) {
      lines.push(current);
    }
    current = word.length > maxChars ? `${word.slice(0, maxChars - 1)}…` : word;
  }
  if (current) {
    lines.push(current);
  }
  if (lines.length <= maxLines) {
    return lines;
  }
  const kept = lines.slice(0, maxLines);
  const last = kept[maxLines - 1];
  kept[maxLines - 1] = last.endsWith("…") ? last : `${last.slice(0, Math.max(1, last.length - 1))}…`;
  return kept;
}

function tileToScreen(tile: Coords, origin: "CENTER" | "BOTTOM" | "LEFT" | "TOP" | "RIGHT"): Coords {
  const halfW = PROJECTED_TILE.width / 2;
  const halfH = PROJECTED_TILE.height / 2;
  const position = {
    x: halfW * tile.x - halfW * tile.y,
    y: -(halfH * tile.x + halfH * tile.y),
  };
  switch (origin) {
    case "TOP":
      return { x: position.x, y: position.y - halfH };
    case "BOTTOM":
      return { x: position.x, y: position.y + halfH };
    case "LEFT":
      return { x: position.x - halfW, y: position.y };
    case "RIGHT":
      return { x: position.x + halfW, y: position.y };
    default:
      return position;
  }
}

function sortByPosition(tiles: Coords[]) {
  const xs = tiles.map((tile) => tile.x);
  const ys = tiles.map((tile) => tile.y);
  return {
    lowX: Math.min(...xs),
    highX: Math.max(...xs),
    lowY: Math.min(...ys),
    highY: Math.max(...ys),
  };
}

function getBoundingBox(tiles: Coords[], offset: Coords = { x: 0, y: 0 }): Coords[] {
  const { lowX, lowY, highX, highY } = sortByPosition(tiles);
  return [
    { x: lowX - offset.x, y: lowY - offset.y },
    { x: highX + offset.x, y: lowY - offset.y },
    { x: highX + offset.x, y: highY + offset.y },
    { x: lowX - offset.x, y: highY + offset.y },
  ];
}

function getBoundingBoxSize(boundingBox: Coords[]): Size {
  const { lowX, lowY, highX, highY } = sortByPosition(boundingBox);
  return {
    width: highX - lowX + 1,
    height: highY - lowY + 1,
  };
}

function greedyPath(from: Coords, to: Coords): Coords[] {
  const path: Coords[] = [{ x: from.x, y: from.y }];
  let x = from.x;
  let y = from.y;
  while (x !== to.x || y !== to.y) {
    if (x !== to.x) {
      x += Math.sign(to.x - x);
    }
    if (y !== to.y) {
      y += Math.sign(to.y - y);
    }
    path.push({ x, y });
  }
  return path;
}

function findPath(from: Coords, to: Coords, gridSize: Size): Coords[] {
  const width = gridSize.width;
  const height = gridSize.height;
  const inBounds = (x: number, y: number) => x >= 0 && y >= 0 && x < width && y < height;
  if (!inBounds(from.x, from.y) || !inBounds(to.x, to.y)) {
    return greedyPath(from, to);
  }
  if (from.x === to.x && from.y === to.y) {
    return [{ x: from.x, y: from.y }];
  }

  const keyOf = (x: number, y: number) => `${x},${y}`;
  const heuristic = (x: number, y: number) => Math.abs(x - to.x) + Math.abs(y - to.y);
  const gScore = new Map<string, number>([[keyOf(from.x, from.y), 0]]);
  const cameFrom = new Map<string, Coords>();
  const open: Array<{ x: number; y: number; f: number }> = [{ x: from.x, y: from.y, f: heuristic(from.x, from.y) }];
  const closed = new Set<string>();
  const neighbors = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
    [1, 1],
    [1, -1],
    [-1, 1],
    [-1, -1],
  ];

  while (open.length > 0) {
    open.sort((left, right) => left.f - right.f);
    const current = open.shift();
    if (!current) {
      break;
    }
    const currentKey = keyOf(current.x, current.y);
    if (closed.has(currentKey)) {
      continue;
    }
    closed.add(currentKey);
    if (current.x === to.x && current.y === to.y) {
      const path: Coords[] = [{ x: current.x, y: current.y }];
      let walkKey = currentKey;
      while (cameFrom.has(walkKey)) {
        const previous = cameFrom.get(walkKey);
        if (!previous) {
          break;
        }
        path.push(previous);
        walkKey = keyOf(previous.x, previous.y);
      }
      return path.reverse();
    }

    for (const [dx, dy] of neighbors) {
      const nx = current.x + dx;
      const ny = current.y + dy;
      if (!inBounds(nx, ny)) {
        continue;
      }
      const neighborKey = keyOf(nx, ny);
      if (closed.has(neighborKey)) {
        continue;
      }
      const step = dx !== 0 && dy !== 0 ? Math.SQRT2 : 1;
      const tentative = (gScore.get(currentKey) ?? Number.POSITIVE_INFINITY) + step;
      if (tentative >= (gScore.get(neighborKey) ?? Number.POSITIVE_INFINITY)) {
        continue;
      }
      cameFrom.set(neighborKey, { x: current.x, y: current.y });
      gScore.set(neighborKey, tentative);
      open.push({ x: nx, y: ny, f: tentative + heuristic(nx, ny) });
    }
  }

  return greedyPath(from, to);
}

function getConnectorPath(fromTile: Coords, toTile: Coords): { tiles: Coords[]; rectangle: { from: Coords; to: Coords } } {
  const anchors = [fromTile, toTile];
  const searchArea = getBoundingBox(anchors, CONNECTOR_SEARCH_OFFSET);
  const sorted = sortByPosition(searchArea);
  const searchAreaSize = getBoundingBoxSize(searchArea);
  const rectangle = {
    from: { x: sorted.highX, y: sorted.highY },
    to: { x: sorted.lowX, y: sorted.lowY },
  };
  const normalised = anchors.map((position) => ({
    x: rectangle.from.x - position.x,
    y: rectangle.from.y - position.y,
  }));
  const tiles = findPath(normalised[0], normalised[1], searchAreaSize);
  return { tiles, rectangle };
}

function getIsoProjection(from: Coords, to: Coords): { position: Coords; pxSize: Size } {
  const pxSize = {
    width: (Math.abs(from.x - to.x) + 1) * UNPROJECTED_TILE_SIZE,
    height: (Math.abs(from.y - to.y) + 1) * UNPROJECTED_TILE_SIZE,
  };
  const origin = getBoundingBox([from, to])[3];
  return {
    position: tileToScreen(origin, "LEFT"),
    pxSize,
  };
}

function applyIsoMatrix(point: Coords): Coords {
  return {
    x: ISO_MATRIX.a * point.x + ISO_MATRIX.c * point.y + ISO_MATRIX.e,
    y: ISO_MATRIX.b * point.x + ISO_MATRIX.d * point.y + ISO_MATRIX.f,
  };
}

function projectConnectorPoint(point: Coords, position: Coords, pxSize: Size): Coords {
  const mirrored = { x: pxSize.width - point.x, y: point.y };
  const iso = applyIsoMatrix(mirrored);
  return { x: iso.x + position.x, y: iso.y + position.y };
}

function getConnectorDirectionIcon(tiles: Coords[]): { x: number; y: number; rotation: number } | null {
  if (tiles.length < 2) {
    return null;
  }
  const iconTile = tiles[tiles.length - 2];
  const lastTile = tiles[tiles.length - 1];
  let rotation = -90;
  if (lastTile.x > iconTile.x) {
    if (lastTile.y > iconTile.y) {
      rotation = 135;
    } else if (lastTile.y < iconTile.y) {
      rotation = 45;
    } else {
      rotation = 90;
    }
  } else if (lastTile.x < iconTile.x) {
    if (lastTile.y > iconTile.y) {
      rotation = -135;
    } else if (lastTile.y < iconTile.y) {
      rotation = -45;
    } else {
      rotation = -90;
    }
  } else if (lastTile.y > iconTile.y) {
    rotation = 180;
  } else if (lastTile.y < iconTile.y) {
    rotation = 0;
  }
  return {
    x: iconTile.x * UNPROJECTED_TILE_SIZE + UNPROJECTED_TILE_SIZE / 2,
    y: iconTile.y * UNPROJECTED_TILE_SIZE + UNPROJECTED_TILE_SIZE / 2,
    rotation,
  };
}

interface NodeLayout {
  node: FossflowSceneNode;
  bottom: Coords;
  center: Coords;
  iconX: number;
  iconY: number;
  nameLines: string[];
  descLines: string[];
  cardW: number;
  cardH: number;
  cardX: number;
  cardY: number;
}

function layoutNode(node: FossflowSceneNode): NodeLayout {
  const bottom = tileToScreen(node.tile, "BOTTOM");
  const center = tileToScreen(node.tile, "CENTER");
  const nameLines = wrapText(node.name, 28, 2);
  const descLines = wrapText(node.description, 32, 3);
  const nameWidth = Math.max(0, ...nameLines.map((line) => line.length * 8.2));
  const descWidth = Math.max(0, ...descLines.map((line) => line.length * 7));
  const cardW = Math.min(LABEL_MAX_WIDTH, Math.max(96, nameWidth, descWidth) + 24);
  const cardH = 16 + nameLines.length * 18 + descLines.length * 16 + (nameLines.length && descLines.length ? 6 : 0);
  return {
    node,
    bottom,
    center,
    iconX: bottom.x - ICON_WIDTH / 2,
    iconY: bottom.y - ICON_HEIGHT,
    nameLines,
    descLines,
    cardW,
    cardH,
    cardX: center.x - cardW / 2,
    cardY: center.y - LABEL_HEIGHT - cardH,
  };
}

function expandBounds(points: Coords[]): { minX: number; minY: number; maxX: number; maxY: number } {
  return {
    minX: Math.min(...points.map((point) => point.x)),
    minY: Math.min(...points.map((point) => point.y)),
    maxX: Math.max(...points.map((point) => point.x)),
    maxY: Math.max(...points.map((point) => point.y)),
  };
}

function renderGrid(tiles: Coords[], ox: number, oy: number): string {
  const { lowX, highX, lowY, highY } = sortByPosition(tiles);
  const minX = lowX - GRID_PADDING_TILES;
  const maxX = highX + GRID_PADDING_TILES;
  const minY = lowY - GRID_PADDING_TILES;
  const maxY = highY + GRID_PADDING_TILES;
  const diamonds: string[] = [];
  for (let x = minX; x <= maxX; x += 1) {
    for (let y = minY; y <= maxY; y += 1) {
      const top = tileToScreen({ x, y }, "TOP");
      const right = tileToScreen({ x, y }, "RIGHT");
      const bottom = tileToScreen({ x, y }, "BOTTOM");
      const left = tileToScreen({ x, y }, "LEFT");
      diamonds.push(
        `<polygon points="${top.x + ox},${top.y + oy} ${right.x + ox},${right.y + oy} ${bottom.x + ox},${bottom.y + oy} ${left.x + ox},${left.y + oy}" fill="none" stroke="#000000" stroke-opacity="0.15" stroke-width="1" />`,
      );
    }
  }
  return `<g pointer-events="none">${diamonds.join("")}</g>`;
}

function renderConnector(from: FossflowSceneNode, to: FossflowSceneNode, ox: number, oy: number): { markup: string; points: Coords[] } {
  const path = getConnectorPath(from.tile, to.tile);
  if (path.tiles.length === 0) {
    return { markup: "", points: [] };
  }
  const { position, pxSize } = getIsoProjection(path.rectangle.from, path.rectangle.to);
  const drawOffset = UNPROJECTED_TILE_SIZE / 2;
  const unprojected = path.tiles.map((tile) => ({
    x: tile.x * UNPROJECTED_TILE_SIZE + drawOffset,
    y: tile.y * UNPROJECTED_TILE_SIZE + drawOffset,
  }));
  const pointsAttr = unprojected.map((point) => `${point.x},${point.y}`).join(" ");
  const projected = unprojected.map((point) => projectConnectorPoint(point, position, pxSize));
  const direction = getConnectorDirectionIcon(path.tiles);
  const arrow = direction
    ? `<g transform="translate(${direction.x}, ${direction.y}) rotate(${direction.rotation})"><polygon fill="#000000" stroke="#ffffff" stroke-width="4" points="17.58,17.01 0,-17.01 -17.58,17.01" /></g>`
    : "";
  const markup = [
    `<g transform="translate(${position.x + ox}, ${position.y + oy})">`,
    `<g transform="matrix(${ISO_MATRIX.a} ${ISO_MATRIX.b} ${ISO_MATRIX.c} ${ISO_MATRIX.d} ${ISO_MATRIX.e} ${ISO_MATRIX.f})">`,
    `<g transform="translate(${pxSize.width / 2}, ${pxSize.height / 2}) scale(-1 1) translate(${-pxSize.width / 2}, ${-pxSize.height / 2})">`,
    `<polyline points="${pointsAttr}" fill="none" stroke="#ffffff" stroke-width="${CONNECTOR_WIDTH * 1.4}" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.7" />`,
    `<polyline points="${pointsAttr}" fill="none" stroke="${CONNECTOR_STROKE}" stroke-width="${CONNECTOR_WIDTH}" stroke-linecap="round" stroke-linejoin="round" />`,
    arrow,
    "</g></g></g>",
  ].join("");
  return { markup, points: projected };
}

function renderNode(layout: NodeLayout, ox: number, oy: number): string {
  const { node, bottom, center, iconX, iconY, nameLines, descLines, cardW, cardH, cardX, cardY } = layout;
  const x = bottom.x + ox;
  const y = bottom.y + oy;
  const image = node.iconUrl
    ? `<image href="${escapeXml(node.iconUrl)}" xlink:href="${escapeXml(node.iconUrl)}" x="${iconX + ox}" y="${iconY + oy}" width="${ICON_WIDTH}" height="${ICON_HEIGHT}" />`
    : `<polygon points="${x},${iconY + oy} ${x + ICON_WIDTH / 2},${y - ICON_HEIGHT / 2} ${x},${y} ${x - ICON_WIDTH / 2},${y - ICON_HEIGHT / 2}" fill="#cbd5e1" stroke="#64748b" />`;

  const hasLabel = nameLines.length > 0 || descLines.length > 0;
  if (!hasLabel) {
    return `<g>${image}</g>`;
  }

  const stem = `<line x1="${center.x + ox}" y1="${center.y + oy}" x2="${center.x + ox}" y2="${center.y - LABEL_HEIGHT + oy}" stroke="#000000" stroke-width="3" stroke-linecap="round" stroke-dasharray="0 6" />`;
  const card = `<rect x="${cardX + ox}" y="${cardY + oy}" width="${cardW}" height="${cardH}" rx="8" fill="#ffffff" stroke="#bdbdbd" />`;
  let textY = cardY + oy + 20;
  const nameMarkup = nameLines
    .map((line) => {
      const markup = `<text x="${center.x + ox}" y="${textY}" text-anchor="middle" fill="#1e293b" font-size="14" font-family="${FONT_FAMILY}" font-weight="600">${escapeXml(line)}</text>`;
      textY += 18;
      return markup;
    })
    .join("");
  if (nameLines.length && descLines.length) {
    textY += 4;
  }
  const descMarkup = descLines
    .map((line) => {
      const markup = `<text x="${center.x + ox}" y="${textY}" text-anchor="middle" fill="#64748b" font-size="12" font-family="${FONT_FAMILY}">${escapeXml(line)}</text>`;
      textY += 16;
      return markup;
    })
    .join("");

  return `<g>${stem}${card}${nameMarkup}${descMarkup}${image}</g>`;
}

export function renderFossflowScene(scene: FossflowScene): FossflowSvgRender {
  if (scene.nodes.length === 0) {
    return {
      svg: [
        '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120" viewBox="0 0 320 120">',
        `<rect width="100%" height="100%" fill="${DIAGRAM_BG}"/>`,
        `<text x="160" y="64" text-anchor="middle" fill="#64748b" font-size="14" font-family="${FONT_FAMILY}">빈 다이어그램</text>`,
        "</svg>",
      ].join(""),
      width: 320,
      height: 120,
      nodes: [],
    };
  }

  const nodeByIndex = new Map(scene.nodes.map((node) => [node.index, node]));
  const layouts = scene.nodes.map(layoutNode);
  const boundPoints: Coords[] = [];

  for (const layout of layouts) {
    boundPoints.push(
      { x: layout.iconX, y: layout.iconY },
      { x: layout.iconX + ICON_WIDTH, y: layout.bottom.y },
      { x: layout.cardX, y: layout.cardY },
      { x: layout.cardX + layout.cardW, y: layout.cardY + layout.cardH },
    );
  }

  const connectorParts = scene.connectors.map((connector) => {
    const from = nodeByIndex.get(connector.fromIndex);
    const to = nodeByIndex.get(connector.toIndex);
    if (!from || !to) {
      return { markup: "", points: [] as Coords[] };
    }
    return renderConnector(from, to, 0, 0);
  });
  for (const part of connectorParts) {
    boundPoints.push(...part.points);
  }

  const tiles = scene.nodes.map((node) => node.tile);
  const { lowX, highX, lowY, highY } = sortByPosition(tiles);
  for (let x = lowX - GRID_PADDING_TILES; x <= highX + GRID_PADDING_TILES; x += 1) {
    for (let y = lowY - GRID_PADDING_TILES; y <= highY + GRID_PADDING_TILES; y += 1) {
      boundPoints.push(tileToScreen({ x, y }, "TOP"), tileToScreen({ x, y }, "BOTTOM"));
    }
  }

  const bounds = expandBounds(boundPoints);
  const width = Math.ceil(bounds.maxX - bounds.minX + PADDING * 2);
  const height = Math.ceil(bounds.maxY - bounds.minY + PADDING * 2);
  const ox = -bounds.minX + PADDING;
  const oy = -bounds.minY + PADDING;

  const connectorMarkup = scene.connectors
    .map((connector) => {
      const from = nodeByIndex.get(connector.fromIndex);
      const to = nodeByIndex.get(connector.toIndex);
      if (!from || !to) {
        return "";
      }
      return renderConnector(from, to, ox, oy).markup;
    })
    .join("");

  const nodeMarkup = [...layouts]
    .sort((left, right) => right.node.tile.x + right.node.tile.y - (left.node.tile.x + left.node.tile.y))
    .map((layout) => renderNode(layout, ox, oy))
    .join("");

  const svg = [
    `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<rect width="100%" height="100%" fill="${DIAGRAM_BG}"/>`,
    renderGrid(tiles, ox, oy),
    connectorMarkup,
    nodeMarkup,
    "</svg>",
  ].join("");

  return {
    svg,
    width,
    height,
    nodes: layouts.map((layout) => ({
      index: layout.node.index,
      name: layout.node.name,
      description: layout.node.description,
      x: layout.iconX + ox,
      y: layout.iconY + oy,
      width: ICON_WIDTH,
      height: ICON_HEIGHT,
    })),
  };
}

export function renderFossflowSceneSvg(scene: FossflowScene): string {
  return renderFossflowScene(scene).svg;
}
