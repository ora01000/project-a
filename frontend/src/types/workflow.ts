export type WorkScriptType = "" | "yaml" | "ansible" | "cli";

export const WORK_SCRIPT_TYPE_OPTIONS: { value: Exclude<WorkScriptType, "">; label: string }[] = [
  { value: "yaml", label: "yaml" },
  { value: "ansible", label: "ansible" },
  { value: "cli", label: "cli" },
];

export interface WorkNodeItem {
  uuid: string;
  work_name: string;
  work_description?: string;
  target_agent: number;
  target_agent_name: string;
  work_script: string;
  script_type?: WorkScriptType | string;
  test_result: boolean;
  files: string;
  create_date?: string;
  validate_date?: string;
  is_draft?: boolean;
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
  work_uuid: string | null;
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
  uuid: string;
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
  is_draft?: boolean;
  draft_dirty?: boolean;
}
