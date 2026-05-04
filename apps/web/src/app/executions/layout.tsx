import type { ReactNode } from "react";
import { ExecutionsShell } from "@/components/features/executions/executions-shell";

export default function ExecutionsLayout({ children }: { children: ReactNode }) {
  return <ExecutionsShell>{children}</ExecutionsShell>;
}
