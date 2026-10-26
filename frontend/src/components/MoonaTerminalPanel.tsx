import { useEffect, useRef, useState, type FormEvent } from "react";

import { useTheme } from "../context/ThemeContext";
import type { AuthUser } from "../types/auth";
import { formatResponseTimestamp } from "../utils/messageIndex";
import { flushSseBuffer, parseSseChunk } from "../utils/parseSse";
import { MoonaIcon } from "./MoonaIcon";

type TerminalLine =
  | { id: string; kind: "command"; text: string }
  | { id: string; kind: "output"; text: string }
  | { id: string; kind: "error"; text: string }
  | { id: string; kind: "system"; text: string };

interface MoonaTerminalPanelProps {
  user: AuthUser;
  agentId: string | null;
  agentName: string | null;
  disabled?: boolean;
  sessionId: string;
  onCopyToNote?: (content: string, noteName?: string) => Promise<void>;
}

const HELP_MAN_PAGE = `무너 코드는 명령어 기반으로 질의를 할 수 있습니다.

* 단축 명령어
터미널 명령어
?, \\?,  \\help, help           도움말을 출력합니다.
\\c, \\clear                    터미널 내용을 삭제합니다.
\\s, \\save                     터미널 내용을 나의 노트에 저장합니다.

에이전트 단축 명령어
\\t, \\tool                     사용 가능한 도구와 기능을 출력합니다.
\\p, \\platform                 등록된 private 클라우드 플랫폼(okd 클러스터/ vcenter 데이터센터)을 출력합니다.`;

const HELP_COMMANDS = new Set(["?", "\\?", "\\help", "help"]);
const CLEAR_COMMANDS = new Set(["\\clear", "\\c"]);
const SAVE_COMMANDS = new Set(["/save", "/s", "\\save", "\\s"]);
const AGENT_QUERY_BY_COMMAND: Record<string, string> = {
  "\\t": "사용가능한 도구와 기능을 알려주세요",
  "\\tool": "사용가능한 도구와 기능을 알려주세요",
  "\\p": "조회/관리가 가능한 private 클라우드 플랫폼(okd, vcenter, kubevirt) 목록을 알려주세요",
  "\\platform":
    "조회/관리가 가능한 private 클라우드 플랫폼(okd, vcenter, kubevirt) 목록을 알려주세요",
};

const REGISTERED_BACKSLASH_COMMANDS = new Set([
  ...HELP_COMMANDS,
  ...CLEAR_COMMANDS,
  ...SAVE_COMMANDS,
  ...Object.keys(AGENT_QUERY_BY_COMMAND),
]);

