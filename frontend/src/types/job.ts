export interface JobPlanStep {
  agent_id: string;
  agent_name?: string;
  tool_name?: string;
  tool_params?: Record<string, unknown>;
  description?: string;
}

export interface JobPlan {
  summary?: string;
  steps?: JobPlanStep[];
}

export interface JobExecutionStepResult {
  agent_id: string;
  agent_name?: string;
  tool_name?: string;
  tool_params?: Record<string, unknown>;
  status: string;
  content: string;
}

export interface JobExecutionResult {
  summary?: string;
  results?: JobExecutionStepResult[];
}

export interface JobRecord {
  idx: number;
  sr_num?: string | null;
  request_date: string;
  job_title: string;
  request_depart: string;
  requester: string;
  requester_email: string;
  completion_request_date: string;
  job_description: string;
  approver: string;
  state: number;
  state_label: string;
  notify_channel: string;
  job_plan?: JobPlan | null;
  original_job_plan?: JobPlan | null;
  execution_result?: JobExecutionResult | null;
  actual_completion_time?: string | null;
  approval_date?: string | null;
  pending_date?: string | null;
  reject_date?: string | null;
  /** users.username resolved from requester userid (fallback: userid). */
  requester_name?: string | null;
  /** users.username resolved from approver userid (fallback: userid). */
  approver_name?: string | null;
}

export interface JobNotification {
  idx: number;
  job_idx: number;
  notification_type: string;
  title: string;
  message: string;
  created_at: string;
  request_date?: string | null;
  actual_completion_time?: string | null;
}

export type JobDetailTab = "review" | "pending" | "completed";

export const JOB_NOTIFICATION_REVIEW = "review_request";
export const JOB_NOTIFICATION_RESULT = "execution_result";
export const JOB_NOTIFICATION_FAILURE = "execution_failure";
export const JOB_NOTIFICATION_REJECTION = "rejection";

/** 작업 목록 화면에서 표시하는 상태 (0~6). */
export const JOB_LIST_STATES: { state: number; label: string }[] = [
  { state: 0, label: "접수" },
  { state: 1, label: "계획수립완료" },
  { state: 2, label: "검토중" },
  { state: 3, label: "보류" },
  { state: 4, label: "반려" },
  { state: 5, label: "승인" },
  { state: 6, label: "완료" },
];

export function jobRequesterLabel(job: Pick<JobRecord, "requester" | "requester_name">): string {
  return job.requester_name?.trim() || job.requester;
}

export function jobApproverLabel(job: Pick<JobRecord, "approver" | "approver_name">): string {
  return job.approver_name?.trim() || job.approver;
}
