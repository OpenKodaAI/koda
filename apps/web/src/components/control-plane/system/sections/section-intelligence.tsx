"use client";

import { useMemo } from "react";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { SettingsSectionShell } from "@/components/control-plane/system/settings-section-shell";
import { SettingsFieldGroup } from "@/components/control-plane/system/settings-field-group";
import { FieldShell } from "@/components/control-plane/system/shared/field-shell";
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
        <FieldShell
          label={tl("Memory enabled")}
          description={tl("Enable persistent memory and recall for agents.")}
        >
          <label className="inline-flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              className="sr-only"
              checked={mk.memory_enabled}
              onChange={(e) => update({ memory_enabled: e.target.checked })}
            />
            <div
              className={`relative h-5 w-9 rounded-full transition-colors ${
                mk.memory_enabled
                  ? "bg-[rgba(113,219,190,0.6)]"
                  : "bg-[var(--border-subtle)]"
              }`}
            >
              <div
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  mk.memory_enabled ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </div>
            <span className="text-sm text-[var(--text-secondary)]">
              {mk.memory_enabled ? tl("Enabled") : tl("Disabled")}
            </span>
          </label>
        </FieldShell>

        <FieldShell
          label={tl("Memory profile")}
          description={tl("Preset baseline for retention, recall and maintenance.")}
        >
          <select
            className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
            value={mk.memory_profile}
            onChange={(e) => update({ memory_profile: e.target.value })}
          >
            {memoryProfileOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {tl(opt.label)}
              </option>
            ))}
          </select>
        </FieldShell>

        <FieldShell
          label={tl("Procedural memory")}
          description={tl("Enable storage of procedural knowledge and learned workflows.")}
        >
          <label className="inline-flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              className="sr-only"
              checked={mk.procedural_enabled}
              onChange={(e) => update({ procedural_enabled: e.target.checked })}
            />
            <div
              className={`relative h-5 w-9 rounded-full transition-colors ${
                mk.procedural_enabled
                  ? "bg-[rgba(113,219,190,0.6)]"
                  : "bg-[var(--border-subtle)]"
              }`}
            >
              <div
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  mk.procedural_enabled ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </div>
            <span className="text-sm text-[var(--text-secondary)]">
              {mk.procedural_enabled ? tl("Enabled") : tl("Disabled")}
            </span>
          </label>
        </FieldShell>

        <FieldShell
          label={tl("Proactive memory")}
          description={tl("Allow agents to proactively surface relevant memories.")}
        >
          <label className="inline-flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              className="sr-only"
              checked={mk.proactive_enabled}
              onChange={(e) => update({ proactive_enabled: e.target.checked })}
            />
            <div
              className={`relative h-5 w-9 rounded-full transition-colors ${
                mk.proactive_enabled
                  ? "bg-[rgba(113,219,190,0.6)]"
                  : "bg-[var(--border-subtle)]"
              }`}
            >
              <div
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  mk.proactive_enabled ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </div>
            <span className="text-sm text-[var(--text-secondary)]">
              {mk.proactive_enabled ? tl("Enabled") : tl("Disabled")}
            </span>
          </label>
        </FieldShell>
      </SettingsFieldGroup>

      {/* ── Knowledge ───────────────────────────────────────────────────── */}
      <SettingsFieldGroup title={tl("Knowledge")}>
        <FieldShell
          label={tl("Knowledge enabled")}
          description={tl("Enable knowledge grounding and RAG for agents.")}
        >
          <label className="inline-flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              className="sr-only"
              checked={mk.knowledge_enabled}
              onChange={(e) => update({ knowledge_enabled: e.target.checked })}
            />
            <div
              className={`relative h-5 w-9 rounded-full transition-colors ${
                mk.knowledge_enabled
                  ? "bg-[rgba(113,219,190,0.6)]"
                  : "bg-[var(--border-subtle)]"
              }`}
            >
              <div
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  mk.knowledge_enabled ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </div>
            <span className="text-sm text-[var(--text-secondary)]">
              {mk.knowledge_enabled ? tl("Enabled") : tl("Disabled")}
            </span>
          </label>
        </FieldShell>

        <FieldShell
          label={tl("Knowledge profile")}
          description={tl("Preset baseline for layers, recall and freshness.")}
        >
          <select
            className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
            value={mk.knowledge_profile}
            onChange={(e) => update({ knowledge_profile: e.target.value })}
          >
            {knowledgeProfileOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {tl(opt.label)}
              </option>
            ))}
          </select>
        </FieldShell>

        <FieldShell
          label={tl("Provenance policy")}
          description={tl("Governance baseline for owner and freshness requirements.")}
        >
          <select
            className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
            value={mk.provenance_policy}
            onChange={(e) => update({ provenance_policy: e.target.value })}
          >
            {provenancePolicyOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {tl(opt.label)}
              </option>
            ))}
          </select>
        </FieldShell>

        <FieldShell
          label={tl("Promotion mode")}
          description={tl("Controls how knowledge items are approved and promoted.")}
        >
          <select
            className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
            value={mk.promotion_mode}
            onChange={(e) => update({ promotion_mode: e.target.value })}
          >
            {promotionModeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {tl(opt.label)}
              </option>
            ))}
          </select>
        </FieldShell>
      </SettingsFieldGroup>

      {/* ── Autonomy ─────────────────────────────────────────────────────── */}
      <SettingsFieldGroup title={tl("Autonomy")}>
        <FieldShell
          label={tl("Autonomy tier")}
          description={tl("Default operational autonomy tier for agent executions.")}
        >
          <select
            className="field-shell px-4 py-2.5 text-sm text-[var(--text-primary)]"
            value={autonomyPolicy.default_autonomy_tier}
            onChange={(e) => updateAutonomyTier(e.target.value)}
          >
            {autonomyTierOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {tl(opt.label)}
              </option>
            ))}
          </select>
        </FieldShell>
      </SettingsFieldGroup>

    </SettingsSectionShell>
  );
}
