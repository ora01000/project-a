export const JOB_TYPE_AX_INFRA = 1;
export const JOB_TYPE_WHATAP = 2;
export const JOB_TYPE_WORKFLOW = 3;
export const JOB_TYPE_SIGNUP = 10;

export interface JobRecord {
  idx: number;
  srnum: string;
  status_code: number;
  job_type?: number;
  approver_registered_date: string | null;
  approver: string | null;
  job_title: string;
  requester_name: string;
  requester_email: string;
  requester_depart: string;
  job_content: string;
  request_date: string;
  madang_id: string;
  team_id: string;
  channel_id: string;
  message_id: string;
  received_at: string;
  reject_reason?: string;
  drop_reason?: string;
  ai_audit_comment?: string;
  ai_audit_date?: string | null;
  ai_audit_cnt?: number;
}
