import type { WorkNodeItem, WorkScriptType } from "../../types/workflow";

export type FailSpec =
  | { kind: "none" }
  | { kind: "end" }
  | { kind: "work"; clientId: string };

export type WorkEditorNode = {
  clientId: string;
  type: "work";
  idx: number;
  uuid: string;
  name: string;
  description: string;
  targetAgent: number;
  targetAgentName: string;
  userPrompt: string;
  agentResponse: string;
  scriptType: WorkScriptType | string;
  testResult: boolean;
  files: string;
  createDate: string;
  validateDate: string;
  fail: FailSpec;
};

export type EditorStep =
  | { clientId: string; type: "start" }
  | { clientId: string; type: "end" }
  | { clientId: string; type: "hitl"; userid: string; username: string }
  | WorkEditorNode;

export type EditorModel = {
  main: EditorStep[];
  extras: Record<string, WorkEditorNode>;
};

let clientSeq = 0;

export function nextClientId(prefix: string): string {
  clientSeq += 1;
  return `${prefix}-${clientSeq}`;
}

export function emptyEditorModel(): EditorModel {
  return {
    main: [
      { clientId: nextClientId("S"), type: "start" },
      { clientId: nextClientId("E"), type: "end" },
    ],
    extras: {},
  };
}

export function workFieldsFromItem(
  item: WorkNodeItem,
): Omit<WorkEditorNode, "clientId" | "type" | "fail"> {
  return {
    idx: item.idx,
    uuid: item.uuid || "",
    name: item.work_name,
    description: item.work_description || "",
    targetAgent: item.target_agent,
    targetAgentName: item.target_agent_name || "",
    userPrompt: item.user_prompt,
    agentResponse: item.agent_response,
    scriptType: item.script_type || "",
    testResult: item.test_result,
    files: item.files,
    createDate: item.create_date || "",
    validateDate: item.validate_date || "",
  };
}

export function workNodeFromItem(
  item: WorkNodeItem,
  fail: FailSpec = { kind: "none" },
): WorkEditorNode {
  return {
    clientId: nextClientId(`W${item.idx}`),
    type: "work",
    ...workFieldsFromItem(item),
    fail,
  };
}

export function workNodeWriteBody(node: WorkEditorNode) {
  return {
    work_name: node.name,
    work_description: node.description,
    target_agent: node.targetAgent,
    user_prompt: node.userPrompt,
    agent_response: node.agentResponse,
    script_type: node.scriptType || "",
    test_result: node.testResult,
    files: node.files,
  };
}

type ParsedToken =
  | { kind: "start" }
  | { kind: "end" }
  | { kind: "hitl"; userid: string }
  | { kind: "work"; workIdx: number; failWorkIdx?: number; failEnd?: boolean };

function parseToken(raw: string): ParsedToken {
  const token = raw.trim();
  const upper = token.toUpperCase();
  if (upper === "S") {
    return { kind: "start" };
  }
  if (upper === "E") {
    return { kind: "end" };
  }
  if (token.toUpperCase().startsWith("H:")) {
    return { kind: "hitl", userid: token.slice(token.indexOf(":") + 1).trim() };
  }
  if (token.includes(":")) {
    const splitAt = token.indexOf(":");
    const workIdx = Number(token.slice(0, splitAt));
    const fail = token.slice(splitAt + 1).trim();
    if (fail.toUpperCase() === "E") {
      return { kind: "work", workIdx, failEnd: true };
    }
    return { kind: "work", workIdx, failWorkIdx: Number(fail) };
  }
  if (/^\d+$/.test(token)) {
    return { kind: "work", workIdx: Number(token) };
  }
  throw new Error(`알 수 없는 워크플로우 토큰: ${token}`);
}

export function parseExpression(expression: string): ParsedToken[] {
  const text = (expression || "").trim();
  if (!text) {
    return [];
  }
  return text
    .split("->")
    .map((part) => part.trim())
    .filter(Boolean)
    .map(parseToken);
}

export function hydrateEditor(
  expression: string,
  workNodes: WorkNodeItem[],
  userNames: Record<string, string>,
): EditorModel {
  const tokens = parseExpression(expression);
  if (tokens.length === 0) {
    return emptyEditorModel();
  }
  const byIdx = new Map(workNodes.map((item) => [item.idx, item]));
  const extras: Record<string, WorkEditorNode> = {};
  const extraByWorkIdx = new Map<number, string>();
  const main: EditorStep[] = [];

  const toWork = (idx: number, fail: FailSpec = { kind: "none" }): WorkEditorNode => {
    const item = byIdx.get(idx);
    if (item) {
      return workNodeFromItem(item, fail);
    }
    return {
      clientId: nextClientId(`W${idx}`),
      type: "work",
      idx,
      uuid: "",
      name: String(idx),
      description: "",
      targetAgent: 0,
      targetAgentName: "",
      userPrompt: "",
      agentResponse: "",
      scriptType: "",
      testResult: false,
      files: "",
      createDate: "",
      validateDate: "",
      fail,
    };
  };

  for (const token of tokens) {
    if (token.kind === "start") {
      main.push({ clientId: nextClientId("S"), type: "start" });
      continue;
    }
    if (token.kind === "end") {
      main.push({ clientId: nextClientId("E"), type: "end" });
      continue;
    }
    if (token.kind === "hitl") {
      main.push({
        clientId: nextClientId("H"),
        type: "hitl",
        userid: token.userid,
        username: userNames[token.userid] || token.userid,
      });
      continue;
    }
    let fail: FailSpec = { kind: "none" };
    if (token.failEnd) {
      fail = { kind: "end" };
    } else if (token.failWorkIdx != null && Number.isFinite(token.failWorkIdx)) {
      let extraId = extraByWorkIdx.get(token.failWorkIdx);
      if (!extraId) {
        const extra = toWork(token.failWorkIdx);
        extraId = extra.clientId;
        extras[extraId] = extra;
        extraByWorkIdx.set(token.failWorkIdx, extraId);
      }
      fail = { kind: "work", clientId: extraId };
    }
    main.push(toWork(token.workIdx, fail));
  }

  if (main.length === 0 || main[0].type !== "start") {
    main.unshift({ clientId: nextClientId("S"), type: "start" });
  }
  return { main, extras };
}

