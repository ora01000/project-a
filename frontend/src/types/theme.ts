export type AppTheme = "dark" | "light" | "homebrew" | "monochrome";

export const THEME_STORAGE_KEY = "app-theme";

/** DB users.theme_for_*_mode — 1:dark 2:white 3:homebrew 4:monochrome */
export type ThemeId = 1 | 2 | 3 | 4;

export const THEME_LABELS: Record<AppTheme, string> = {
  dark: "다크",
  light: "밝은",
  homebrew: "Homebrew (테스트)",
  monochrome: "모노크롬",
};

const THEME_TO_ID: Record<AppTheme, ThemeId> = {
  dark: 1,
  light: 2,
  homebrew: 3,
  monochrome: 4,
};

const ID_TO_THEME: Record<ThemeId, AppTheme> = {
  1: "dark",
  2: "light",
  3: "homebrew",
  4: "monochrome",
};

export function themeToId(theme: AppTheme): ThemeId {
  return THEME_TO_ID[theme];
}

export function themeFromId(themeId: number | null | undefined): AppTheme {
  if (themeId === 2 || themeId === 3 || themeId === 4) {
    return ID_TO_THEME[themeId];
  }
  return "dark";
}

export function themeIdForProdMode(
  user: {
    current_prod_mode?: number;
    theme_for_dev_mode?: number;
    theme_for_prod_mode?: number;
  } | null | undefined,
): number {
  if (user?.current_prod_mode === 2) {
    return user.theme_for_prod_mode ?? 1;
  }
  return user?.theme_for_dev_mode ?? 1;
}
