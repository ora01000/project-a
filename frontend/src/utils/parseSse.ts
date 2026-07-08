export interface SseEvent {
  event: string;
  data: string;
}

export function parseSseChunk(buffer: string, chunk: string): {
  events: SseEvent[];
  remainder: string;
} {
  const normalized = `${buffer}${chunk}`.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const remainder = parts.pop() ?? "";
  const events: SseEvent[] = [];

  for (const block of parts) {
    if (!block.trim()) {
      continue;
    }

    const lines = block.split("\n");
    let eventName = "message";
    let dataLine = "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLine = line.slice(5).trim();
      }
    }

    if (dataLine) {
      events.push({ event: eventName, data: dataLine });
    }
  }

  return { events, remainder };
}

export function flushSseBuffer(buffer: string): SseEvent[] {
  const trimmed = buffer.trim();
  if (!trimmed) {
    return [];
  }

  return parseSseChunk("", `${trimmed}\n\n`).events;
}
