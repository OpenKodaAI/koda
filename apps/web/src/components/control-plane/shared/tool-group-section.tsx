"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { COLLAPSE_TRANSITION } from "./motion-constants";
import { ToolPolicySegment, type ToolPolicy } from "./tool-policy-segment";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type ToolItem = {
  id: string;
  label: string;
  description?: string;
  policy: ToolPolicy;
};

export type GroupPolicy = ToolPolicy | "custom";

type ToolGroupSectionProps = {
  label: string;
  count: number;
  tools: ToolItem[];
  groupPolicy: GroupPolicy;
  onGroupPolicyChange: (policy: ToolPolicy) => void;
  onToolPolicyChange: (toolId: string, policy: ToolPolicy) => void;
  defaultExpanded?: boolean;
};

/* ------------------------------------------------------------------ */
/*  Select options                                                     */
/* ------------------------------------------------------------------ */

const GROUP_POLICY_OPTIONS: { value: GroupPolicy; labelKey: string }[] = [
  { value: "always_allow", labelKey: "Sempre permitir" },
  { value: "always_ask", labelKey: "Precisa de aprovacao" },
  { value: "blocked", labelKey: "Bloqueado" },
  { value: "custom", labelKey: "Customizado" },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ToolGroupSection({
  label,
  count,
  tools,
  groupPolicy,
  onGroupPolicyChange,
  onToolPolicyChange,
  defaultExpanded = false,
}: ToolGroupSectionProps) {
  const { tl } = useAppI18n();
  const [expanded, setExpanded] = useState(defaultExpanded);

  function handleSelectChange(val: GroupPolicy) {
    if (val !== "custom") {
      onGroupPolicyChange(val);
    }
  }

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center gap-2">
        {/* Left side: clickable to toggle expand */}
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left"
        >
          <motion.span
            animate={{ rotate: expanded ? 0 : -90 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="text-[var(--text-quaternary)] shrink-0"
          >
            <ChevronDown size={14} />
          </motion.span>

          <span className="text-sm font-semibold text-[var(--text-primary)] truncate">
            {tl(label)}
          </span>

          <span
            className="inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium"
            style={{
              backgroundColor: "rgba(255,255,255,0.06)",
              color: "var(--text-quaternary)",
            }}
          >
            {count}
          </span>
        </button>

        {/* Right side: policy select */}
        <Select
          value={groupPolicy}
          onValueChange={(v) => handleSelectChange(v as GroupPolicy)}
        >
          <SelectTrigger
            sizeVariant="sm"
            onClick={(e) => e.stopPropagation()}
            className="w-auto max-w-[180px] shrink-0 text-[var(--text-secondary)]"
            title={tl("Politica do grupo")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {GROUP_POLICY_OPTIONS.map(({ value, labelKey }) => (
              <SelectItem
                key={value}
                value={value}
                disabled={value === "custom" && groupPolicy !== "custom"}
              >
                {tl(labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Collapsible body */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={COLLAPSE_TRANSITION}
            className="overflow-hidden"
          >
            <div className="flex flex-col">
              {tools.map((tool) => (
                <div
                  key={tool.id}
                  className={cn(
                    "flex items-center justify-between py-3",
                    "border-b border-[rgba(255,255,255,0.04)] last:border-b-0",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <span className="text-sm text-[var(--text-tertiary)]">
                      {tool.label}
                    </span>
                    {tool.description && (
                      <p className="mt-0.5 text-xs text-[var(--text-quaternary)] truncate">
                        {tool.description}
                      </p>
                    )}
                  </div>
                  <ToolPolicySegment
                    value={tool.policy}
                    onChange={(p) => onToolPolicyChange(tool.id, p)}
                  />
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
