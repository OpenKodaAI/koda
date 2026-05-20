"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { McpDiscoveredTool, McpToolPolicy } from "@/lib/control-plane";
import { McpRiskBadgeGroup, getMcpToolRisk } from "./mcp-risk-badges";

const POLICY_OPTIONS: { value: McpToolPolicy; label: string; description: string }[] = [
  {
    value: "auto",
    label: "controlPlane.mcpToolPolicy.options.auto.label",
    description: "controlPlane.mcpToolPolicy.options.auto.description",
  },
  {
    value: "always_allow",
    label: "controlPlane.mcpToolPolicy.options.alwaysAllow.label",
    description: "controlPlane.mcpToolPolicy.options.alwaysAllow.description",
  },
  {
    value: "always_ask",
    label: "controlPlane.mcpToolPolicy.options.alwaysAsk.label",
    description: "controlPlane.mcpToolPolicy.options.alwaysAsk.description",
  },
  {
    value: "blocked",
    label: "controlPlane.mcpToolPolicy.options.blocked.label",
    description: "controlPlane.mcpToolPolicy.options.blocked.description",
  },
];

type McpToolPolicyRowProps = {
  agentId: string;
  serverKey: string;
  tool: McpDiscoveredTool;
  currentPolicy: McpToolPolicy;
  onPolicyChange: (toolName: string, policy: McpToolPolicy) => void;
};

export function McpToolPolicyRow({
  agentId: _agentId,
  serverKey: _serverKey,
  tool,
  currentPolicy,
  onPolicyChange,
}: McpToolPolicyRowProps) {
  const { t, tl } = useAppI18n();
  void _agentId;
  void _serverKey;

  const annotations = tool.annotations;
  const readOnly = annotations?.read_only_hint === true;
  const destructive = annotations?.destructive_hint === true;
  const idempotent = annotations?.idempotent_hint === true;
  const risk = getMcpToolRisk(tool);

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {annotations?.title || tool.name}
          </span>
          {readOnly && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-info-text)]">
              {t("generated.controlPlane.somente_leitura_0f78d76a")}
            </span>
          )}
          {destructive && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-danger-text)]">
              {t("generated.controlPlane.destrutivo_9a492f91")}
            </span>
          )}
          {idempotent && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-success-text)]">
              {t("generated.controlPlane.idempotente_940705ab")}
            </span>
          )}
          <McpRiskBadgeGroup risk={risk} capabilityName={tool.name} />
        </div>
        {tool.description && (
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-tertiary)]">
            {tool.description}
          </p>
        )}
      </div>

      <div className="shrink-0">
        <Select
          value={currentPolicy}
          onValueChange={(v) => onPolicyChange(tool.name, v as McpToolPolicy)}
        >
          <SelectTrigger sizeVariant="sm" className="min-w-[220px]" title={t("generated.controlPlane.politica_de_execucao_723767cb")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {POLICY_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {tl(option.label)} — {tl(option.description)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
