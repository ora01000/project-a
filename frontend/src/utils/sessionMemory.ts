import { clearD2SvgCache } from "../components/D2Diagram";
import { clearMermaidSvgCache } from "../components/MermaidDiagram";

/**
 * Release app-owned caches after logout / session expiry.
 * Does not force browser GC; makes retained heap eligible for collection.
 */
export function clearClientSessionMemory(): void {
  clearMermaidSvgCache();
  clearD2SvgCache();
}
