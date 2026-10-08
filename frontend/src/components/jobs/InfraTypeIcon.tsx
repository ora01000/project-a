import type { ImgHTMLAttributes } from "react";

import { useTheme } from "../../context/ThemeContext";
import type { AppTheme } from "../../types/theme";
import { WORKFLOW_ICON_BASE } from "../workflow/WorkflowIcon";

export type InfraTypeIconName = "okd" | "kubevirt" | "vsphere";

type InfraTypeIconProps = {
  infraType: string;
  size?: "xs" | "sm" | "md" | "lg";
  label?: string;
} & Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt" | "width" | "height">;

const SIZE_CLASS: Record<NonNullable<InfraTypeIconProps["size"]>, string> = {
  xs: "h-3 w-3",
  sm: "h-3.5 w-3.5",
  md: "h-4 w-4",
  lg: "h-5 w-5",
};

export function resolveInfraTypeIconName(infraType: string): InfraTypeIconName {
  const lower = (infraType ?? "").trim().toLowerCase();
  if (lower === "kubevirt") {
    return "kubevirt";
  }
  if (lower === "vsphere") {
    return "vsphere";
  }
  return "okd";
}

export function infraTypeIconSrc(name: InfraTypeIconName, theme: AppTheme = "dark"): string {
  if (theme === "light") {
    return `${WORKFLOW_ICON_BASE}/light/${name}.svg`;
  }
  return `${WORKFLOW_ICON_BASE}/${name}.svg`;
}

export function InfraTypeIcon({
  infraType,
  size = "md",
  label,
  className = "",
  ...rest
}: InfraTypeIconProps) {
  const { theme } = useTheme();
  const name = resolveInfraTypeIconName(infraType);
  const resolvedLabel =
    label ??
    (name === "okd" ? "k8s (OKD)" : name === "kubevirt" ? "KubeVirt" : "vSphere");
  return (
    <img
      src={infraTypeIconSrc(name, theme)}
      alt={resolvedLabel}
      title={resolvedLabel}
      className={`inline-block shrink-0 object-contain ${SIZE_CLASS[size]} ${className}`.trim()}
      {...rest}
    />
  );
}
