export type WorkScriptType = "" | "kubectl" | "ansible" | "cli" | "prompt";

export const WORK_SCRIPT_TYPE_OPTIONS: { value: Exclude<WorkScriptType, "">; label: string }[] = [
  { value: "prompt", label: "자연어(프롬프트)" },
  { value: "kubectl", label: "kubectl(Kubernetes)" },
  { value: "ansible", label: "playbook" },
  { value: "cli", label: "cli(bash)" },
];

export interface WorkNodeItem {
  uuid: string;
  owner?: number;
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
  last_start_date?: string;
  last_end_date?: string;
  last_success?: boolean;
  last_fail_reason?: string;
  use_previous_work_result?: boolean;
  work_report?: string;
  cron?: boolean;
  cron_expr?: string;
  schedule_wait?: boolean;
  worker?: "agent" | "hitl" | string;
  upload?: boolean;
  upload_path?: string;
  approver_userid?: string;
  /** Compact CRUD flags e.g. ``cru`` (HITL empty). */
  crud?: string;
}

export interface WorkflowApprover {
  userid: string;
  username: string;
  role: number;
}

export interface WorkflowGraphNode {
  id: string;
  kind: "start" | "end" | "work" | "hitl" | "mail" | string;
  label: string;
  work_uuid: string | null;
  userid: string | null;
  upload?: boolean;
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
  owner?: number;
  owner_username?: string;
  distribute?: boolean;
  can_edit?: boolean;
  workflow_name: string;
  workflow_description: string;
  workflow: string;
  create_date?: string;
  test_result?: boolean;
  validate_date?: string;
  last_start_date?: string;
  last_end_date?: string;
  run_count?: number;
  sucess_count?: number;
  fail_count?: number;
  last_success?: boolean;
  cron?: boolean;
  cron_expr?: string;
  awaiting_approval?: boolean;
  awaiting_hitl_node_id?: string;
  awaiting_hitl_userid?: string;
  awaiting_job_idx?: number | null;
  graph: WorkflowGraph;
}
