"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { prettyJson } from "@/lib/control-plane-editor";

interface CoreGovernancePanelProps {
  coreTools: {
    items: Array<Record<string, unknown>>;
    governance: Record<string, unknown>;
  };
  coreProviders: Record<string, unknown>;
  corePolicies: Record<string, unknown>;
  coreCapabilities: Record<string, unknown>;
}

export function CoreGovernancePanel({
  coreTools,
  coreProviders,
  corePolicies,
  coreCapabilities,
}: CoreGovernancePanelProps) {
  const [expanded, setExpanded] = useState(false);
  const { tl } = useAppI18n();

  const toolsJson = prettyJson(coreTools);
  const providersJson = prettyJson(coreProviders);
  const policiesAndCapabilities = prettyJson({
    policies: corePolicies,
    capabilities: coreCapabilities,
  });

  return (
    <section>
      <button
        type="button"
        className="eyebrow flex items-center gap-2 py-2 w-full text-left hover:text-[var(--text-secondary)] transition-colors"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <ChevronRight
          className="h-3.5 w-3.5 transition-transform duration-200"
          style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
        />
        {tl("Governanca do sistema")}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="pt-3 grid gap-4 xl:grid-cols-3">
              {/* Core tools */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="eyebrow">{tl("Core tools")}</span>
                  <span className="chip text-[10px]">
                    {tl("{{count}} item(s)", { count: coreTools.items.length })}
                  </span>
                </div>
                <textarea
                  className="field-shell min-h-[260px] font-mono text-sm leading-relaxed"
                  value={toolsJson}
                  readOnly
                  spellCheck={false}
                />
              </div>

              {/* Providers */}
              <div className="space-y-2">
                <span className="eyebrow">{tl("Providers")}</span>
                <textarea
                  className="field-shell min-h-[260px] font-mono text-sm leading-relaxed"
                  value={providersJson}
                  readOnly
                  spellCheck={false}
                />
              </div>

              {/* Policies & Capabilities */}
              <div className="space-y-2">
                <span className="eyebrow">{tl("Policies & capabilities")}</span>
                <textarea
                  className="field-shell min-h-[260px] font-mono text-sm leading-relaxed"
                  value={policiesAndCapabilities}
                  readOnly
                  spellCheck={false}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