export function serializeEditor(model: EditorModel): string {
  const workByClient = (clientId: string): WorkEditorNode | undefined => {
    if (model.extras[clientId]) {
      return model.extras[clientId];
    }
    const found = model.main.find((step) => step.clientId === clientId);
    return found?.type === "work" ? found : undefined;
  };

  const tokens: string[] = [];
  for (const step of model.main) {
    if (step.type === "start") {
      tokens.push("S");
      continue;
    }
    if (step.type === "end") {
      tokens.push("E");
      continue;
    }
    if (step.type === "hitl") {
      tokens.push(`H:${step.userid}`);
      continue;
    }
    if (step.fail.kind === "end") {
      tokens.push(`${step.idx}:E`);
    } else if (step.fail.kind === "work") {
      const failNode = workByClient(step.fail.clientId);
      tokens.push(failNode ? `${step.idx}:${failNode.idx}` : `${step.idx}:E`);
    } else {
      tokens.push(String(step.idx));
    }
  }
  if (tokens.length === 0) {
    return "S->E";
  }
  if (tokens[0] !== "S") {
    tokens.unshift("S");
  }
  if (tokens[tokens.length - 1] !== "E") {
    tokens.push("E");
  }
  return tokens.join("->");
}

export function validateEditor(model: EditorModel): string | null {
  for (const step of model.main) {
    if (step.type === "hitl" && !step.userid.trim()) {
      return "승인자를 지정하세요.";
    }
    if (step.type === "work" && step.fail.kind === "work" && !model.extras[step.fail.clientId]) {
      return "실패시 작업노드가 올바르지 않습니다.";
    }
  }
  return null;
}

export function insertAfter(model: EditorModel, clientId: string, step: EditorStep): EditorModel {
  const index = model.main.findIndex((item) => item.clientId === clientId);
  if (index < 0) {
    return model;
  }
  const main = [...model.main];
  main.splice(index + 1, 0, step);
  return { ...model, main };
}

export function terminateAfter(model: EditorModel, clientId: string): EditorModel {
  const index = model.main.findIndex((item) => item.clientId === clientId);
  if (index < 0) {
    return model;
  }
  const main = model.main.slice(0, index + 1);
  if (main[main.length - 1]?.type !== "end") {
    main.push({ clientId: nextClientId("E"), type: "end" });
  }
  const used = new Set(
    main
      .filter((step): step is WorkEditorNode => step.type === "work" && step.fail.kind === "work")
      .map((step) => (step.fail.kind === "work" ? step.fail.clientId : "")),
  );
  const extras = Object.fromEntries(
    Object.entries(model.extras).filter(([id]) => used.has(id)),
  );
  return { main, extras };
}

export function updateWork(
  model: EditorModel,
  clientId: string,
  patch: Partial<WorkEditorNode>,
): EditorModel {
  const apply = (node: WorkEditorNode): WorkEditorNode => ({ ...node, ...patch, clientId, type: "work" });
  if (model.extras[clientId]) {
    return { ...model, extras: { ...model.extras, [clientId]: apply(model.extras[clientId]) } };
  }
  return {
    ...model,
    main: model.main.map((step) => (step.clientId === clientId && step.type === "work" ? apply(step) : step)),
  };
}

export function setFailWork(
  model: EditorModel,
  workClientId: string,
  failNode: WorkEditorNode,
): EditorModel {
  const extras = { ...model.extras, [failNode.clientId]: failNode };
  const main = model.main.map((step) => {
    if (step.clientId !== workClientId || step.type !== "work") {
      return step;
    }
    return { ...step, fail: { kind: "work" as const, clientId: failNode.clientId } };
  });
  return { main, extras };
}

function pruneExtras(model: EditorModel): EditorModel {
  const used = new Set(
    model.main
      .filter((step): step is WorkEditorNode => step.type === "work" && step.fail.kind === "work")
      .map((step) => (step.fail.kind === "work" ? step.fail.clientId : "")),
  );
  return {
    ...model,
    extras: Object.fromEntries(Object.entries(model.extras).filter(([id]) => used.has(id))),
  };
}

/** 시작/종료를 제외한 워크·승인자(실패 분기 포함) 노드를 다이어그램에서 제거한다. */
export function removeNode(model: EditorModel, clientId: string): EditorModel {
  if (model.extras[clientId]) {
    const main = model.main.map((step) => {
      if (step.type !== "work" || step.fail.kind !== "work" || step.fail.clientId !== clientId) {
        return step;
      }
      return { ...step, fail: { kind: "none" as const } };
    });
    const extras = { ...model.extras };
    delete extras[clientId];
    return { main, extras };
  }

  const target = model.main.find((step) => step.clientId === clientId);
  if (!target || target.type === "start" || target.type === "end") {
    return model;
  }

  const main = model.main.filter((step) => step.clientId !== clientId);
  return pruneExtras({ ...model, main });
}
