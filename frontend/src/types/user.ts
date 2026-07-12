export interface UserRecord {
  idx: number;
  userid: string;
  email: string;
  username: string;
  depart: string;
  role: number;
}

export interface UserFormValues {
  userid: string;
  email: string;
  username: string;
  password: string;
  depart: string;
  role: number;
}

export function roleLabel(role: number): string {
  if (role === 0) {
    return "admin";
  }
  if (role === 5) {
    return "보류";
  }
  return "user";
}

export const ROLE_ADMIN = 0;
export const ROLE_USER = 1;
export const ROLE_PENDING = 5;

export const EMPTY_USER_FORM: UserFormValues = {
  userid: "",
  email: "",
  username: "",
  password: "",
  depart: "",
  role: 1,
};
