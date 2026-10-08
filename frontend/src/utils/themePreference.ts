import { AppTheme, THEME_STORAGE_KEY } from "../types/theme";

const VALID_THEMES: ReadonlySet<string> = new Set([
  "dark",
  "light",
  "homebrew",
  "monochrome",
]);

export function loadThemePreference(): AppTheme {
  if (typeof window === "undefined") {
    return "dark";
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return VALID_THEMES.has(stored ?? "") ? (stored as AppTheme) : "dark";
}

export function saveThemePreference(theme: AppTheme): void {
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}

/** CSS `color-scheme` for native controls; non-light themes use dark palettes. */
export function themeColorScheme(theme: AppTheme): "dark" | "light" {
  return theme === "light" ? "light" : "dark";
}

export function applyThemeToDocument(theme: AppTheme): void {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = themeColorScheme(theme);
}
