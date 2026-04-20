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
  const { draft, setField } = useSystemSettings();
  const { tl } = useAppI18n();
  const mk = draft.values.memory_and_knowledge;
  const catalogs = draft.catalogs ?? {};

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
  const memoryProfileOptions = useMemo(
    () =>
      asOptions(catalogs.memory_profiles, [
        { value: "standard", label: "Standard" },
        { value: "minimal", label: "Minimal" },
        { value: "extended", label: "Extended" },
      ]),
    [catalogs.memory_profiles],
  );

  const knowledgeProfileOptions = useMemo(
    () =>
      asOptions(catalogs.knowledge_profiles, [
        { value: "standard", label: "Standard" },
        { value: "strict", label: "Strict" },
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

  const promotionModeOptions = useMemo(
    () =>
      asOptions(catalogs.approval_modes, [
        { value: "read_only", label: tl("Read only") },
        { value: "guarded", label: tl("Guarded") },
        { value: "supervised", label: tl("Supervised") },
        { value: "escalation_required", label: tl("Escalation required") },
      ]),
    [catalogs.approval_modes, tl],
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

        <FieldShell
          label={tl("Promotion mode")}
          description={tl("Controls how knowledge items are approved and promoted.")}
        >
          <Select
            value={mk.promotion_mode}
            onValueChange={(v) => update({ promotion_mode: v })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {promotionModeOptions.map((opt) => (
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
