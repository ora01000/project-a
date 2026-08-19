import isoflowIsopack from "@isoflow/isopacks/dist/isoflow";
import kubernetesIsopack from "@isoflow/isopacks/dist/kubernetes";

type IconCollection = {
  id: string;
  name: string;
  icons: Array<{
    id: string;
    name: string;
    url: string;
    isIsometric?: boolean;
  }>;
};

function unwrapModule(value: unknown, depth = 0): unknown {
  if (depth > 3) {
    return value;
  }
  if (value && typeof value === "object" && "default" in value) {
    const inner = (value as { default: unknown }).default;
    if (inner && inner !== value) {
      return unwrapModule(inner, depth + 1);
    }
  }
  return value;
}

function asIconCollection(value: unknown, packName: string): IconCollection {
  const unwrapped = unwrapModule(value);
  if (
    unwrapped &&
    typeof unwrapped === "object" &&
    Array.isArray((unwrapped as IconCollection).icons)
  ) {
    return unwrapped as IconCollection;
  }
  throw new Error(`${packName} 아이콘 팩을 불러오지 못했습니다.`);
}

const ICON_PACKS: IconCollection[] = [
  asIconCollection(isoflowIsopack, "isoflow"),
  asIconCollection(kubernetesIsopack, "kubernetes"),
];

export function lookupFossflowIconUrl(iconRef: string): string {
  for (const pack of ICON_PACKS) {
    const matched = pack.icons.find((icon) => icon.id === iconRef || icon.name === iconRef);
    if (matched?.url) {
      return matched.url;
    }
  }
  return "";
}
