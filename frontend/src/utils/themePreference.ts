import { AppTheme, THEME_STORAGE_KEY } from "../types/theme";

export function loadThemePreference(): AppTheme {
  if (typeof window === "undefined") {
    return "dark";
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" ? "light" : "dark";
}

export function saveThemePreference(theme: AppTheme): void {
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}

export function applyThemeToDocument(theme: AppTheme): void {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
}
