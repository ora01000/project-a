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
}

export interface JobNotification {
  idx: number;
  job_idx: number;
  notification_type: string;
  title: string;
  message: string;
  created_at: string;
}

export type JobDetailTab = "review" | "pending" | "completed";

export const JOB_NOTIFICATION_REVIEW = "review_request";
export const JOB_NOTIFICATION_RESULT = "execution_result";
export const JOB_NOTIFICATION_FAILURE = "execution_failure";
export const JOB_NOTIFICATION_REJECTION = "rejection";
