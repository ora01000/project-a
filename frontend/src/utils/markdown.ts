const MARKDOWN_PATTERNS = [
  /^#{1,6}\s/m,
  /\*\*[^*]+\*\*/,
  /\*[^*]+\*/,
  /__[^_]+__/,
  /_[^_]+_/,
  /```mermaid[\s\S]*?```/,
  /```d2[\s\S]*?```/,
  /```fossflow[\s\S]*?```/,
  /```isoflow[\s\S]*?```/,
  /```[\s\S]*?```/,
  /`[^`]+`/,
  /^\s*[-*+]\s/m,
  /^\s*\d+\.\s/m,
  /^\s*\|.+\|\s*$/m,
  /\[.+?\]\(.+?\)/,
  /^>\s/m,
];

export function hasMarkdownSyntax(content: string): boolean {
  return MARKDOWN_PATTERNS.some((pattern) => pattern.test(content));
}
