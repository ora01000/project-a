import { useState } from "react";

import type { AgentRuntimeRecord } from "../../types/agentruntime";
import { assignableAgentId } from "../../types/agentruntime";
import type { WorkScriptType } from "../../types/workflow";
import { flushSseBuffer, parseSseChunk } from "../../utils/parseSse";
import type { WorkEditorNode } from "./workflowModel";

interface WorkNodeEditPanelProps {
  node: WorkEditorNode;
  assignedAgents: AgentRuntimeRecord[];
  runtimes: AgentRuntimeRecord[];
  userid: string;
  onChange: (patch: Partial<WorkEditorNode>) => void;
  onSave: () => void;
  onPersistPatch: (patch: Partial<WorkEditorNode>) => Promise<void>;
  onUploadFile: (file: File) => Promise<void>;
}

const ALLOWED_SCRIPT_TYPES = new Set(["yaml", "ansible", "cli"]);
const VALIDATABLE_SCRIPT_TYPES = new Set(["yaml", "ansible"]);

const SCRIPT_GENERATION_REQUIREMENTS = [
  "질의 요청사항에 대한 답변시 반드시 스크립트 결과물만 응답하며 스크립트의 내용 설명은 2줄 이내의 스크립트 주석으로 표현한다.",
  '다음 JSON 형식으로만 응답한다(다른 설명 문장 없이 JSON만 출력): {"script_type":"yaml 또는 ansible 또는 cli 중 1","work_script":"스크립트 내용(스크립트 설명에 대한 주석을 포함)"}',
].join("\n");

function buildScriptGenerationMessage(userPrompt: string): string {
  return `${userPrompt.trim()}\n\n[제반사항]\n${SCRIPT_GENERATION_REQUIREMENTS.split("\n")
    .map((item) => `- ${item}`)
    .join("\n")}`;
}

function extractJsonText(raw: string): string {
  const trimmed = raw.trim();
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]) {
    return fenced[1].trim();
  }
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start >= 0 && end > start) {
    return trimmed.slice(start, end + 1);
  }
  return trimmed;
}

function parseScriptGenerationPayload(raw: string): {
  scriptType: WorkScriptType;
  workScript: string;
} {
  const parsed = JSON.parse(extractJsonText(raw)) as {
    script_type?: unknown;
    work_script?: unknown;
    agent_response?: unknown;
  };
  const scriptType = String(parsed.script_type || "")
    .trim()
    .toLowerCase() as WorkScriptType;
  const workScript = String(parsed.work_script || parsed.agent_response || "").trim();
  if (!ALLOWED_SCRIPT_TYPES.has(scriptType)) {
    throw new Error("응답의 script_type이 yaml, ansible, cli 중 하나가 아닙니다.");
  }
  if (!workScript) {
    throw new Error("응답에 work_script 스크립트 내용이 없습니다.");
  }
  return { scriptType, workScript };
}

function parseValidationPayload(raw: string): { valid: boolean; message: string } {
  try {
    const parsed = JSON.parse(extractJsonText(raw)) as {
      valid?: unknown;
      message?: unknown;
    };
    if (typeof parsed.valid === "boolean") {
      return {
        valid: parsed.valid,
        message: String(parsed.message || (parsed.valid ? "검증 통과" : "검증 실패")),
      };
    }
  } catch {
    // fall through — treat raw text as message
  }
  const looksFailed = /\b(fail|error|invalid|오류|실패)\b/i.test(raw) && !/\b(pass|valid|성공|통과)\b/i.test(raw);
  return {
    valid: !looksFailed,
    message: raw.trim() || (looksFailed ? "검증 실패" : "검증 완료"),
  };
}

