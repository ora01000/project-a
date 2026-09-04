export type WorkScriptType = "" | "yaml" | "ansible";

export const WORK_SCRIPT_TYPE_OPTIONS: { value: Exclude<WorkScriptType, "">; label: string }[] = [
  { value: "yaml", label: "yaml" },
  { value: "ansible", label: "ansible" },
];

export interface WorkNodeItem {
  idx: number;
  uuid?: string;
  work_name: string;
  work_description?: string;
  target_agent: number;
  target_agent_name: string;
  user_prompt: string;
  agent_response: string;
  script_type?: WorkScriptType | string;
  test_result: boolean;
  files: string;
  create_date?: string;
  validate_date?: string;
}

export interface WorkflowApprover {
  userid: string;
  username: string;
  role: number;
}

export interface WorkflowGraphNode {
  id: string;
  kind: "start" | "end" | "work" | "hitl" | string;
  label: string;
  work_idx: number | null;
  userid: string | null;
  cx: number;
  cy: number;
  width: number;
  height: number;
}

export interface WorkflowGraphEdge {
  source: string;
  target: string;
  kind: "success" | "fail" | string;
}

export interface WorkflowGraph {
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
  width: number;
  height: number;
}

export interface WorkflowItem {
  idx: number;
  uuid?: string;
  checkin_user?: number;
  checkin_username?: string;
  checkin_time?: string;
  workflow_name: string;
  workflow_description: string;
  workflow: string;
  create_date?: string;
  test_result?: boolean;
  validate_date?: string;
  graph: WorkflowGraph;
}
