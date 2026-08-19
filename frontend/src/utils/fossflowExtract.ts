import { isFossflowCompactDiagram, parseFossflowCompactJson } from "../types/fossflow";
import type { FossflowCompactDiagram } from "../types/fossflow";

const FENCE_PATTERN = /```[\s\S]*?```/g;

interface TextRange {
  start: number;
  end: number;
}

function fenceRanges(content: string): TextRange[] {
  return [...content.matchAll(FENCE_PATTERN)].map((match) => ({
    start: match.index ?? 0,
    end: (match.index ?? 0) + match[0].length,
  }));
}

function isInsideRange(index: number, ranges: TextRange[]): boolean {
  return ranges.some((range) => index >= range.start && index < range.end);
}

function readJsonValue(text: string, start: number): { end: number; value: unknown } | null {
  if (text[start] !== "{") {
    return null;
  }
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (char === "\\") {
        escaped = true;
        continue;
      }
      if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === "{") {
      depth += 1;
      continue;
    }
    if (char !== "}") {
      continue;
    }
    depth -= 1;
    if (depth !== 0) {
      continue;
    }
    const slice = text.slice(start, index + 1);
    try {
      return { end: index + 1, value: JSON.parse(slice) as unknown };
    } catch {
      return null;
    }
  }
  return null;
}

export function findFossflowCompactBlocks(content: string): Array<{ start: number; end: number; diagram: FossflowCompactDiagram }> {
  const blocks: Array<{ start: number; end: number; diagram: FossflowCompactDiagram }> = [];
  let cursor = 0;
  while (cursor < content.length) {
    const start = content.indexOf("{", cursor);
    if (start < 0) {
      break;
    }
    const parsed = readJsonValue(content, start);
    if (!parsed || !isFossflowCompactDiagram(parsed.value)) {
      cursor = start + 1;
      continue;
    }
    blocks.push({ start, end: parsed.end, diagram: parsed.value });
    cursor = parsed.end;
  }
  return blocks;
}

export function embedFossflowJsonFences(content: string): string {
  const fenced = fenceRanges(content);
  const blocks = findFossflowCompactBlocks(content).filter((block) => !isInsideRange(block.start, fenced));
  if (blocks.length === 0) {
    return content;
  }
  let next = content;
  for (let index = blocks.length - 1; index >= 0; index -= 1) {
    const block = blocks[index];
    const json = next.slice(block.start, block.end);
    next = `${next.slice(0, block.start)}\n\`\`\`fossflow\n${json}\n\`\`\`\n${next.slice(block.end)}`;
  }
  return next;
}

export function parseEmbeddedFossflowJson(content: string): FossflowCompactDiagram | null {
  const trimmed = content.trim();
  const whole = parseFossflowCompactJson(trimmed);
  if (whole) {
    return whole;
  }
  const blocks = findFossflowCompactBlocks(trimmed);
  return blocks.length === 1 && blocks[0].start === 0 && blocks[0].end === trimmed.length
    ? blocks[0].diagram
    : null;
}
