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

export type HitlEditorNode = {
  clientId: string;
  type: "hitl";
  uuid: string;
  userid: string;
  username: string;
  name: string;
  description: string;
  upload: boolean;
  uploadPath: string;
};

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
  worker: "agent" | "hitl" | string;
  upload: boolean;
  uploadPath: string;
  approverUserid: string;
  fail: FailSpec;
};

export type EditorStep =
  | { clientId: string; type: "start" }
  | { clientId: string; type: "end" }
  | HitlEditorNode
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
    worker: (item.worker || "agent") as "agent" | "hitl" | string,
    upload: Boolean(item.upload),
    uploadPath: item.upload_path || "",
    approverUserid: item.approver_userid || "",
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
    worker: node.worker || "agent",
    upload: Boolean(node.upload),
    upload_path: node.uploadPath || "",
    approver_userid: node.approverUserid || "",
    ...(extras?.validation_message != null
      ? { validation_message: extras.validation_message }
      : {}),
  };
}

export function hitlNodeWriteBody(node: HitlEditorNode) {
  return {
    work_name: node.name || `결재승인 (${node.userid})`,
    work_description: node.description || "",
    target_agent: 0,
    work_script: "",
    script_type: "",
    test_result: false,
    files: "",
    use_previous_work_result: false,
    work_report: "",
    cron: false,
    cron_expr: "0 9 * * *",
    worker: "hitl",
    upload: Boolean(node.upload),
    upload_path: "",
    approver_userid: node.userid || "",
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
  if (text.startsWith("{")) {
    return parseJsonExpression(text);
  }
  return text
    .split("->")
    .map((part) => part.trim())
    .filter(Boolean)
    .map(parseToken);
}

function parseJsonExpression(raw: string): ParsedToken[] {
  const data = JSON.parse(raw) as {
    nodes?: unknown;
    edges?: Array<{ from?: string; to?: string; source?: string; target?: string; kind?: string }>;
  };
  const edges = Array.isArray(data.edges) ? data.edges : [];
  const successNext = new Map<string, string>();
  const failNext = new Map<string, string>();
  for (const edge of edges) {
    const from = String(edge.from || edge.source || "").trim();
    const to = String(edge.to || edge.target || "").trim();
    const kind = String(edge.kind || "success").trim().toLowerCase() || "success";
    if (!from || !to) {
      continue;
    }
    const fromKey = isUuidToken(from) ? from.toLowerCase() : from;
    const toKey = isUuidToken(to) ? to.toLowerCase() : to;
    if (kind === "fail") {
      failNext.set(fromKey, toKey);
    } else {
      successNext.set(fromKey, toKey);
    }
  }
  if (!successNext.has("S")) {
    throw new Error("workflow JSON 에 S success edge 가 없습니다.");
  }
  const tokens: ParsedToken[] = [{ kind: "start" }];
  let current = successNext.get("S") || "E";
  const visited = new Set<string>();
  while (current.toUpperCase() !== "E") {
    if (visited.has(current)) {
      throw new Error("workflow success 경로에 순환이 있습니다.");
    }
    visited.add(current);
    if (!isUuidToken(current)) {
      throw new Error(`알 수 없는 workflow 노드: ${current}`);
    }
    const failTarget = failNext.get(current);
    if (failTarget?.toUpperCase() === "E") {
      tokens.push({ kind: "work", workUuid: current.toLowerCase(), failEnd: true });
    } else if (failTarget && isUuidToken(failTarget)) {
      tokens.push({
        kind: "work",
        workUuid: current.toLowerCase(),
        failWorkUuid: failTarget.toLowerCase(),
      });
    } else {
      tokens.push({ kind: "work", workUuid: current.toLowerCase() });
    }
    const next = successNext.get(current);
    if (!next) {
      throw new Error(`노드 ${current} 에서 이어지는 success edge 가 없습니다.`);
    }
    current = next;
  }
  tokens.push({ kind: "end" });
  return tokens;
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
      worker: "agent",
      upload: false,
      uploadPath: "",
      approverUserid: "",
      fail,
    };
  };

  const toHitl = (item: WorkNodeItem): HitlEditorNode => {
    const userid = (item.approver_userid || "").trim();
    return {
      clientId: nextClientId(`H${item.uuid}`),
      type: "hitl",
      uuid: item.uuid,
      userid,
      username: userNames[userid] || userid,
      name: item.work_name || `결재승인 (${userid})`,
      description: item.work_description || "",
      upload: Boolean(item.upload),
      uploadPath: item.upload_path || "",
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
        uuid: "",
        userid: token.userid,
        username: userNames[token.userid] || token.userid,
        name: `결재승인 (${token.userid})`,
        description: "",
        upload: false,
        uploadPath: "",
      });
      continue;
    }
    const item = byUuid.get(token.workUuid.toLowerCase());
    if (item && (item.worker || "agent") === "hitl") {
      main.push(toHitl(item));
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

  const nodes: string[] = [];
  const edges: Array<{ from: string; to: string; kind: string }> = [];
  const mainRefs: string[] = [];

  for (const step of model.main) {
    if (step.type === "start") {
      mainRefs.push("S");
      continue;
    }
    if (step.type === "end") {
      mainRefs.push("E");
      continue;
    }
    if (step.type === "hitl") {
      const uuid = (step.uuid || "").trim().toLowerCase();
      if (!uuid) {
        continue;
      }
      if (!nodes.includes(uuid)) {
        nodes.push(uuid);
      }
      mainRefs.push(uuid);
      continue;
    }
    const uuid = step.uuid.toLowerCase();
    if (!nodes.includes(uuid)) {
      nodes.push(uuid);
    }
    mainRefs.push(uuid);
    if (step.fail.kind === "end") {
      edges.push({ from: uuid, to: "E", kind: "fail" });
    } else if (step.fail.kind === "work") {
      const failNode = workByClient(step.fail.clientId);
      if (failNode?.uuid) {
        const failUuid = failNode.uuid.toLowerCase();
        if (!nodes.includes(failUuid)) {
          nodes.push(failUuid);
        }
        edges.push({ from: uuid, to: failUuid, kind: "fail" });
      } else {
        edges.push({ from: uuid, to: "E", kind: "fail" });
      }
    }
  }

  if (mainRefs.length === 0) {
    mainRefs.push("S", "E");
  }
  if (mainRefs[0] !== "S") {
    mainRefs.unshift("S");
  }
  if (mainRefs[mainRefs.length - 1] !== "E") {
    mainRefs.push("E");
  }
  for (let i = 0; i < mainRefs.length - 1; i += 1) {
    edges.push({ from: mainRefs[i], to: mainRefs[i + 1], kind: "success" });
  }
  return JSON.stringify({ version: 1, nodes, edges });
}

export function validateEditor(model: EditorModel): string | null {
  for (const step of model.main) {
    if (step.type === "hitl" && !step.userid.trim()) {
      return "승인자를 지정하세요.";
    }
    if (step.type === "hitl" && !step.uuid.trim()) {
      return "승인 노드를 저장하세요.";
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
