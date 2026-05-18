"use client";

import { AlertTriangle, LockKeyhole, ShieldCheck, ShieldQuestion, Wrench } from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import type {
  McpCapabilityRisk,
  McpGrantState,
  McpRiskClass,
} from "@/lib/contracts/mcp-risk";
import { parseMcpCapabilityRisk } from "@/lib/contracts/mcp-risk";
import type { McpDiscoveredTool } from "@/lib/control-plane";
import { cn } from "@/lib/utils";

type McpRiskBadgeGroupProps = {
  risk: McpCapabilityRisk | null;
  capabilityName: string;
  className?: string;
};

function riskTone(riskClass: McpRiskClass | "unavailable"): StatusDotTone {
  if (riskClass === "read_context") return "info";
  if (riskClass === "low_risk_write" || riskClass === "network_write") {
    return "warning";
  }
  if (
    riskClass === "destructive_write" ||
    riskClass === "secret_access" ||
    riskClass === "code_execution" ||
    riskClass === "unknown"
  ) {
    return "danger";
  }
  return "neutral";
}

function grantTone(grantState: McpGrantState): StatusDotTone {
  if (grantState === "granted") return "success";
  if (grantState === "requires_approval") return "warning";
  if (grantState === "blocked") return "danger";
  return "neutral";
}

function formatValue(value: string) {
  return value
    .split("_")
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function readToolRisk(tool: McpDiscoveredTool): McpCapabilityRisk | null {
  const record = tool as McpDiscoveredTool & {
    risk?: unknown;
    risk_metadata?: unknown;
    mcp_risk?: unknown;
  };
  return (
    parseMcpCapabilityRisk(record.risk_metadata) ??
    parseMcpCapabilityRisk(record.mcp_risk) ??
    parseMcpCapabilityRisk(record.risk) ??
    parseMcpCapabilityRisk(tool.annotations?.risk)
  );
}

export function getMcpToolRisk(tool: McpDiscoveredTool): McpCapabilityRisk | null {
  return readToolRisk(tool);
}

export function McpRiskBadgeGroup({
  risk,
  capabilityName,
  className,
}: McpRiskBadgeGroupProps) {
  if (!risk) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-[var(--radius-chip)] border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-danger-text)]",
          className,
        )}
        title={`${capabilityName}: mcp_risk.v1 unavailable`}
      >
        <ShieldQuestion className="h-3 w-3" strokeWidth={1.75} />
        Unknown risk
      </span>
    );
  }

  const riskClassTone = riskTone(risk.risk_class);
  const grantStateTone = grantTone(risk.grant_state);
  const Icon =
    risk.risk_class === "secret_access"
      ? LockKeyhole
      : risk.risk_class === "destructive_write" ||
          risk.risk_class === "code_execution" ||
          risk.risk_class === "unknown"
        ? AlertTriangle
        : risk.risk_class === "read_context"
          ? ShieldCheck
          : Wrench;

  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)}>
      <span
        className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] border px-2 py-0.5 text-[10px] font-medium"
        style={{
          background: `var(--tone-${riskClassTone}-bg)`,
          borderColor: `var(--tone-${riskClassTone}-border)`,
          color: `var(--tone-${riskClassTone}-text)`,
        }}
        title={risk.rationale ?? `${capabilityName}: ${risk.risk_class}`}
      >
        <Icon className="h-3 w-3" strokeWidth={1.75} />
        {formatValue(risk.risk_class)}
      </span>
      <span
        className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] border px-2 py-0.5 text-[10px] font-medium"
        style={{
          background: `var(--tone-${grantStateTone}-bg)`,
          borderColor: `var(--tone-${grantStateTone}-border)`,
          color: `var(--tone-${grantStateTone}-text)`,
        }}
        title={risk.policy_ref ?? undefined}
      >
        <StatusDot tone={grantStateTone} />
        {formatValue(risk.grant_state)}
      </span>
      {risk.redaction_required ? (
        <span className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--tone-warning-text)]">
          Redaction
        </span>
      ) : null}
    </span>
  );
}
