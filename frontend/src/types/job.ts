export interface JobRecord {
  idx: number;
  srnum: string;
  status_code: number;
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
}
