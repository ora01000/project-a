export interface JobWorkflowStep {
  status_code: number;
  label: string;
  timestamp: string | null;
  detail: string;
}

export interface JobWorkflowItem {
  idx: number;
  srnum: string;
  requester_idx: number;
  requester_name: string;
  requester_userid?: string;
  approver_idx: number | null;
  approver_userid?: string | null;
  approver_name: string;
  status_code: number;
  steps: JobWorkflowStep[];
  is_scheduled?: boolean;
  scheduled_at?: string | null;
  schedule_waiting?: boolean;
}
