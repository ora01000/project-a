export type AppTheme = "dark" | "light" | "homebrew" | "monochrome";

export const THEME_STORAGE_KEY = "app-theme";

export const THEME_LABELS: Record<AppTheme, string> = {
  dark: "다크",
  light: "밝은",
  homebrew: "Homebrew (테스트)",
  monochrome: "모노크롬",
};
