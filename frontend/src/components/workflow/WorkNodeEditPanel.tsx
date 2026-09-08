import { useEffect, useState } from "react";

import type { AgentRuntimeRecord } from "../../types/agentruntime";
import { assignableAgentId } from "../../types/agentruntime";
import type { WorkScriptType } from "../../types/workflow";
import { WORK_SCRIPT_TYPE_OPTIONS } from "../../types/workflow";
import { flushSseBuffer, parseSseChunk } from "../../utils/parseSse";
import { JobReportEmailModal } from "../jobs/JobReportEmailModal";
import type { WorkEditorNode } from "./workflowModel";

interface WorkNodeEditPanelProps {
  node: WorkEditorNode;
  assignedAgents: AgentRuntimeRecord[];
  runtimes: AgentRuntimeRecord[];
  userid: string;
  onChange: (patch: Partial<WorkEditorNode>) => void;
  onSave: () => void;
  onPersistPatch: (
    patch: Partial<WorkEditorNode>,
    extras?: { validationMessage?: string },
  ) => Promise<void>;
  onUploadFile: (file: File) => Promise<void>;
}

const ALLOWED_SCRIPT_TYPES = new Set(["kubectl", "ansible", "cli", "prompt"]);

const SCRIPT_GENERATION_PREAMBLES: Record<Exclude<WorkScriptType, "">, string> = {
  prompt: [
    "다음 질의는 질의 자체에 결함이 없는지를 테스트하기 위함이며 절대 도구를 사용해서 작업을 수행하지 마세요.",
    "단 실제로 수행한다면 수행이 가능할지를 판단하고 다음에도 동일한 문구로 에이전트가 수행시 결과의 차이가 최소화 될 수 있도록 보완해 주세요.",
    "보완 수정된(또는 문제가 없다면 원문 그대로) 문구 외에는 어떤 결과도 덧붙이지 마세요.",
    '결과는 다음 형태로만 응답하세요: {"script_type":"prompt","work_script":"검토된 질의문"}',
  ].join(" "),
  kubectl: [
    "다음 질의를 분석하여 kubectl 명령어를 작성하시기 바랍니다.",
    "단, 절대 도구를 사용해서 작업을 수행하지 마세요.",
    "답변에는 생성된 kubectl 명령어 외 어떤 결과도 덧붙이지 마세요.",
    '결과는 다음 형태로만 응답하세요: {"script_type":"kubectl","work_script":"생성된 kubectl cli"}',
  ].join(" "),
  ansible: [
    "다음 질의를 분석하여 ansible playbook을 작성하시기 바랍니다.",
    "문법 체크를 위한 ansible-lint 만 허용하고 그 외 도구를 사용해서 작업을 수행하지 마세요.",
    "답변에는 생성된 playbook 외 어떤 결과도 덧붙이지 마세요.",
    '결과는 다음 형태로만 응답하세요: {"script_type":"ansible","work_script":"생성된 playbook"}',
  ].join(" "),
  cli: [
    "다음 질의를 분석하여 cli(bash) 명령어를 작성하시기 바랍니다.",
    "단, 절대 도구를 사용해서 작업을 수행하지 마세요.",
    "답변에는 생성된 bash script 외 어떤 결과도 덧붙이지 마세요.",
    '결과는 다음 형태로만 응답하세요: {"script_type":"cli","work_script":"생성된 bash script"}',
  ].join(" "),
};

