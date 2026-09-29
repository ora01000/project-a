export interface JobWorkflowStep {
  status_code: number;
  label: string;
  timestamp: string | null;
  detail: string;
}

export interface JobWorkflowItem {
  idx: number;
  srnum: string;
  requester_name: string;
  requester_userid: string;
  approver: string | null;
  approver_name: string;
  status_code: number;
  steps: JobWorkflowStep[];
}
