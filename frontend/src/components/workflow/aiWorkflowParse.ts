import type { WorkScriptType } from "../../types/workflow";

export type AiWorkNodeDraft = {
  logicalId: string;
  work_name: string;
  work_description: string;
  target_agent: string;
  work_script: string;
  script_type: WorkScriptType | string;
};

export type AiWorkflowDesignPayload = {
  work_nodes: AiWorkNodeDraft[];
  workflow_name: string;
  workflow_description: string;
  workflow: string;
};

const SCRIPT_TYPES = new Set(["yaml", "ansible", "cli"]);
/** Logical work IDs in AI JSON (mapped to DB integer idx on import). */
const LOGICAL_ID_RE = /^[a-zA-Z0-9_-]{4,64}$/;

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
  const work_nodes: AiWorkNodeDraft[] = workList.map((item, index) => {
    if (!item || typeof item !== "object") {
      throw new Error(`work_node[${index}] 형식이 올바르지 않습니다.`);
    }
    const row = item as Record<string, unknown>;
    const logicalId = asString(row.idx);
    if (!LOGICAL_ID_RE.test(logicalId)) {
      throw new Error(
        `work_node.idx('${logicalId || "(빈 값)"}')는 /^[a-zA-Z0-9_-]{4,64}$/ 형식이어야 합니다.`,
      );
    }
    if (seen.has(logicalId)) {
      throw new Error(`중복된 work_node.idx: ${logicalId}`);
    }
    seen.add(logicalId);

    const scriptType = asString(row.script_type).toLowerCase();
    if (scriptType && !SCRIPT_TYPES.has(scriptType)) {
      throw new Error(`script_type은 yaml|ansible|cli 중 하나여야 합니다: ${scriptType}`);
    }

    return {
      logicalId,
      work_name: asString(row.work_name) || logicalId,
      work_description: asString(row.work_description),
      target_agent: asString(row.target_agent),
      work_script: asString(row.work_script),
      script_type: scriptType,
    };
  });

  const workflow = asString(workflowObj.workflow);
  if (!workflow) {
    throw new Error("workflow.workflow 표현식이 비어 있습니다.");
  }

  return {
    work_nodes,
    workflow_name: asString(workflowObj.workflow_name) || "AI 생성 워크플로우",
    workflow_description: asString(workflowObj.workflow_description),
    workflow,
  };
}

export function remapWorkflowExpression(
  expression: string,
  logicalToDbIdx: Record<string, number>,
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
    if (Object.prototype.hasOwnProperty.call(logicalToDbIdx, key)) {
      return String(logicalToDbIdx[key]);
    }
    // Already a DB integer
    if (/^\d+$/.test(key)) {
      return key;
    }
    throw new Error(`표현식의 작업 ID '${key}'를 DB idx로 매핑하지 못했습니다.`);
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
