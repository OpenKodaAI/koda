"use client";

import { useMemo } from "react";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { ToggleField } from "@/components/control-plane/shared/toggle-field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { parseAutonomyPolicy, serializeAutonomyPolicy } from "@/lib/policy-serializers";
import { findFieldError } from "@/lib/system-settings-schema";

function asOptions(
  catalog: Array<Record<string, unknown>> | null | undefined,
  fallback: Array<{ value: string; label: string }>,
) {
  if (!Array.isArray(catalog) || catalog.length === 0) return fallback;
  return catalog.map((item) => ({
    value: String(item.id),
    label: String(item.label || item.id),
  }));
}

export function SectionIntelligence() {
  const { draft, setField, sectionErrors } = useSystemSettings();
  const { tl } = useAppI18n();
  const mk = draft.values.memory_and_knowledge;
  const catalogs = draft.catalogs ?? {};
  const intelligenceErrors = sectionErrors.intelligence;

  function update(next: Partial<typeof mk>) {
    setField("memory_and_knowledge", { ...mk, ...next });
  }

  // ── Autonomy policy helpers ──────────────────────────────────────────────
  const autonomyPolicy = useMemo(
    () => parseAutonomyPolicy(JSON.stringify(mk.autonomy_policy || {})),
    [mk.autonomy_policy],
  );

  function updateAutonomyTier(tier: string) {
    const next = { ...autonomyPolicy, default_autonomy_tier: tier };
    update({
      autonomy_policy: JSON.parse(serializeAutonomyPolicy(next)) as Record<string, unknown>,
    });
  }

  // ── Catalog options ──────────────────────────────────────────────────────
  // Fallbacks mirror the backend's `_GENERAL_{MEMORY,KNOWLEDGE}_PROFILES` IDs
  // so the select always has a matching option for the persisted value, even
  // if the backend didn't serve the catalogs (stale build).
  const memoryProfileOptions = useMemo(
    () =>
      asOptions(catalogs.memory_profiles, [
        { value: "conservative", label: "Conservador" },
        { value: "balanced", label: "Equilibrado" },
        { value: "strong_learning", label: "Aprendizado forte" },
      ]),
    [catalogs.memory_profiles],
  );

  const knowledgeProfileOptions = useMemo(
    () =>
      asOptions(catalogs.knowledge_profiles, [
        { value: "curated_only", label: "Curado apenas" },
        { value: "curated_workspace", label: "Curado + workspace" },
        { value: "curated_workspace_patterns", label: "Curado + workspace + padrões" },
      ]),
    [catalogs.knowledge_profiles],
  );

  const provenancePolicyOptions = useMemo(
    () =>
      asOptions(catalogs.provenance_policies, [
        { value: "standard", label: tl("Standard") },
        { value: "strict", label: tl("Strict") },
      ]),
    [catalogs.provenance_policies, tl],
  );

  const autonomyTierOptions = useMemo(
    () =>
      asOptions(catalogs.autonomy_tiers, [
        { value: "t0", label: "T0" },
        { value: "t1", label: "T1" },
        { value: "t2", label: "T2" },
      ]),
    [catalogs.autonomy_tiers],
  );

  return (
    <SettingsSectionShell
      sectionId="intelligence"
      title="settings.sections.intelligence.label"
      description="settings.sections.intelligence.description"
    >
      {/* ── Memory ──────────────────────────────────────────────────────── */}
      <SettingsFieldGroup title={tl("Memory")}>
        <ToggleField
          label="Memory enabled"
          description="Enable persistent memory and recall for bots."
          checked={mk.memory_enabled}
          onChange={(next) => update({ memory_enabled: next })}
        />

        <FieldShell
          label={tl("Memory profile")}
          description={tl("Preset baseline for retention, recall and maintenance.")}
          error={
            findFieldError(intelligenceErrors, "memory_and_knowledge.memory_policy.profile")
              ?.message
          }
        >
          <Select
            value={mk.memory_profile}
            onValueChange={(v) => update({ memory_profile: v })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {memoryProfileOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {tl(opt.label)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldShell>

        <ToggleField
          label="Procedural memory"
          description="Enable storage of procedural knowledge and learned workflows."
          checked={mk.procedural_enabled}
          onChange={(next) => update({ procedural_enabled: next })}
        />

        <ToggleField
          label="Proactive memory"
          description="Allow bots to proactively surface relevant memories."
          checked={mk.proactive_enabled}
          onChange={(next) => update({ proactive_enabled: next })}
        />
      </SettingsFieldGroup>

      {/* ── Knowledge ───────────────────────────────────────────────────── */}
      <SettingsFieldGroup title={tl("Knowledge")}>
        <ToggleField
          label="Knowledge enabled"
          description="Enable knowledge grounding and RAG for bots."
          checked={mk.knowledge_enabled}
          onChange={(next) => update({ knowledge_enabled: next })}
        />

        <FieldShell
          label={tl("Knowledge profile")}
          description={tl("Preset baseline for layers, recall and freshness.")}
          error={
            findFieldError(intelligenceErrors, "memory_and_knowledge.knowledge_policy.profile")
              ?.message
          }
        >
          <Select
            value={mk.knowledge_profile}
            onValueChange={(v) => update({ knowledge_profile: v })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {knowledgeProfileOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {tl(opt.label)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldShell>

        <FieldShell
          label={tl("Provenance policy")}
          description={tl("Governance baseline for owner and freshness requirements.")}
          error={
            findFieldError(
              intelligenceErrors,
              "memory_and_knowledge.knowledge_policy.provenance_policy",
            )?.message
          }
        >
          <Select
            value={mk.provenance_policy}
            onValueChange={(v) => update({ provenance_policy: v })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {provenancePolicyOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {tl(opt.label)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldShell>

      </SettingsFieldGroup>

      {/* ── Autonomy ─────────────────────────────────────────────────────── */}
      <SettingsFieldGroup title={tl("Autonomy")}>
        <FieldShell
          label={tl("Autonomy tier")}
          description={tl("Default operational autonomy tier for bot executions.")}
          error={
            findFieldError(
              intelligenceErrors,
              "memory_and_knowledge.autonomy_policy.default_autonomy_tier",
            )?.message
          }
        >
          <Select
            value={autonomyPolicy.default_autonomy_tier}
            onValueChange={updateAutonomyTier}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {autonomyTierOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {tl(opt.label)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldShell>
      </SettingsFieldGroup>

    </SettingsSectionShell>
  );
}
