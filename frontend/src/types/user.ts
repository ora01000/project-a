export interface UserRecord {
  idx: number;
  userid: string;
  email: string;
  username: string;
  depart: string;
  role: number;
  band: number;
  agents?: string;
  agent_ids?: string[];
}

export interface UserFormValues {
  userid: string;
  email: string;
  username: string;
  password: string;
  depart: string;
  role: number;
  band: number;
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

export const BAND_EMPLOYEE = 1;
export const BAND_SENIOR = 2;
export const BAND_PRINCIPAL = 3;

export const BAND_OPTIONS: { value: number; label: string }[] = [
  { value: BAND_EMPLOYEE, label: "사원" },
  { value: BAND_SENIOR, label: "선임" },
  { value: BAND_PRINCIPAL, label: "책임" },
];

export function bandLabel(band: number | null | undefined): string {
  const matched = BAND_OPTIONS.find((option) => option.value === band);
  return matched?.label ?? "";
}

export const EMPTY_USER_FORM: UserFormValues = {
  userid: "",
  email: "",
  username: "",
  password: "",
  depart: "",
  role: 1,
  band: BAND_EMPLOYEE,
};
