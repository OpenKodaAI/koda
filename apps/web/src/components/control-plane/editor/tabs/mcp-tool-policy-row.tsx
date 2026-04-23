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

const POLICY_OPTIONS: { value: McpToolPolicy; label: string; description: string }[] = [
  { value: "auto", label: "Automatico", description: "Classificacao automatica" },
  { value: "always_allow", label: "Sempre permitir", description: "Executar sem aprovacao" },
  { value: "always_ask", label: "Sempre perguntar", description: "Requer aprovacao" },
  { value: "blocked", label: "Bloqueado", description: "Nunca executar" },
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
  const { tl } = useAppI18n();
  void _agentId;
  void _serverKey;

  const annotations = tool.annotations;
  const readOnly = annotations?.read_only_hint === true;
  const destructive = annotations?.destructive_hint === true;
  const idempotent = annotations?.idempotent_hint === true;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {annotations?.title || tool.name}
          </span>
          {readOnly && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-info-text)]">
              {tl("Somente leitura")}
            </span>
          )}
          {destructive && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-danger-text)]">
              {tl("Destrutivo")}
            </span>
          )}
          {idempotent && (
            <span className="inline-flex items-center gap-1 rounded-full border border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-success-text)]">
              {tl("Idempotente")}
            </span>
          )}
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
          <SelectTrigger sizeVariant="sm" className="min-w-[220px]" title={tl("Politica de execucao")}>
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
