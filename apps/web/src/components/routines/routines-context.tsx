"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

interface RoutinesContextValue {
  defaultTimezone: string;
}

const RoutinesContext = createContext<RoutinesContextValue>({
  defaultTimezone: "UTC",
});

export function RoutinesContextProvider({
  defaultTimezone,
  children,
}: {
  defaultTimezone: string;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ defaultTimezone }), [defaultTimezone]);
  return <RoutinesContext.Provider value={value}>{children}</RoutinesContext.Provider>;
}

export function useRoutinesContext() {
  return useContext(RoutinesContext);
}
