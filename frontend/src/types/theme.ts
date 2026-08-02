export type AppTheme = "dark" | "light";

export const THEME_STORAGE_KEY = "app-theme";

export const THEME_LABELS: Record<AppTheme, string> = {
  dark: "다크",
  light: "밝은",
};
