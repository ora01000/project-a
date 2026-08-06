import { todayDateOnly } from "./datetime";

const WELCOME_BACK_HIDE_DATE_KEY = "project-a-welcome-back-hide-date";

export function isWelcomeBackHiddenToday(): boolean {
  try {
    return localStorage.getItem(WELCOME_BACK_HIDE_DATE_KEY) === todayDateOnly();
  } catch {
    return false;
  }
}

export function setWelcomeBackHiddenForToday(): void {
  try {
    localStorage.setItem(WELCOME_BACK_HIDE_DATE_KEY, todayDateOnly());
  } catch {
    // ignore quota / private mode
  }
}