async function streamAgentChat(params: {
  agentId: string;
  userid: string;
  message: string;
}): Promise<string> {
  const response = await fetch(`/api/agents/${encodeURIComponent(params.agentId)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: params.message,
      userid: params.userid,
    }),
  });

  if (!response.ok) {
    throw new Error((await response.text()) || `HTTP ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("스트리밍 응답을 받지 못했습니다.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let assistantText = "";

  const applyEvents = (events: ReturnType<typeof parseSseChunk>["events"]) => {
    for (const event of events) {
      if (event.event === "error") {
        const payload = JSON.parse(event.data) as { message?: string };
        throw new Error(payload.message || "에이전트 호출에 실패했습니다.");
      }
      if (event.event !== "token") {
        continue;
      }
      const payload = JSON.parse(event.data) as { content: string };
      assistantText += payload.content;
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

  const finalText = assistantText.trim();
  if (!finalText) {
    throw new Error("에이전트가 빈 응답을 반환했습니다.");
  }
  return finalText;
}

function resolveChatAgentId(
  agent: AgentRuntimeRecord | undefined,
  fallbackLabel: string,
): string {
  if (!agent) {
    throw new Error(`${fallbackLabel}를 찾을 수 없습니다.`);
  }
  const agentId = assignableAgentId(agent);
  if (!agentId) {
    throw new Error(`${fallbackLabel} ID를 확인할 수 없습니다.`);
  }
  return agentId;
}

function buildValidationMessage(scriptType: string, script: string): string {
  if (scriptType === "ansible") {
    return [
      "다음 Ansible 스크립트에 대해 lint 검증을 수행하고, 가능하면 dry-run도 수행하라.",
      '결과는 다음 JSON만 출력한다: {"valid":true|false,"message":"요약"}',
      "",
      "```yaml",
      script,
      "```",
    ].join("\n");
  }
  return [
    "다음 YAML 스크립트에 대해 dry-run 검증을 수행하라.",
    '결과는 다음 JSON만 출력한다: {"valid":true|false,"message":"요약"}',
    "",
    "```yaml",
    script,
    "```",
  ].join("\n");
}

function fileLabel(name: string): string {
  return name.trim().split(/[/\\]/).pop() || "";
}

export function WorkNodeEditPanel({
  node,
  assignedAgents,
  runtimes,
  userid,
  onChange,
  onSave,
  onPersistPatch,
  onUploadFile,
}: WorkNodeEditPanelProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [validateMessage, setValidateMessage] = useState<string | null>(null);

  const hasGeneratedScript = Boolean(node.workScript.trim());

  const requestScriptGeneration = async () => {
    const prompt = node.userPrompt.trim();
    if (!prompt) {
      setGenerateError("작업 스크립트 생성 프롬프트를 입력하세요.");
      return;
    }
    if (node.targetAgent <= 0) {
      setGenerateError("대상 에이전트를 선택하세요.");
      return;
    }

    const agent = assignedAgents.find((item) => item.idx === node.targetAgent);
    let agentId: string;
    try {
      agentId = resolveChatAgentId(agent, "대상 에이전트");
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "대상 에이전트를 확인할 수 없습니다.");
      return;
    }

    setIsGenerating(true);
    setGenerateError(null);
    setValidateMessage(null);

    try {
      const raw = await streamAgentChat({
        agentId,
        userid,
        message: buildScriptGenerationMessage(prompt),
      });
      const parsed = parseScriptGenerationPayload(raw);
      await onPersistPatch({
        scriptType: parsed.scriptType,
        workScript: parsed.workScript,
        testResult: false,
      });
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "스크립트 작성 요청에 실패했습니다.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDeleteScript = async () => {
    setValidateMessage(null);
    setGenerateError(null);
    await onPersistPatch({
      workScript: "",
      scriptType: "",
      testResult: false,
    });
  };

  const handleValidateScript = async () => {
    const script = node.workScript.trim();
    const scriptType = String(node.scriptType || "")
      .trim()
      .toLowerCase();
    if (!script) {
      setValidateMessage("검증할 스크립트가 없습니다.");
      return;
    }
    if (scriptType === "cli") {
      setValidateMessage("cli 스크립트 자동 검증은 아직 지원하지 않습니다.");
      return;
    }
    if (!VALIDATABLE_SCRIPT_TYPES.has(scriptType)) {
      setValidateMessage("script_type이 yaml 또는 ansible이 아닙니다.");
      return;
    }

    let agent: AgentRuntimeRecord | undefined;
    if (scriptType === "ansible") {
      agent =
        assignedAgents.find(
          (item) =>
            item.local_agent_id === "ansible-lint" || item.agent_id === "ansible-lint",
        ) ||
        runtimes.find(
          (item) =>
            item.local_agent_id === "ansible-lint" || item.agent_id === "ansible-lint",
        ) ||
        assignedAgents.find((item) => item.idx === node.targetAgent);
    } else {
      agent = assignedAgents.find((item) => item.idx === node.targetAgent);
    }

    let agentId: string;
    try {
      agentId = resolveChatAgentId(
        agent,
        scriptType === "ansible" ? "ansible-lint 에이전트" : "대상 에이전트",
      );
    } catch (err) {
      setValidateMessage(err instanceof Error ? err.message : "검증 에이전트를 확인할 수 없습니다.");
      return;
    }

    setIsValidating(true);
    setValidateMessage(null);

    try {
      const raw = await streamAgentChat({
        agentId,
        userid,
        message: buildValidationMessage(scriptType, script),
      });
      const result = parseValidationPayload(raw);
      setValidateMessage(result.message);
      await onPersistPatch({ testResult: result.valid });
    } catch (err) {
      setValidateMessage(err instanceof Error ? err.message : "검증 요청에 실패했습니다.");
    } finally {
      setIsValidating(false);
    }
  };

  return (
    <div className={`grid min-h-0 flex-1 gap-3 ${hasGeneratedScript ? "md:grid-cols-2" : ""}`}>
      <div className="grid min-h-0 content-start gap-3 overflow-auto">
        <label className="grid gap-1 text-xs text-slate-400">
          작업명
          <input
            value={node.name}
            onChange={(event) => onChange({ name: event.target.value })}
            maxLength={100}
            className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </label>

        <label className="grid gap-1 text-xs text-slate-400">
          대상 에이전트
          {assignedAgents.length === 0 ? (
            <span className="text-sm text-slate-500">할당된 에이전트가 없습니다.</span>
          ) : (
            <select
              value={node.targetAgent || ""}
              onChange={(event) => {
                const idx = Number(event.target.value);
                const agent = assignedAgents.find((item) => item.idx === idx);
                onChange({
                  targetAgent: idx,
                  targetAgentName: agent?.agent_name ?? "",
                });
              }}
              className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            >
              <option value="">선택하세요</option>
              {assignedAgents.map((agent) => (
                <option key={agent.idx} value={agent.idx}>
                  {agent.agent_name}
                </option>
              ))}
            </select>
          )}
        </label>

        <label className="grid gap-1 text-xs text-slate-400">
          작업 설명
          <textarea
            value={node.description}
            onChange={(event) => onChange({ description: event.target.value })}
            rows={3}
            maxLength={500}
            className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
        </label>

        <label className="grid gap-1 text-xs text-slate-400">
          <span className="flex items-center justify-between gap-2">
            작업 스크립트 생성
            <button
              type="button"
              disabled={isGenerating}
              title="대상 에이전트에 스크립트 작성을 요청합니다"
              aria-label="작성요청"
              onClick={() => {
                void requestScriptGeneration();
              }}
              className="rounded-md border border-sky-700 bg-sky-950/50 px-2.5 py-1 text-[11px] font-medium text-sky-100 hover:bg-sky-900/60 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isGenerating ? "작성 중…" : "작성요청"}
            </button>
          </span>
          <textarea
            value={node.userPrompt}
            onChange={(event) => onChange({ userPrompt: event.target.value })}
            rows={4}
            placeholder="생성할 작업 스크립트에 대한 지시사항을 입력하세요"
            className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
          {generateError ? <span className="text-[11px] text-rose-300">{generateError}</span> : null}
        </label>

        <label className="grid gap-1 text-xs text-slate-400">
          파일 업로드
          <input
            type="file"
            className="text-sm text-slate-200"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                void onUploadFile(file);
                event.target.value = "";
              }
            }}
          />
          {node.files ? (
            <span className="text-xs text-slate-500">현재 파일: {fileLabel(node.files)}</span>
          ) : null}
        </label>

        <button
          type="button"
          onClick={onSave}
          className="w-fit rounded-md border border-sky-700 bg-sky-950/50 px-3 py-2 text-sm text-sky-100 hover:bg-sky-900/60"
        >
          저장
        </button>
      </div>

      {hasGeneratedScript ? (
        <section className="flex min-h-0 flex-col overflow-hidden rounded-md border border-slate-700 bg-slate-900/50">
          <header className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-700 px-3 py-2">
            <div className="min-w-0">
              <h4 className="text-xs font-semibold text-slate-200">생성된 스크립트</h4>
              {node.scriptType ? (
                <p className="truncate text-[10px] text-slate-500">script_type: {node.scriptType}</p>
              ) : null}
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                disabled={isValidating || isGenerating}
                onClick={() => {
                  void handleDeleteScript();
                }}
                className="rounded-md border border-rose-800 bg-rose-950/40 px-2.5 py-1 text-[11px] font-medium text-rose-100 hover:bg-rose-900/50 disabled:opacity-50"
              >
                삭제
              </button>
              <button
                type="button"
                disabled={isValidating || isGenerating}
                onClick={() => {
                  void handleValidateScript();
                }}
                className="rounded-md border border-emerald-700 bg-emerald-950/40 px-2.5 py-1 text-[11px] font-medium text-emerald-100 hover:bg-emerald-900/50 disabled:opacity-50"
              >
                {isValidating ? "검증 중…" : "검증"}
              </button>
            </div>
          </header>
          <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap px-3 py-2 text-[11px] text-slate-200">
            {node.workScript}
          </pre>
          {validateMessage ? (
            <p
              className={`shrink-0 border-t border-slate-700 px-3 py-2 text-[11px] ${
                node.testResult ? "text-emerald-300" : "text-amber-200"
              }`}
            >
              {validateMessage}
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
