import type { ImgHTMLAttributes } from "react";

import { useTheme } from "../../context/ThemeContext";
import type { AppTheme } from "../../types/theme";

/** Served from ``frontend/public/workflow-icons`` (Vite public root). */
export const WORKFLOW_ICON_BASE = "/workflow-icons";

export const WORKFLOW_ICON_NAMES = [
  "ai",
  "approve",
  "clone",
  "connect",
  "distribute",
  "edit",
  "fail-branch",
  "history",
  "list",
  "log",
  "mail",
  "nodes",
  "owner",
  "quickstart",
  "refresh",
  "result",
  "run",
  "script",
  "session",
  "stop",
  "template",
  "upload",
  "validate",
  "variable",
  "work-node",
] as const;

export type WorkflowIconName = (typeof WORKFLOW_ICON_NAMES)[number];

type WorkflowIconProps = {
  name: WorkflowIconName;
  label?: string;
  size?: "xs" | "sm" | "md" | "lg";
} & Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt" | "width" | "height">;

const SIZE_CLASS: Record<NonNullable<WorkflowIconProps["size"]>, string> = {
  xs: "h-3 w-3",
  sm: "h-3.5 w-3.5",
  md: "h-4 w-4",
  lg: "h-5 w-5",
};

/** Dark-theme assets live at the icon root; light variants under ``light/``. */
export function workflowIconSrc(name: WorkflowIconName, theme: AppTheme = "dark"): string {
  if (theme === "light") {
    return `${WORKFLOW_ICON_BASE}/light/${name}.svg`;
  }
  return `${WORKFLOW_ICON_BASE}/${name}.svg`;
}

/** Rewrite markdown icon paths for the active theme (guide docs). */
export function rewriteWorkflowIconPathsForTheme(markdown: string, theme: AppTheme): string {
  if (theme !== "light") {
    return markdown;
  }
  return markdown.replace(/\/workflow-icons\/(?!light\/)/g, "/workflow-icons/light/");
}

export function WorkflowIcon({
  name,
  label,
  size = "md",
  className = "",
  ...rest
}: WorkflowIconProps) {
  const { theme } = useTheme();
  return (
    <img
      src={workflowIconSrc(name, theme)}
      alt={label ?? ""}
      aria-hidden={label ? undefined : true}
      className={`inline-block shrink-0 object-contain ${SIZE_CLASS[size]} ${className}`.trim()}
      draggable={false}
      {...rest}
    />
  );
}
