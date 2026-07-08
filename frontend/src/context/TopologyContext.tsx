import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import type { TopologyFlow } from "../types/topology";

interface TopologyContextValue {
  activeFlows: TopologyFlow[];
  emitFlow: (from: string, to: string) => void;
}

const TopologyContext = createContext<TopologyContextValue | null>(null);

const FLOW_DURATION_MS = 2200;

export function TopologyProvider({ children }: { children: ReactNode }) {
  const [activeFlows, setActiveFlows] = useState<TopologyFlow[]>([]);

  const emitFlow = useCallback((from: string, to: string) => {
    const id = `${from}->${to}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const flow: TopologyFlow = { id, from, to, startedAt: Date.now() };

    setActiveFlows((prev) => [...prev, flow]);

    window.setTimeout(() => {
      setActiveFlows((prev) => prev.filter((item) => item.id !== id));
    }, FLOW_DURATION_MS);
  }, []);

  const value = useMemo(
    () => ({
      activeFlows,
      emitFlow,
    }),
    [activeFlows, emitFlow],
  );

  return <TopologyContext.Provider value={value}>{children}</TopologyContext.Provider>;
}

export function useTopology(): TopologyContextValue {
  const context = useContext(TopologyContext);
  if (!context) {
    throw new Error("useTopology must be used within TopologyProvider");
  }
  return context;
}
