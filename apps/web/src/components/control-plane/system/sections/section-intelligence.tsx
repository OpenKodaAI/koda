"use client";

import { useMemo } from "react";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
import { ToggleField } from "@/components/control-plane/shared/toggle-field";
import { EmbeddingModelPicker } from "@/components/control-plane/system/sections/embedding-model-picker";
import { translate } from "@/lib/i18n";
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
  const { t, tl } = useAppI18n();
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
        { value: "conservative", label: "controlPlane.intelligence.memoryProfiles.conservative" },
        { value: "balanced", label: "controlPlane.intelligence.memoryProfiles.balanced" },
        { value: "strong_learning", label: "controlPlane.intelligence.memoryProfiles.strongLearning" },
      ]),
    [catalogs.memory_profiles],
  );

  const knowledgeProfileOptions = useMemo(
    () =>
      asOptions(catalogs.knowledge_profiles, [
        { value: "curated_only", label: "controlPlane.intelligence.knowledgeProfiles.curatedOnly" },
        { value: "curated_workspace", label: "controlPlane.intelligence.knowledgeProfiles.curatedWorkspace" },
        {
          value: "curated_workspace_patterns",
          label: "controlPlane.intelligence.knowledgeProfiles.curatedWorkspacePatterns",
        },
      ]),
    [catalogs.knowledge_profiles],
  );

  const provenancePolicyOptions = useMemo(
    () =>
      asOptions(catalogs.provenance_policies, [
        { value: "standard", label: t("generated.controlPlane.standard_ec6537f7") },
        { value: "strict", label: t("generated.controlPlane.strict_d1df64ff") },
      ]),
    [catalogs.provenance_policies, t],
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
      title={translate("generated.controlPlane.settings_sections_intelligence_label_5f1c5ee4")}
      description={translate("generated.controlPlane.settings_sections_intelligence_description_bb278541")}
    >
      {/* ── Memory ──────────────────────────────────────────────────────── */}
      <SettingsFieldGroup title={t("generated.controlPlane.memory_9aa6101b")}>
        <ToggleField
          label={t("generated.controlPlane.memory_enabled_cdbdeb65")}
          description={t("generated.controlPlane.enable_persistent_memory_and_recall_for_agen_97d1b42a")}
          checked={mk.memory_enabled}
          onChange={(next) => update({ memory_enabled: next })}
        />

        <FieldShell
          label={t("generated.controlPlane.memory_profile_81c8bd70")}
          description={t("generated.controlPlane.preset_baseline_for_retention_recall_and_mai_e586e017")}
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
          label={t("generated.controlPlane.procedural_memory_54c924ab")}
          description={t("generated.controlPlane.enable_storage_of_procedural_knowledge_and_l_04c8d09e")}
          checked={mk.procedural_enabled}
          onChange={(next) => update({ procedural_enabled: next })}
        />

        <ToggleField
          label={t("generated.controlPlane.proactive_memory_ff96b94a")}
          description={t("generated.controlPlane.allow_agents_to_proactively_surface_relevant_beaa45a1")}
          checked={mk.proactive_enabled}
          onChange={(next) => update({ proactive_enabled: next })}
        />

        <FieldShell
          label={t("generated.controlPlane.modelo_de_embedding_0ed9f55e")}
          description={t("controlPlane.intelligence.embeddingModelDescription")}
        >
          <EmbeddingModelPicker memoryEnabled={mk.memory_enabled} />
        </FieldShell>
      </SettingsFieldGroup>

      {/* ── Knowledge ───────────────────────────────────────────────────── */}
      <SettingsFieldGroup title={t("generated.controlPlane.knowledge_b125a195")}>
        <ToggleField
          label={t("generated.controlPlane.knowledge_enabled_fe557f9d")}
          description={t("generated.controlPlane.enable_knowledge_grounding_and_rag_for_agent_fd201a99")}
          checked={mk.knowledge_enabled}
          onChange={(next) => update({ knowledge_enabled: next })}
        />

        <FieldShell
          label={t("generated.controlPlane.knowledge_profile_77ba3b95")}
          description={t("generated.controlPlane.preset_baseline_for_layers_recall_and_freshn_4d23704e")}
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
          label={t("generated.controlPlane.provenance_policy_bb7a1848")}
          description={t("generated.controlPlane.governance_baseline_for_owner_and_freshness__2fa85a58")}
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
      <SettingsFieldGroup title={t("generated.controlPlane.autonomy_99129e59")}>
        <FieldShell
          label={t("generated.controlPlane.autonomy_tier_cf2b9d75")}
          description={t("generated.controlPlane.default_operational_autonomy_tier_for_bot_ex_310edc03")}
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
