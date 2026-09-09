import type { WorkNodeItem, WorkScriptType } from "../../types/workflow";

/** DB last_start_date / last_end_date 로 실행중 여부 판별 */
export function isRunInProgress(
  lastStartDate?: string | null,
  lastEndDate?: string | null,
): boolean {
  const start = (lastStartDate || "").trim();
  const end = (lastEndDate || "").trim();
  if (!start) {
    return false;
  }
  if (!end) {
    return true;
  }
  return start > end;
}

export type FailSpec =
  | { kind: "none" }
  | { kind: "end" }
  | { kind: "work"; clientId: string };

export type WorkEditorNode = {
  clientId: string;
  type: "work";
  uuid: string;
  name: string;
  description: string;
  targetAgent: number;
  targetAgentName: string;
  /** UI-only: not persisted (DB user_prompt removed). */
  userPrompt: string;
  workScript: string;
  scriptType: WorkScriptType | string;
  testResult: boolean;
  files: string;
  createDate: string;
  validateDate: string;
  lastStartDate: string;
  lastEndDate: string;
  lastSuccess: boolean;
  lastFailReason: string;
  usePreviousWorkResult: boolean;
  workReport: string;
  cron: boolean;
  cronExpr: string;
  scheduleWait: boolean;
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

const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

let clientSeq = 0;

export function nextClientId(prefix: string): string {
  clientSeq += 1;
  return `${prefix}-${clientSeq}`;
}

export function isUuidToken(value: string): boolean {
  return UUID_RE.test((value || "").trim());
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
    uuid: item.uuid || "",
    name: item.work_name,
    description: item.work_description || "",
    targetAgent: item.target_agent,
    targetAgentName: item.target_agent_name || "",
    userPrompt: "",
    workScript: item.work_script || "",
    scriptType: item.script_type === "yaml" ? "kubectl" : item.script_type || "",
    testResult: item.test_result,
    files: item.files,
    createDate: item.create_date || "",
    validateDate: item.validate_date || "",
    lastStartDate: item.last_start_date || "",
    lastEndDate: item.last_end_date || "",
    lastSuccess: Boolean(item.last_success),
    lastFailReason: item.last_fail_reason || "",
    usePreviousWorkResult: Boolean(item.use_previous_work_result),
    workReport: item.work_report || "",
    cron: Boolean(item.cron),
    cronExpr: (item.cron_expr || "0 9 * * *").slice(0, 20),
    scheduleWait: Boolean(item.schedule_wait),
  };
}

export function workNodeFromItem(
  item: WorkNodeItem,
  fail: FailSpec = { kind: "none" },
): WorkEditorNode {
  return {
    clientId: nextClientId(`W${item.uuid}`),
    type: "work",
    ...workFieldsFromItem(item),
    fail,
  };
}

export function workNodeWriteBody(
  node: WorkEditorNode,
  extras?: { validation_message?: string },
) {
  return {
    work_name: node.name,
    work_description: node.description,
    target_agent: node.targetAgent,
    work_script: node.workScript,
    script_type: node.scriptType || "",
    test_result: node.testResult,
    files: node.files,
    use_previous_work_result: node.usePreviousWorkResult,
    work_report: (node.workReport || "").trim().slice(0, 400),
    cron: Boolean(node.cron),
    cron_expr: (node.cronExpr || "0 9 * * *").slice(0, 20),
    ...(extras?.validation_message != null
      ? { validation_message: extras.validation_message }
      : {}),
  };
}

type ParsedToken =
  | { kind: "start" }
  | { kind: "end" }
  | { kind: "hitl"; userid: string }
  | { kind: "work"; workUuid: string; failWorkUuid?: string; failEnd?: boolean };

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
    const workUuid = token.slice(0, splitAt).trim();
    const fail = token.slice(splitAt + 1).trim();
    if (!isUuidToken(workUuid)) {
      throw new Error(`알 수 없는 작업 워크플로우 토큰: ${token}`);
    }
    if (fail.toUpperCase() === "E") {
      return { kind: "work", workUuid, failEnd: true };
    }
    if (!isUuidToken(fail)) {
      throw new Error(`알 수 없는 실패 토큰: ${token}`);
    }
    return { kind: "work", workUuid, failWorkUuid: fail.toLowerCase() };
  }
  if (isUuidToken(token)) {
    return { kind: "work", workUuid: token.toLowerCase() };
  }
  throw new Error(`알 수 없는 작업 워크플로우 토큰: ${token}`);
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
  const byUuid = new Map(workNodes.map((item) => [item.uuid.toLowerCase(), item]));
  const extras: Record<string, WorkEditorNode> = {};
  const extraByWorkUuid = new Map<string, string>();
  const main: EditorStep[] = [];

  const toWork = (workUuid: string, fail: FailSpec = { kind: "none" }): WorkEditorNode => {
    const key = workUuid.toLowerCase();
    const item = byUuid.get(key);
    if (item) {
      return workNodeFromItem(item, fail);
    }
    return {
      clientId: nextClientId(`W${key}`),
      type: "work",
      uuid: key,
      name: key,
      description: "",
      targetAgent: 0,
      targetAgentName: "",
      userPrompt: "",
      workScript: "",
      scriptType: "",
      testResult: false,
      files: "",
      createDate: "",
      validateDate: "",
      lastStartDate: "",
      lastEndDate: "",
      lastSuccess: false,
      lastFailReason: "",
      usePreviousWorkResult: false,
      workReport: "",
      cron: false,
      cronExpr: "0 9 * * *",
      scheduleWait: false,
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
    } else if (token.failWorkUuid) {
      const failKey = token.failWorkUuid.toLowerCase();
      let extraId = extraByWorkUuid.get(failKey);
      if (!extraId) {
        const extra = toWork(failKey);
        extraId = extra.clientId;
        extras[extraId] = extra;
        extraByWorkUuid.set(failKey, extraId);
      }
      fail = { kind: "work", clientId: extraId };
    }
    main.push(toWork(token.workUuid, fail));
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
    const uuid = step.uuid.toLowerCase();
    if (step.fail.kind === "end") {
      tokens.push(`${uuid}:E`);
    } else if (step.fail.kind === "work") {
      const failNode = workByClient(step.fail.clientId);
      tokens.push(failNode ? `${uuid}:${failNode.uuid.toLowerCase()}` : `${uuid}:E`);
    } else {
      tokens.push(uuid);
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
    if (step.type === "work" && !step.uuid.trim()) {
      return "작업노드 uuid가 없습니다.";
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
