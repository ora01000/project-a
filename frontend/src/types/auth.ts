export interface AuthUser {
  idx: number;
  userid: string;
  email: string;
  username: string;
  depart: string;
  role: number;
  agents?: string;
  agent_ids?: string[];
}
