export interface AuthUser {
  idx: number;
  userid: string;
  email: string;
  username: string;
  depart: string;
  role: number;
  band?: number;
  agents?: string;
  agent_ids?: string[];
}
