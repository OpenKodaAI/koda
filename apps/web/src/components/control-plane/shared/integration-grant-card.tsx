"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Plug } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { renderIntegrationLogo } from "@/components/control-plane/system/integrations/integration-logos";
import { FormSelect } from "@/components/control-plane/shared/form-field";
import { TagInputField } from "@/components/control-plane/shared/tag-input-field";
import { cn } from "@/lib/utils";
import type { ControlPlaneCoreIntegration } from "@/lib/control-plane";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type IntegrationGrantValue = {
  enabled?: boolean;
  approval_mode?: string;
  allow_actions?: string[];
  deny_actions?: string[];
};

interface IntegrationGrantCardProps {
  integration: ControlPlaneCoreIntegration;
  grant: IntegrationGrantValue | undefined;
  onToggle: (integrationId: string, enabled: boolean) => void;
  onUpdate: (integrationId: string, grant: IntegrationGrantValue) => void;
}

/* ------------------------------------------------------------------ */
/*  Connection status badge                                            */
/* ------------------------------------------------------------------ */

function ConnectionBadge({ status }: { status: string | undefined }) {
  const { tl } = useAppI18n();
  const label = status === "connected"
    ? tl("Conectado")
    : status === "pending"
      ? tl("Pendente")
      : tl("Desconectado");

  const bg = status === "connected"
    ? "rgba(113,219,190,0.12)"
    : status === "pending"
      ? "rgba(255,180,76,0.12)"
      : "rgba(255,255,255,0.04)";

  const color = status === "connected"
    ? "var(--tone-success-dot)"
    : status === "pending"
      ? "#ffb44c"
      : "var(--text-quaternary)";

  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium"
      style={{ backgroundColor: bg, color }}
    >
      {label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Toggle switch (inline, minimal)                                    */
/* ------------------------------------------------------------------ */

function GrantSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className="relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-200"
      style={{
        backgroundColor: checked
          ? "var(--tone-success-bg-strong)"
          : "var(--field-bg)",
      }}
    >
      <motion.span
        className="inline-block h-5 w-5 rounded-full bg-[var(--text-primary)] shadow-sm"
        style={{ marginTop: 2 }}
        animate={{ x: checked ? 22 : 2 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Main card                                                          */
/* ------------------------------------------------------------------ */

export function IntegrationGrantCard({
  integration,
  grant,
  onToggle,
  onUpdate,
}: IntegrationGrantCardProps) {
  const { tl } = useAppI18n();
  const [expanded, setExpanded] = useState(false);

  const enabled = grant?.enabled === true;
  const logoKey = integration.id;
  const logo = renderIntegrationLogo(logoKey, "h-6 w-6");
  const connectionStatus = integration.connection_status || integration.connection?.connection_status;

  function handleBodyClick() {
    if (enabled) {
      setExpanded((prev) => !prev);
    }
  }

  function handleApprovalModeChange(mode: string) {
    onUpdate(integration.id, {
      ...grant,
      enabled: true,
      approval_mode: mode || undefined,
    });
  }

  function handleAllowedActionsChange(actions: string[]) {
    onUpdate(integration.id, {
      ...grant,
      enabled: true,
      allow_actions: actions,
    });
  }

  function handleDeniedActionsChange(actions: string[]) {
    onUpdate(integration.id, {
      ...grant,
      enabled: true,
      deny_actions: actions,
    });
  }

  return (
    <div
      className={cn(
        "rounded-xl border transition-all duration-200",
        enabled
          ? "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.018)]"
          : "border-[rgba(255,255,255,0.04)] bg-[rgba(255,255,255,0.008)]",
      )}
      style={{
        borderLeftWidth: 3,
        borderLeftColor: enabled
          ? "rgba(113,219,190,0.4)"
          : "transparent",
      }}
    >
      {/* Header row */}
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-3 transition-colors",
          enabled && "cursor-pointer hover:bg-[rgba(255,255,255,0.015)]",
        )}
        onClick={handleBodyClick}
      >
        {/* Logo */}
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors",
            enabled
              ? "bg-[rgba(113,219,190,0.08)]"
              : "bg-[rgba(255,255,255,0.04)]",
          )}
        >
          {logo || <Plug size={16} className="text-[var(--text-quaternary)]" />}
        </div>

        {/* Title + description */}
        <div className={cn("min-w-0 flex-1", !enabled && "opacity-50")}>
          <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
            {integration.title}
          </div>
          {integration.description && (
            <div className="mt-0.5 truncate text-xs text-[var(--text-quaternary)]">
              {integration.description}
            </div>
          )}
        </div>

        {/* Connection badge */}
        <ConnectionBadge status={connectionStatus} />

        {/* Expand indicator (only when enabled) */}
        {enabled && (
          <motion.span
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.2 }}
            className="text-[var(--text-quaternary)]"
          >
            <ChevronDown size={14} />
          </motion.span>
        )}

        {/* Toggle */}
        <GrantSwitch
          checked={enabled}
          onChange={(value) => onToggle(integration.id, value)}
        />
      </div>

      {/* Expandable settings */}
      <AnimatePresence initial={false}>
        {expanded && enabled && (
          <motion.div
            key="settings"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-[rgba(255,255,255,0.06)] px-4 pb-4 pt-3">
              <div className="grid gap-4 xl:grid-cols-3">
                <FormSelect
                  label={tl("Modo de aprovacao")}
                  description={tl("Como acoes nesta integracao sao aprovadas.")}
                  value={grant?.approval_mode || ""}
                  onChange={(e) => handleApprovalModeChange(e.target.value)}
                  options={[
                    { value: "", label: tl("Padrao") },
                    { value: "auto", label: tl("Automatico") },
                    { value: "manual", label: tl("Manual") },
                    { value: "guarded", label: tl("Supervisionado") },
                  ]}
                />
              </div>

              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                <TagInputField
                  label={tl("Acoes permitidas")}
                  description={tl("Restrinja a acoes especificas (vazio = todas permitidas).")}
                  values={grant?.allow_actions || []}
                  onChange={handleAllowedActionsChange}
                  placeholder={tl("Ex.: read, list, query")}
                />
                <TagInputField
                  label={tl("Acoes negadas")}
                  description={tl("Bloqueie acoes especificas (vazio = nenhuma bloqueada).")}
                  values={grant?.deny_actions || []}
                  onChange={handleDeniedActionsChange}
                  placeholder={tl("Ex.: delete, destroy")}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