function buildScriptGenerationMessage(scriptType: Exclude<WorkScriptType, "">, userPrompt: string): string {
  return `${SCRIPT_GENERATION_PREAMBLES[scriptType]}\n\n[질의]\n${userPrompt.trim()}`;
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
  const scriptTypeRaw = String(parsed.script_type || "")
    .trim()
    .toLowerCase();
  const scriptType = (
    scriptTypeRaw === "yaml" ? "kubectl" : scriptTypeRaw
  ) as WorkScriptType;
  const workScript = String(parsed.work_script || parsed.agent_response || "").trim();
  if (!ALLOWED_SCRIPT_TYPES.has(scriptType)) {
    throw new Error("응답의 script_type이 kubectl, ansible, cli, prompt 중 하나가 아닙니다.");
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
    const coerced = coerceValidationFlag(parsed.valid);
    if (coerced != null) {
      return {
        valid: coerced,
        message: String(parsed.message || (coerced ? "검증 통과" : "검증 실패")),
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

function coerceValidationFlag(value: unknown): boolean | null {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (value === 1) {
      return true;
    }
    if (value === 0) {
      return false;
    }
    return null;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "pass", "ok", "성공", "통과"].includes(normalized)) {
      return true;
    }
    if (["false", "0", "no", "fail", "실패"].includes(normalized)) {
      return false;
    }
  }
  return null;
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
  if (scriptType === "prompt") {
    return script;
  }
  if (scriptType === "ansible") {
    return [
      "다음 Ansible 스크립트에 대해 lint 검증을 수행하고, 가능하면 dry-run도 수행하라.",
      '결과는 다음 JSON만 출력한다: {"valid":true|false,"message":"실행결과"}',
      "",
      "```yaml",
      script,
      "```",
    ].join("\n");
  }
  if (scriptType === "kubectl") {
    return [
      "선제 조건문 : kubectl 명령어를 수행하기 전 get(ReadOnly) 인 경우는 바로 수행 가능하나 delete, edit, create, apply, patch 등 CUD 인 경우는 반드시 --dry-run 으로 수행 테스트만 진행한다. 결과는 다음 JSON만 출력한다.",
      '{"valid": true | false, "message": "실행결과"}',
      "",
      "다음 kubectl 명령어를 위 선제 조건에 따라 검증/수행하라.",
      "",
      "```bash",
      script,
      "```",
    ].join("\n");
  }
  return script;
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
  const [validateResult, setValidateResult] = useState<string | null>(null);
  const [isReportMailOpen, setIsReportMailOpen] = useState(false);

  const hasGeneratedScript = Boolean(node.workScript.trim());

  useEffect(() => {
    let cancelled = false;
    const shouldLoad =
      Boolean(node.uuid) && node.testResult && Boolean(node.validateDate.trim());

    if (!shouldLoad) {
      setValidateMessage(null);
      setValidateResult(null);
      return () => {
        cancelled = true;
      };
    }

    setValidateMessage(null);
    setValidateResult(null);

    void (async () => {
      try {
        const response = await fetch(`/api/work-nodes/${node.uuid}/validation-result`);
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as { content?: string };
        if (cancelled) {
          return;
        }
        const content = String(payload.content ?? "").trim();
        if (!content) {
          return;
        }
        setValidateMessage("저장된 검증 결과를 불러왔습니다.");
        setValidateResult(content);
      } catch {
        // Keep panel quiet when prior result file is unavailable.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [node.uuid, node.testResult, node.validateDate]);

  const requestScriptGeneration = async () => {
    const prompt = node.userPrompt.trim();
    if (!prompt) {
      setGenerateError("작업 스크립트 생성 프롬프트를 입력하세요.");
      return;
    }
    const selectedType = String(node.scriptType || "")
      .trim()
      .toLowerCase();
    const normalizedType = (selectedType === "yaml" ? "kubectl" : selectedType) as WorkScriptType;
    if (!ALLOWED_SCRIPT_TYPES.has(normalizedType)) {
      setGenerateError("스크립트 종류를 선택하세요.");
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
    setValidateResult(null);

    try {
      const raw = await streamAgentChat({
        agentId,
        userid,
        message: buildScriptGenerationMessage(
          normalizedType as Exclude<WorkScriptType, "">,
          prompt,
        ),
      });
      const parsed = parseScriptGenerationPayload(raw);
      await onPersistPatch({
        scriptType: parsed.scriptType || normalizedType,
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
    setValidateResult(null);
    setGenerateError(null);
    await onPersistPatch({
      workScript: "",
      scriptType: "",
      testResult: false,
    });
  };

  const handleScriptTypeChange = async (nextType: WorkScriptType) => {
    setValidateMessage(null);
    setValidateResult(null);
    onChange({ scriptType: nextType, testResult: false });
    await onPersistPatch({ scriptType: nextType, testResult: false });
  };

  const handleValidateScript = async () => {
    const script = node.workScript.trim();
    const scriptType = String(node.scriptType || "")
      .trim()
      .toLowerCase();
    if (!script) {
      setValidateMessage("검증할 스크립트가 없습니다.");
      setValidateResult(null);
      return;
    }
    if (scriptType === "cli") {
      setValidateMessage("cli 스크립트 자동 검증은 아직 지원하지 않습니다.");
      setValidateResult(null);
      return;
    }
    if (scriptType !== "kubectl" && scriptType !== "ansible" && scriptType !== "prompt") {
      setValidateMessage("script_type이 kubectl, ansible, prompt 중 하나가 아닙니다.");
      setValidateResult(null);
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
      setValidateResult(null);
      return;
    }

    setIsValidating(true);
    setValidateMessage(null);
    setValidateResult(null);

    try {
      const raw = await streamAgentChat({
        agentId,
        userid,
        message: buildValidationMessage(scriptType, script),
      });
      if (scriptType === "prompt") {
        const responseText = raw.trim() || "(빈 응답)";
        setValidateMessage("대상 에이전트 응답을 수신했습니다.");
        setValidateResult(responseText);
        await onPersistPatch(
          { testResult: true },
          { validationMessage: responseText },
        );
      } else {
        const result = parseValidationPayload(raw);
        setValidateMessage(result.message);
        setValidateResult(raw.trim() || result.message);
        await onPersistPatch(
          { testResult: result.valid },
          result.valid ? { validationMessage: result.message } : undefined,
        );
      }
    } catch (err) {
      setValidateMessage(err instanceof Error ? err.message : "검증 요청에 실패했습니다.");
      setValidateResult(null);
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

        <label className="flex cursor-pointer items-start gap-2 rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={node.usePreviousWorkResult}
            disabled={isGenerating || isValidating}
            onChange={(event) => {
              const next = event.target.checked;
              onChange({ usePreviousWorkResult: next });
              void onPersistPatch({ usePreviousWorkResult: next });
            }}
            className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-slate-600 bg-slate-900 text-sky-500 focus:ring-sky-600"
          />
          <span className="grid gap-0.5">
            <span className="font-medium text-slate-200">이전 작업 결과 사용</span>
            <span className="text-[11px] text-slate-500">
              직전 work_node 의 검증/실행 결과 파일을 이 작업 입력으로 사용합니다.
            </span>
          </span>
        </label>

        <div className="grid gap-1 text-xs text-slate-400">
          <span className="flex flex-wrap items-center justify-between gap-2">
            결과보고 메일
            <button
              type="button"
              disabled={isGenerating || isValidating}
              onClick={() => setIsReportMailOpen(true)}
              className="rounded-md border border-emerald-700/80 bg-emerald-950/40 px-2.5 py-1 text-[11px] font-medium text-emerald-100 hover:bg-emerald-900/50 disabled:opacity-50"
            >
              수신자 선택
            </button>
          </span>
          {node.workReport.trim() ? (
            <div className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-[11px] text-slate-200">
              {node.workReport
                .split(";")
                .map((part) => part.trim())
                .filter(Boolean)
                .join(", ")}
            </div>
          ) : (
            <p className="rounded-md border border-dashed border-slate-700 bg-slate-950/40 px-3 py-2 text-[11px] text-slate-500">
              선택된 수신자가 없습니다.
            </p>
          )}
          <span className="text-[11px] text-slate-500">
            수신자가 있으면 작업 완료 후 결과를 메일로 전송합니다.
          </span>
        </div>

        {isReportMailOpen ? (
          <JobReportEmailModal
            pickMode={{
              initialEmails: node.workReport,
              title: "결과보고 메일 수신자",
              confirmLabel: "적용",
              maxLength: 200,
              onConfirm: (emailsJoined) => {
                onChange({ workReport: emailsJoined });
                void onPersistPatch({ workReport: emailsJoined });
              },
            }}
            onClose={() => setIsReportMailOpen(false)}
          />
        ) : null}

        <label className="grid gap-1 text-xs text-slate-400">
          <span className="flex flex-wrap items-center justify-between gap-2">
            작업 스크립트 생성
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="flex items-center gap-1.5 text-[11px] text-slate-400">
                스크립트 종류
                <select
                  value={
                    WORK_SCRIPT_TYPE_OPTIONS.some((item) => item.value === node.scriptType)
                      ? node.scriptType
                      : ""
                  }
                  disabled={isGenerating || isValidating}
                  onChange={(event) => {
                    const next = event.target.value as WorkScriptType;
                    onChange({ scriptType: next, testResult: false });
                  }}
                  className="rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-[11px] text-slate-100 disabled:opacity-50"
                >
                  <option value="" disabled>
                    선택
                  </option>
                  {WORK_SCRIPT_TYPE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </span>
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
          </span>
          <textarea
            value={node.userPrompt}
            onChange={(event) => onChange({ userPrompt: event.target.value })}
            rows={4}
            placeholder={
              node.scriptType === "prompt"
                ? "대상 에이전트에 전달할 자연어 질의를 입력하세요"
                : "생성할 작업 스크립트에 대한 지시사항을 입력하세요"
            }
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
          <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-700 px-3 py-2">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h4 className="text-xs font-semibold text-slate-200">생성된 스크립트</h4>
              <label className="flex items-center gap-1.5 text-[11px] text-slate-400">
                스크립트 종류
                <select
                  value={
                    WORK_SCRIPT_TYPE_OPTIONS.some((item) => item.value === node.scriptType)
                      ? node.scriptType
                      : ""
                  }
                  disabled={isValidating || isGenerating}
                  onChange={(event) => {
                    const next = event.target.value as WorkScriptType;
                    void handleScriptTypeChange(next);
                  }}
                  className="rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-[11px] text-slate-100 disabled:opacity-50"
                >
                  <option value="" disabled>
                    선택
                  </option>
                  {WORK_SCRIPT_TYPE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {node.testResult ? (
                <span
                  className="inline-flex items-center gap-1 text-[11px] text-emerald-300"
                  title={node.validateDate ? `검증 시각: ${node.validateDate}` : "검증 완료"}
                >
                  <span aria-hidden>✓</span>
                  {node.validateDate ? (
                    <span className="tabular-nums text-emerald-200/90">{node.validateDate}</span>
                  ) : null}
                </span>
              ) : null}
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
                title="검증 실행"
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
          {validateMessage || validateResult ? (
            <div className="shrink-0 border-t border-slate-700">
              {validateMessage ? (
                <p
                  className={`px-3 py-2 text-[11px] ${
                    node.testResult ? "text-emerald-300" : "text-amber-200"
                  }`}
                >
                  {validateMessage}
                </p>
              ) : null}
              {validateResult ? (
                <div className="border-t border-slate-800 bg-slate-950/60 px-3 py-2">
                  <h5 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    응답 결과
                  </h5>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-[11px] text-slate-200">
                    {validateResult}
                  </pre>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
