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
  prod_auth?: boolean;
  /** 1=개발, 2=운영 */
  current_prod_mode?: number;
  /** 1:dark 2:light 3:homebrew 4:monochrome */
  theme_for_dev_mode?: number;
  theme_for_prod_mode?: number;
}
