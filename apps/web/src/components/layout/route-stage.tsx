"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

export function RouteStage({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div key={pathname} className="route-stage" data-route-stage={pathname}>
      {children}
    </div>
  );
}
