export interface SignupNotification {
  idx: number;
  user_idx: number;
  title: string;
  message: string;
  created_at: string;
}

export const SIGNUP_NOTIFICATION_TITLE = "신규 가입 신청";
