import type { WorkScriptType } from "../../types/workflow";

export type AiWorkNodeDraft = {
  /** Opaque link token from AI (`work_id` / `idx` / ignored `uuid`); used only for expression remap. */
  logicalId: string;
  /** Platform-assigned UUID (AI `uuid` is ignored). */
  uuid: string;
  work_name: string;
  work_description: string;
  target_agent: string;
  work_script: string;
  script_type: WorkScriptType | string;
  use_previous_work_result: boolean;
  work_report: string;
};

export type AiWorkflowDesignPayload = {
  work_nodes: AiWorkNodeDraft[];
  workflow_uuid: string;
  workflow_name: string;
  workflow_description: string;
  workflow: string;
};

const SCRIPT_TYPES = new Set(["kubectl", "ansible", "cli", "prompt"]);
/** Prefer short logical ids from the agent; also accept opaque tokens (incl. guardrail-masked text). */
const LOGICAL_ID_RE = /^[^\s]{1,200}$/;

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

function asString(value: unknown): string {
  return String(value ?? "").trim();
}

function asBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  const text = asString(value).toLowerCase();
  if (text === "true" || text === "1" || text === "yes") {
    return true;
  }
  if (text === "false" || text === "0" || text === "no") {
    return false;
  }
  return fallback;
}

function asWorkReport(value: unknown): string {
  const text = asString(value);
  if (!text || text === "-" || text === "공백" || text.toLowerCase() === "none") {
    return "";
  }
  return text.slice(0, 200);
}

function newUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
    const n = (Math.random() * 16) | 0;
    const v = ch === "x" ? n : (n & 0x3) | 0x8;
    return v.toString(16);
  });
}

function resolveLogicalId(row: Record<string, unknown>, index: number): string {
  const candidates = [row.work_id, row.idx, row.uuid];
  for (const candidate of candidates) {
    const text = asString(candidate);
    if (text && LOGICAL_ID_RE.test(text)) {
      return text;
    }
  }
  return `work_${index + 1}`;
}

function rewriteLogicalTokens(text: string, idToUuid: Record<string, string>): string {
  if (!text) {
    return text;
  }
  const keys = Object.keys(idToUuid).sort((left, right) => right.length - left.length);
  let out = text;
  for (const key of keys) {
    if (!key) {
      continue;
    }
    out = out.split(key).join(idToUuid[key]);
  }
  return out;
}

export function parseAiWorkflowDesignResponse(raw: string): AiWorkflowDesignPayload {
  let parsed: unknown;
  try {
    parsed = JSON.parse(extractJsonText(raw));
  } catch {
    throw new Error("AI 응답이 JSON 형식이 아닙니다. 보충 질문이거나 파싱에 실패했습니다.");
  }

  if (!parsed || typeof parsed !== "object") {
    throw new Error("AI 응답 JSON이 올바르지 않습니다.");
  }

  const root = parsed as Record<string, unknown>;
  const workList = root.work_node ?? root.work;
  if (!Array.isArray(workList) || workList.length === 0) {
    throw new Error("AI 응답에 work_node 배열이 없습니다.");
  }

  const workflowObj =
    root.workflow && typeof root.workflow === "object"
      ? (root.workflow as Record<string, unknown>)
      : null;
  if (!workflowObj) {
    throw new Error("AI 응답에 workflow 객체가 없습니다.");
  }

  const seen = new Set<string>();
  const idToUuid: Record<string, string> = {};
  const drafts: Array<{
    logicalId: string;
    uuid: string;
    work_name: string;
    work_description: string;
    target_agent: string;
    work_script: string;
    script_type: string;
    use_previous_work_result: boolean;
    work_report: string;
  }> = [];

  workList.forEach((item, index) => {
    if (!item || typeof item !== "object") {
      throw new Error(`work_node[${index}] 형식이 올바르지 않습니다.`);
    }
    const row = item as Record<string, unknown>;
    const logicalId = resolveLogicalId(row, index);
    if (seen.has(logicalId)) {
      throw new Error(`중복된 work_node 식별자: ${logicalId}`);
    }
    seen.add(logicalId);

    const scriptTypeRaw = asString(row.script_type).toLowerCase();
    const scriptType = scriptTypeRaw === "yaml" ? "kubectl" : scriptTypeRaw;
    if (scriptType && !SCRIPT_TYPES.has(scriptType)) {
      throw new Error(`script_type은 kubectl|ansible|cli|prompt 중 하나여야 합니다: ${scriptType}`);
    }

    const uuid = newUuid();
    idToUuid[logicalId] = uuid;
    drafts.push({
      logicalId,
      uuid,
      work_name: asString(row.work_name) || logicalId,
      work_description: asString(row.work_description),
      target_agent: asString(row.target_agent),
      work_script: asString(row.work_script),
      script_type: scriptType,
      use_previous_work_result: asBoolean(row.use_previous_work_result, false),
      work_report: asWorkReport(row.work_report),
    });
  });

  const workflowRaw = asString(workflowObj.workflow);
  if (!workflowRaw) {
    throw new Error("workflow.workflow 표현식이 비어 있습니다.");
  }

  const work_nodes: AiWorkNodeDraft[] = drafts.map((draft) => ({
    ...draft,
    work_script: rewriteLogicalTokens(draft.work_script, idToUuid),
  }));

  return {
    work_nodes,
    workflow_uuid: newUuid(),
    workflow_name: asString(workflowObj.workflow_name) || "AI 생성 작업 워크플로우",
    workflow_description: asString(workflowObj.workflow_description),
    workflow: remapWorkflowExpression(workflowRaw, idToUuid),
  };
}

/** Map expression work-token ids to persisted work_node.uuid values. */
export function remapWorkflowExpression(
  expression: string,
  idToUuid: Record<string, string>,
): string {
  const parts = expression
    .split("->")
    .map((part) => part.trim())
    .filter(Boolean);

  const mapId = (raw: string): string => {
    const key = raw.trim();
    if (!key) {
      throw new Error("빈 작업 ID가 표현식에 있습니다.");
    }
    if (Object.prototype.hasOwnProperty.call(idToUuid, key)) {
      return idToUuid[key];
    }
    const lowered = key.toLowerCase();
    const hit = Object.entries(idToUuid).find(([logical]) => logical.toLowerCase() === lowered);
    if (hit) {
      return hit[1];
    }
    throw new Error(`표현식의 작업 ID '${key}'를 work_node 식별자로 매핑하지 못했습니다.`);
  };

  return parts
    .map((token) => {
      const upper = token.toUpperCase();
      if (upper === "S" || upper === "E") {
        return upper;
      }
      if (token.toUpperCase().startsWith("H:")) {
        return token;
      }
      const colon = token.indexOf(":");
      if (colon >= 0) {
        const left = token.slice(0, colon).trim();
        const right = token.slice(colon + 1).trim();
        if (right.toUpperCase() === "E") {
          return `${mapId(left)}:E`;
        }
        return `${mapId(left)}:${mapId(right)}`;
      }
      return mapId(token);
    })
    .join("->");
}
