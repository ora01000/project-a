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
  return role === 0 ? "admin" : "user";
}

export const EMPTY_USER_FORM: UserFormValues = {
  userid: "",
  email: "",
  username: "",
  password: "",
  depart: "",
  role: 1,
};