function createLineId(): string {
  return `moona-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeCommand(raw: string): string {
  return raw.trim().toLowerCase();
}

function formatTerminalTranscript(lines: TerminalLine[]): string {
  return lines
    .map((line) => {
      if (line.kind === "command") {
        return `>> ${line.text}`;
      }
      return line.text;
    })
    .join("\n")
    .trim();
}

export function MoonaTerminalPanel({
  user,
  agentId,
  agentName,
  disabled = false,
  sessionId,
  onCopyToNote,
}: MoonaTerminalPanelProps) {
  const { theme } = useTheme();
  const isLight = theme === "light";
  const [lines, setLines] = useState<TerminalLine[]>([
    {
      id: createLineId(),
      kind: "system",
      text: "헤이 무너코드 — 명령을 입력하면 아래에 결과가 이어집니다. (? 로 도움말)",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const linesRef = useRef(lines);
  linesRef.current = lines;

  const shellClass = isLight
    ? "border-slate-300 bg-slate-50 text-slate-800"
    : "border-slate-800 bg-black text-slate-100";
  const promptAccentClass = isLight ? "text-pink-600" : "text-pink-300";
  const promptSepClass = isLight ? "text-slate-500" : "text-slate-400";
  const commandTextClass = isLight ? "text-slate-900" : "text-slate-100";
  const outputClass = isLight ? "text-emerald-700" : "text-emerald-200/90";
  const errorClass = isLight ? "text-rose-600" : "text-rose-300";
  const systemClass = isLight ? "text-slate-500" : "text-slate-500";
  const inputClass = isLight
    ? "min-w-0 flex-1 bg-transparent text-slate-900 outline-none caret-pink-600 placeholder:text-slate-400"
    : "min-w-0 flex-1 bg-transparent text-slate-100 outline-none caret-pink-300 placeholder:text-slate-600";
  const runningClass = isLight ? "text-slate-500" : "text-slate-500";

  useEffect(() => {
    const node = scrollRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [lines, isRunning]);

  useEffect(() => {
    if (!isRunning) {
      inputRef.current?.focus();
    }
  }, [isRunning, lines.length]);

  const appendLine = (line: Omit<TerminalLine, "id">) => {
    setLines((prev) => [...prev, { ...line, id: createLineId() }]);
  };

  const runAgentChat = async (trimmed: string) => {
    if (!agentId) {
      appendLine({ kind: "error", text: "사용 가능한 에이전트가 없습니다." });
      return;
    }

    setIsRunning(true);
    const abortController = new AbortController();
    abortRef.current = abortController;
    let assistantText = "";

    try {
      const response = await fetch(`/api/agents/${agentId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          userid: user.userid,
          session_id: sessionId,
        }),
        signal: abortController.signal,
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Streaming response unavailable");
      }

      const outputId = createLineId();
      setLines((prev) => [...prev, { id: outputId, kind: "output", text: "" }]);

      const decoder = new TextDecoder();
      let buffer = "";

      const applyEvents = (events: ReturnType<typeof parseSseChunk>["events"]) => {
        for (const event of events) {
          if (!event.data || event.event !== "token") {
            continue;
          }
          try {
            const payload = JSON.parse(event.data) as { content?: string };
            assistantText += payload.content ?? "";
            const snapshot = assistantText;
            setLines((prev) =>
              prev.map((line) =>
                line.id === outputId && line.kind === "output"
                  ? { ...line, text: snapshot }
                  : line,
              ),
            );
          } catch {
            /* ignore malformed token */
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (value) {
          const parsed = parseSseChunk(buffer, decoder.decode(value, { stream: true }));
          buffer = parsed.remainder;
          applyEvents(parsed.events);
        }
        if (done) {
          applyEvents(flushSseBuffer(buffer));
          break;
        }
      }

      if (!assistantText.trim()) {
        setLines((prev) =>
          prev.map((line) =>
            line.id === outputId && line.kind === "output"
              ? { ...line, text: `(응답 없음${agentName ? ` · ${agentName}` : ""})` }
              : line,
          ),
        );
      }
    } catch (err) {
      if (abortController.signal.aborted) {
        appendLine({ kind: "system", text: "^C" });
      } else {
        const message = err instanceof Error ? err.message : String(err);
        appendLine({ kind: "error", text: message });
      }
    } finally {
      abortRef.current = null;
      setIsRunning(false);
    }
  };

  const runSaveCommand = async () => {
    if (!onCopyToNote) {
      appendLine({ kind: "error", text: "노트 저장 기능을 사용할 수 없습니다." });
      return;
    }
    const transcript = formatTerminalTranscript(linesRef.current);
    if (!transcript) {
      appendLine({ kind: "error", text: "저장할 터미널 내용이 없습니다." });
      return;
    }
    setIsRunning(true);
    try {
      const noteName = `무너코드 ${formatResponseTimestamp(new Date())}`.slice(0, 80);
      await onCopyToNote(transcript, noteName);
      appendLine({ kind: "system", text: `나의 노트에 저장했습니다 · ${noteName}` });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      appendLine({ kind: "error", text: message });
    } finally {
      setIsRunning(false);
    }
  };

  const runCommand = async (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed || isRunning) {
      return;
    }

    const command = normalizeCommand(trimmed);
    appendLine({ kind: "command", text: trimmed });
    setDraft("");

    if (HELP_COMMANDS.has(command)) {
      appendLine({ kind: "output", text: HELP_MAN_PAGE });
      return;
    }
    if (CLEAR_COMMANDS.has(command)) {
      setLines([]);
      return;
    }
    if (SAVE_COMMANDS.has(command)) {
      await runSaveCommand();
      return;
    }

    const agentQuery = AGENT_QUERY_BY_COMMAND[command];
    if (agentQuery) {
      await runAgentChat(agentQuery);
      return;
    }

    if (command.startsWith("\\") && !REGISTERED_BACKSLASH_COMMANDS.has(command)) {
      appendLine({ kind: "output", text: HELP_MAN_PAGE });
      return;
    }

    await runAgentChat(trimmed);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void runCommand(draft);
  };

  const inputDisabled = disabled || isRunning;

  return (
    <div
      className={`flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border font-mono text-[12px] ${shellClass}`}
      onClick={() => inputRef.current?.focus()}
    >
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain p-3">
        {lines.map((line) => {
          if (line.kind === "command") {
            return (
              <div key={line.id} className="flex flex-wrap items-start gap-1.5 whitespace-pre-wrap break-words">
                <span className={`inline-flex shrink-0 items-center gap-1.5 ${promptAccentClass}`}>
                  <MoonaIcon size={14} animated={false} />
                  <span className={promptSepClass}>&gt;&gt;</span>
                </span>
                <span className={commandTextClass}>{line.text}</span>
              </div>
            );
          }
          if (line.kind === "error") {
            return (
              <pre key={line.id} className={`whitespace-pre-wrap break-words ${errorClass}`}>
                {line.text}
              </pre>
            );
          }
          if (line.kind === "system") {
            return (
              <pre key={line.id} className={`whitespace-pre-wrap break-words ${systemClass}`}>
                {line.text}
              </pre>
            );
          }
          return (
            <pre key={line.id} className={`whitespace-pre-wrap break-words ${outputClass}`}>
              {line.text || (isRunning ? "…" : "")}
            </pre>
          );
        })}

        {!isRunning ? (
          <form onSubmit={handleSubmit} className="flex items-center gap-1.5">
            <span className={`inline-flex shrink-0 items-center gap-1.5 ${promptAccentClass}`}>
              <MoonaIcon size={14} />
              <span className={promptSepClass}>&gt;&gt;</span>
            </span>
            <input
              ref={inputRef}
              type="text"
              value={draft}
              disabled={inputDisabled}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "c" && event.ctrlKey) {
                  event.preventDefault();
                  abortRef.current?.abort();
                }
              }}
              className={inputClass}
              placeholder=""
              autoComplete="off"
              spellCheck={false}
              aria-label="무너코드 명령 입력"
            />
          </form>
        ) : (
          <div className={`flex items-center gap-1.5 ${runningClass}`}>
            <MoonaIcon size={14} />
            <span>실행 중… (Ctrl+C 중단)</span>
          </div>
        )}
      </div>
    </div>
  );
}
