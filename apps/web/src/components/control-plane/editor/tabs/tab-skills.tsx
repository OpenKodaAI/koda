"use client";

import { useMemo, useState, useCallback, useEffect } from "react";
import { translate } from "@/lib/i18n";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  PackageCheck,
  Plus,
  RotateCcw,
  ShieldAlert,
  Trash2,
  Wand2,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useAgentEditor } from "@/hooks/use-agent-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  FormInput,
  FormSelect,
  FormTextarea,
} from "@/components/control-plane/shared/form-field";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { ListEditorField } from "@/components/control-plane/shared/list-editor-field";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { ToggleField } from "@/components/control-plane/shared/toggle-field";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import {
  parseCustomSkills,
  parseSkillPolicy,
  serializeCustomSkills,
  serializeSkillPolicy,
  type CustomSkill,
} from "@/lib/policy-serializers";
import {
  parseSkillPackageLocks,
  parseSkillRegistry,
  parseSkillScanResult,
  skillPackageErrorMessage,
  type SkillPackageLock,
  type SkillRegistryItem,
  type SkillScanResult,
} from "@/lib/contracts/skill-package";

/*  Constants                                                                  */

const SKILL_CATEGORIES = [
  { value: "general", label: "controlPlane.skillCategories.general" },
  { value: "engineering", label: "controlPlane.skillCategories.engineering" },
  { value: "design", label: "controlPlane.skillCategories.design" },
  { value: "analysis", label: "controlPlane.skillCategories.analysis" },
  { value: "operations", label: "controlPlane.skillCategories.operations" },
  { value: "research", label: "controlPlane.skillCategories.research" },
  { value: "cloud", label: "controlPlane.skillCategories.cloud" },
] as const;

const CATEGORY_COLORS: Record<string, { bg: string; text: string }> = {
  engineering: {
    bg: "rgba(15,123,255,0.10)",
    text: "var(--tone-info-text)",
  },
  design: {
    bg: "rgba(190,75,219,0.10)",
    text: "#c472d4",
  },
  analysis: {
    bg: "rgba(245,159,0,0.10)",
    text: "var(--tone-warning-text)",
  },
  operations: {
    bg: "rgba(55,178,77,0.10)",
    text: "var(--tone-success-text)",
  },
  research: {
    bg: "rgba(32,201,151,0.10)",
    text: "#20c997",
  },
  cloud: {
    bg: "rgba(255,135,60,0.10)",
    text: "#ff873c",
  },
  general: {
    bg: "rgba(245,245,245,0.06)",
    text: "var(--text-tertiary)",
  },
};

const EASE_OUT: [number, number, number, number] = [0.22, 1, 0.36, 1];

/*  CategoryBadge                                                              */

function CategoryBadge({ category }: { category: string }) {
  const colors = CATEGORY_COLORS[category] ?? CATEGORY_COLORS.general;
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.14em]"
      style={{ backgroundColor: colors.bg, color: colors.text }}
    >
      {category}
    </span>
  );
}

function PackageMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-3 py-2">
      <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className="mt-1 truncate text-sm text-[var(--text-secondary)]">{value}</p>
    </div>
  );
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).map((item) => item.trim()).filter(Boolean) : [];
}

function summaryEntries(value: Record<string, unknown> | null | undefined): Array<[string, string]> {
  if (!value) return [];
  return Object.entries(value).flatMap(([key, item]) => {
    if (item === undefined || item === null || item === "") return [];
    if (typeof item === "object") return [[key, JSON.stringify(item)]];
    return [[key, String(item)]];
  });
}

function CompactSummary({ title, entries }: { title: string; entries: Array<[string, string]> }) {
  if (entries.length === 0) return null;
  return (
    <div className="border-t border-[var(--divider-hair)] pt-3">
      <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {title}
      </p>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1.5 text-xs md:grid-cols-2">
        {entries.map(([key, value]) => (
          <div key={key} className="min-w-0">
            <dt className="inline text-[var(--text-quaternary)]">{key}: </dt>
            <dd className="inline break-words text-[var(--text-secondary)]">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function AllowlistChips({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {label}
      </span>
      {items.map((item) => (
        <span
          key={item}
          className="max-w-full truncate rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-2 py-1 font-mono text-[10px] text-[var(--text-tertiary)]"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

async function skillPackageRequest(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(skillPackageErrorMessage(payload, `Request failed with status ${response.status}`));
  }
  return payload;
}

/*  TabSkills                                                                  */

export function TabSkills() {
  const { state, developerMode, updateAgentSpecField } = useAgentEditor();
  const { t } = useAppI18n();
  const agentId = state.agent.id;

  const skillPolicy = useMemo(
    () => parseSkillPolicy(state.skillPolicyJson),
    [state.skillPolicyJson],
  );
  const customSkills = useMemo(
    () => parseCustomSkills(state.customSkillsJson),
    [state.customSkillsJson],
  );

  function toggleSkillsEnabled(enabled: boolean) {
    const next = { ...skillPolicy, enabled };
    if (enabled) {
      if (!next.max_skills || next.max_skills < 1) next.max_skills = 6;
      if (!next.skill_budget_pct || next.skill_budget_pct <= 0) next.skill_budget_pct = 0.15;
    }
    updateAgentSpecField("skillPolicyJson", serializeSkillPolicy(next));
  }

  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [touched, setTouched] = useState<Record<string, Set<string>>>({});
  const [packagePath, setPackagePath] = useState("");
  const [packageLocks, setPackageLocks] = useState<SkillPackageLock[]>([]);
  const [skillRegistryItems, setSkillRegistryItems] = useState<SkillRegistryItem[]>([]);
  const [packageScan, setPackageScan] = useState<SkillScanResult | null>(null);
  const [packageError, setPackageError] = useState<string | null>(null);
  const [reviewAccepted, setReviewAccepted] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [packageBusy, setPackageBusy] = useState<
    "list" | "scan" | "install" | "uninstall" | "rollback" | "evals" | null
  >(null);

  const packageBasePath = `/api/control-plane/agents/${encodeURIComponent(agentId)}/skills/packages`;
  const registryPath = `/api/control-plane/agents/${encodeURIComponent(agentId)}/skills/registry`;
  const enabledSkills = useMemo(() => asStringList(skillPolicy.enabled_skills), [skillPolicy.enabled_skills]);
  const enabledSkillPackages = useMemo(
    () => asStringList(skillPolicy.enabled_skill_packages),
    [skillPolicy.enabled_skill_packages],
  );
  const reviewInstallReady =
    packageScan?.decision !== "review_required" || (reviewAccepted && reviewNote.trim().length > 0);

  const refreshPackages = useCallback(async () => {
    setPackageBusy((current) => current ?? "list");
    try {
      const [packagesPayload, registryPayload] = await Promise.all([
        skillPackageRequest(packageBasePath),
        skillPackageRequest(registryPath),
      ]);
      setPackageLocks(parseSkillPackageLocks(packagesPayload));
      setSkillRegistryItems(parseSkillRegistry(registryPayload).items);
      setPackageError(null);
    } catch (error) {
      setPackageError(error instanceof Error ? error.message : t("generated.controlPlane.failed_to_load_installed_packages_4d2e0b03"));
    } finally {
      setPackageBusy((current) => (current === "list" ? null : current));
    }
  }, [packageBasePath, registryPath, t]);

  useEffect(() => {
    void refreshPackages();
  }, [refreshPackages]);

  async function scanPackage() {
    setPackageBusy("scan");
    setPackageError(null);
    try {
      const payload = await skillPackageRequest(`${packageBasePath}/scan`, {
        method: "POST",
        body: JSON.stringify({ path: packagePath }),
      });
      const scan = parseSkillScanResult(payload);
      setPackageScan(scan);
      setReviewAccepted(false);
      setReviewNote("");
      if (!scan) setPackageError(t("generated.controlPlane.scan_response_did_not_match_the_skill_scan_v_6a19289e"));
    } catch (error) {
      setPackageScan(null);
      setPackageError(error instanceof Error ? error.message : t("generated.controlPlane.package_scan_failed_942444e7"));
    } finally {
      setPackageBusy(null);
    }
  }

  async function installPackage() {
    setPackageBusy("install");
    setPackageError(null);
    try {
      await skillPackageRequest(`${packageBasePath}/install`, {
        method: "POST",
        body: JSON.stringify({
          path: packagePath,
          ...(packageScan?.decision === "review_required"
            ? { review_accepted: true, review_note: reviewNote.trim() }
            : {}),
        }),
      });
      setPackageScan(null);
      setReviewAccepted(false);
      setReviewNote("");
      await refreshPackages();
    } catch (error) {
      setPackageError(error instanceof Error ? error.message : t("generated.controlPlane.package_install_failed_96014566"));
    } finally {
      setPackageBusy(null);
    }
  }

  async function uninstallPackage(packageId: string) {
    setPackageBusy("uninstall");
    setPackageError(null);
    try {
      await skillPackageRequest(`${packageBasePath}/${encodeURIComponent(packageId)}`, { method: "DELETE" });
      await refreshPackages();
    } catch (error) {
      setPackageError(error instanceof Error ? error.message : t("generated.controlPlane.package_uninstall_failed_d1bdc724"));
    } finally {
      setPackageBusy(null);
    }
  }

  async function rollbackPackage(packageId: string) {
    setPackageBusy("rollback");
    setPackageError(null);
    try {
      await skillPackageRequest(`${packageBasePath}/${encodeURIComponent(packageId)}/rollback`, { method: "POST" });
      await refreshPackages();
    } catch (error) {
      setPackageError(error instanceof Error ? error.message : t("generated.controlPlane.package_rollback_failed_bd8382d9"));
    } finally {
      setPackageBusy(null);
    }
  }

  async function runPackageEvals(packageId: string) {
    setPackageBusy("evals");
    setPackageError(null);
    try {
      await skillPackageRequest(`${packageBasePath}/${encodeURIComponent(packageId)}/evals/run`, { method: "POST" });
      await refreshPackages();
    } catch (error) {
      setPackageError(error instanceof Error ? error.message : t("generated.controlPlane.package_eval_run_failed_8775d80c"));
    } finally {
      setPackageBusy(null);
    }
  }

  const markTouched = useCallback((skillId: string, field: string) => {
    setTouched((prev) => {
      const fields = new Set(prev[skillId] ?? []);
      fields.add(field);
      return { ...prev, [skillId]: fields };
    });
  }, []);

  const isTouched = useCallback(
    (skillId: string, field: string) =>
      touched[skillId]?.has(field) ?? false,
    [touched],
  );

  function updateCustomSkills(skills: CustomSkill[]) {
    updateAgentSpecField(
      "customSkillsJson",
      serializeCustomSkills(skills),
    );
  }

  function addSkill() {
    const id = `skill-${Date.now()}`;
    updateCustomSkills([
      ...customSkills,
      { id, name: "", instruction: "", category: "general", content: "" },
    ]);
    setExpandedSkill(id);
  }

  function updateSkill(id: string, patch: Partial<CustomSkill>) {
    updateCustomSkills(
      customSkills.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
  }

  function deleteSkill(id: string) {
    updateCustomSkills(customSkills.filter((s) => s.id !== id));
    setConfirmDelete(null);
    if (expandedSkill === id) setExpandedSkill(null);
  }

  const skillToDelete = confirmDelete
    ? customSkills.find((s) => s.id === confirmDelete)
    : null;

  return (
    <div className="flex flex-col gap-6">
      {/* ── Custom Skills ─────────────────────────────────────── */}
      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <Wand2
              size={15}
              className="text-[var(--text-quaternary)]"
            />
            <h3 className="eyebrow">{t("generated.controlPlane.bot_skills_c6e75c49")}</h3>
          </div>
          <ToggleField
            label={t("generated.controlPlane.ativado_20975d23")}
            checked={skillPolicy.enabled !== false}
            onChange={toggleSkillsEnabled}
          />
        </div>

        {customSkills.length === 0 ? (
          /* ── Empty state ─────────────────────────────────────── */
          <div className="flex flex-col items-center gap-4 rounded-[1.15rem] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-tint)] px-6 py-10">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--tone-info-tint)]">
              <Wand2 size={20} className="text-[var(--tone-info-text)]" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-[var(--text-secondary)]">
                {t("generated.controlPlane.no_custom_skills_yet_d74a99c0")}
              </p>
              <p className="mt-1 max-w-xs text-xs leading-relaxed text-[var(--text-quaternary)]">
                {t(
                  "generated.controlPlane.skills_teach_the_agent_to_follow_specific_me_7df14ed5",
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={addSkill}
              className="mt-1 inline-flex items-center gap-2 rounded-xl bg-[var(--tone-info-tint)] px-4 py-2.5 text-sm font-medium text-[var(--tone-info-text)] transition-colors hover:bg-[rgba(15,123,255,0.18)]"
            >
              <Plus size={14} />
              {t("generated.controlPlane.create_first_skill_aa41c669")}
            </button>
          </div>
        ) : (
          /* ── Skill cards list ────────────────────────────────── */
          <div className="flex flex-col gap-2">
            {customSkills.map((skill) => {
              const isExpanded = expandedSkill === skill.id;
              const nameError =
                isTouched(skill.id, "name") && !skill.name.trim();

              return (
                <div
                  key={skill.id}
                  className="overflow-hidden rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] transition-colors"
                >
                  {/* Card header */}
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedSkill(isExpanded ? null : skill.id)
                    }
                    className={`flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-[rgba(255,255,255,0.02)]${skill.enabled === false ? " opacity-50" : ""}`}
                  >
                    <motion.span
                      animate={{ rotate: isExpanded ? 90 : 0 }}
                      transition={{ duration: 0.2, ease: EASE_OUT }}
                      className="text-[var(--text-quaternary)]"
                    >
                      <ChevronRight size={14} />
                    </motion.span>

                    <span className="flex min-w-0 flex-1 items-center gap-2.5">
                      <span className="truncate text-sm font-medium text-[var(--text-primary)]">
                        {skill.name || t("generated.controlPlane.unnamed_skill_1ad27319")}
                      </span>
                      <CategoryBadge category={skill.category || "general"} />
                    </span>

                    {skill.instruction && !isExpanded ? (
                      <span className="hidden max-w-[220px] truncate text-xs text-[var(--text-quaternary)] md:inline">
                        {skill.instruction}
                      </span>
                    ) : null}

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete(skill.id);
                      }}
                      className="ml-1 rounded-lg p-1.5 text-[var(--text-quaternary)] transition-colors hover:bg-[rgba(250,82,82,0.08)] hover:text-[var(--tone-danger-text)]"
                      aria-label={t("generated.controlPlane.remove_skill_dd547537")}
                    >
                      <Trash2 size={13} />
                    </button>
                  </button>

                  {/* Expanded form */}
                  <AnimatePresence initial={false}>
                    {isExpanded && (
                      <motion.div
                        key="form"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25, ease: EASE_OUT }}
                        className="overflow-hidden"
                      >
                        <div className="flex flex-col gap-5 border-t border-[var(--border-subtle)] px-5 pb-5 pt-5">
                          {/* ── Per-skill toggle ─────────────── */}
                          <ToggleField
                            label={t("generated.controlPlane.skill_ativa_947e3649")}
                            description={t("generated.controlPlane.desativar_esta_skill_sem_remove_la_f97ef5be")}
                            checked={skill.enabled !== false}
                            onChange={(checked) =>
                              updateSkill(skill.id, { enabled: checked })
                            }
                          />

                          {/* ── Essential fields ──────────────── */}
                          <FormInput
                            label={t("generated.controlPlane.name_8224cda4")}
                            description={t(
                              "generated.controlPlane.short_name_that_identifies_the_skill_a6dcfeed",
                            )}
                            required
                            value={skill.name}
                            onChange={(e) =>
                              updateSkill(skill.id, {
                                name: e.target.value,
                              })
                            }
                            onBlur={() => markTouched(skill.id, "name")}
                            placeholder={t("generated.controlPlane.e_g_deploy_review_sales_playbook_f4c2c240")}
                            error={
                              nameError
                                ? t("generated.controlPlane.name_is_required_dafacbff")
                                : undefined
                            }
                          />

                          <FormTextarea
                            label={t("generated.controlPlane.instruction_e87f44fd")}
                            description={t(
                              "generated.controlPlane.imperative_directive_the_model_receives_say__c79ff0fa",
                            )}
                            required
                            value={skill.instruction}
                            onChange={(e) =>
                              updateSkill(skill.id, {
                                instruction: e.target.value,
                              })
                            }
                            placeholder={t("generated.controlPlane.diretiva_imperativa_descrevendo_quando_e_com_4e9426de")}
                            rows={3}
                          />

                          <MarkdownEditorField
                            label={t("generated.controlPlane.content_178cbc41")}
                            description={t(
                              "generated.controlPlane.full_methodology_in_markdown_include_approac_eda7c4e5",
                            )}
                            value={skill.content}
                            onChange={(value) =>
                              updateSkill(skill.id, { content: value })
                            }
                            minHeight="200px"
                            placeholder={t("generated.controlPlane.metodologia_completa_em_markdown_inclua_abor_4942adcf")}
                          />

                          {/* ── Advanced fields (collapsible) ── */}
                          <SectionCollapsible
                            title={t("generated.controlPlane.advanced_settings_5c9eaab2")}
                          >
                            <div className="flex flex-col gap-5 pt-2">
                              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormSelect
                                  label={t("generated.controlPlane.category_6f28d7c2")}
                                  description={t(
                                    "generated.controlPlane.groups_the_skill_for_filtering_57a4a5cc",
                                  )}
                                  value={skill.category}
                                  onChange={(e) =>
                                    updateSkill(skill.id, {
                                      category: e.target.value,
                                    })
                                  }
                                  options={SKILL_CATEGORIES.map((c) => ({
                                    value: c.value,
                                    label: c.label,
                                  }))}
                                />
                                <div /> {/* grid spacer */}
                              </div>

                              <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                                <ListEditorField
                                  label={t("generated.controlPlane.aliases_8c6a41e0")}
                                  description={t(
                                    "generated.controlPlane.alternative_names_that_trigger_this_skill_a879e54a",
                                  )}
                                  items={skill.aliases ?? []}
                                  onChange={(items) =>
                                    updateSkill(skill.id, {
                                      aliases: items,
                                    })
                                  }
                                  placeholder={t("generated.controlPlane.e_g_dr_deploy_64ba850c")}
                                />
                                <ListEditorField
                                  label={t("generated.controlPlane.tags_33d58a76")}
                                  description={t(
                                    "generated.controlPlane.tags_for_classification_and_semantic_search_c5d2d427",
                                  )}
                                  items={skill.tags ?? []}
                                  onChange={(items) =>
                                    updateSkill(skill.id, { tags: items })
                                  }
                                  placeholder={t("generated.controlPlane.e_g_security_devops_6b8e14ff")}
                                />
                              </div>

                              <FormTextarea
                                label={t("generated.controlPlane.output_format_0ba4032c")}
                                description={t(
                                  "generated.controlPlane.format_constraint_the_model_should_follow_op_682b36f7",
                                )}
                                value={skill.output_format_enforcement ?? ""}
                                onChange={(e) =>
                                  updateSkill(skill.id, {
                                    output_format_enforcement:
                                      e.target.value || undefined,
                                  })
                                }
                                placeholder={t("generated.controlPlane.e_g_risks_as_severity_description_mitigation_b6a6d9f6")}
                                rows={2}
                              />
                            </div>
                          </SectionCollapsible>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}

            {/* Add button */}
            <button
              type="button"
              onClick={addSkill}
              className="inline-flex items-center gap-2 self-start rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-2.5 text-sm text-[var(--text-tertiary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)]"
            >
              <Plus size={14} />
              {t("generated.controlPlane.add_skill_d6c48d41")}
            </button>
          </div>
        )}
      </section>

      {/* ── Skill Packages ───────────────────────────────────── */}
      <section className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3 px-1">
          <div className="flex items-center gap-2">
            <PackageCheck size={15} className="text-[var(--text-quaternary)]" />
            <h3 className="eyebrow">{t("generated.controlPlane.skill_packages_fb8077a4")}</h3>
          </div>
          <button
            type="button"
            onClick={refreshPackages}
            disabled={packageBusy !== null}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-xs font-medium text-[var(--text-tertiary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw size={13} />
            {t("generated.controlPlane.refresh_9da693db")}
          </button>
        </div>

        {enabledSkills.length > 0 || enabledSkillPackages.length > 0 ? (
          <div className="flex flex-col gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3">
            <AllowlistChips label={t("generated.controlPlane.enabled_skills_d7bfdfdc")} items={enabledSkills} />
            <AllowlistChips label={t("generated.controlPlane.enabled_packages_f322af83")} items={enabledSkillPackages} />
          </div>
        ) : null}

        {skillRegistryItems.length > 0 ? (
          <div className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4">
            <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("generated.controlPlane.local_trust_registry_b46f25c2")}
            </p>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              {skillRegistryItems.slice(0, 6).map((item) => (
                <div
                  key={`${item.package_id}-${item.package_hash}`}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-3 text-xs"
                >
                  <div className="flex min-w-0 items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-[var(--text-secondary)]">
                        {item.name} {translate("generated.controlPlane.v_76abe6e8")}{item.version}
                      </p>
                      <p className="mt-1 truncate font-mono text-[10px] text-[var(--text-quaternary)]">
                        {item.package_id}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-lg border border-[var(--border-subtle)] px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                      {item.recommendation_status}
                    </span>
                  </div>
                  <CompactSummary
                    title={t("generated.controlPlane.registry_evidence_10be9a40")}
                    entries={[
                      ["scanner", String(item.scan_summary.decision ?? "")],
                      ["installed", String(item.installed)],
                      ["rollback", String(item.rollback_available)],
                      ["run_graph", String(item.run_graph_evidence.node_id ?? "")],
                    ].filter((entry): entry is [string, string] => Boolean(entry[1]))}
                  />
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-5">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_auto] lg:items-end">
            <FormInput
              label={t("generated.controlPlane.package_path_f01cfd9c")}
              description={t("generated.controlPlane.local_folder_or_manifest_path_the_backend_sc_bf0f7b74")}
              value={packagePath}
              onChange={(event) => {
                setPackagePath(event.target.value);
                setPackageScan(null);
                setReviewAccepted(false);
                setReviewNote("");
              }}
              placeholder="~/koda-skills/example-safe"
            />
            <button
              type="button"
              onClick={scanPackage}
              disabled={!packagePath.trim() || packageBusy !== null}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-[var(--border-subtle)] px-4 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ShieldAlert size={15} />
              {packageBusy === "scan" ? t("generated.controlPlane.scanning_f98594ca") : t("generated.controlPlane.scan_e37b96bf")}
            </button>
            <button
              type="button"
              onClick={installPackage}
              disabled={
                !packagePath.trim() ||
                packageBusy !== null ||
                packageScan?.decision === "deny" ||
                !reviewInstallReady
              }
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-[var(--tone-info-tint)] px-4 text-sm font-medium text-[var(--tone-info-text)] transition-colors hover:bg-[rgba(15,123,255,0.18)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <CheckCircle2 size={15} />
              {packageScan?.decision === "review_required" ? t("generated.controlPlane.install_after_review_e63df26d") : t("generated.controlPlane.install_393a9334")}
            </button>
          </div>

          {packageError ? (
            <div className="mt-4 flex gap-2 rounded-xl border border-[rgba(250,82,82,0.25)] bg-[rgba(250,82,82,0.08)] px-3 py-2 text-xs leading-relaxed text-[var(--tone-danger-text)]">
              <XCircle size={14} className="mt-0.5 shrink-0" />
              <span>{packageError}</span>
            </div>
          ) : null}

          {packageScan ? (
            <div className="mt-5 flex flex-col gap-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {packageScan.package.name} {translate("generated.controlPlane.v_76abe6e8")}{packageScan.package.version}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-quaternary)]">
                    {packageScan.package.id} · {packageScan.scanner_version}
                  </p>
                </div>
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                    packageScan.decision === "allow"
                      ? "bg-[var(--tone-success-tint)] text-[var(--tone-success-text)]"
                      : packageScan.decision === "deny"
                        ? "bg-[rgba(250,82,82,0.10)] text-[var(--tone-danger-text)]"
                        : "bg-[var(--tone-warning-tint)] text-[var(--tone-warning-text)]"
                  }`}
                >
                  {packageScan.decision}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <PackageMetric label={t("generated.controlPlane.skills_70e85cf8")} value={String(packageScan.package.skills.length)} />
                <PackageMetric label={t("generated.controlPlane.tools_47663a5c")} value={String(packageScan.package.tools.length)} />
                <PackageMetric label={t("generated.controlPlane.risk_classes_25aba3f9")} value={packageScan.risk_classes.join(", ") || t("generated.controlPlane.none_7fb53bb1")} />
              </div>

              <CompactSummary
                title={t("generated.controlPlane.provenance_cea55c77")}
                entries={[
                  ["author", packageScan.package.author],
                  ["source", packageScan.package.source ?? ""],
                  ["manifest", packageScan.package.manifest_path ?? packageScan.package.path ?? ""],
                  ["package_hash", packageScan.package_hash],
                ].filter((entry): entry is [string, string] => Boolean(entry[1]))}
              />

              {packageScan.decision === "review_required" ? (
                <div className="flex flex-col gap-3 rounded-xl border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] p-3">
                  <label className="flex items-start gap-2 text-xs text-[var(--tone-warning-text)]">
                    <input
                      type="checkbox"
                      checked={reviewAccepted}
                      onChange={(event) => setReviewAccepted(event.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-[var(--border-strong)] bg-[var(--surface-canvas)]"
                    />
                    <span>{t("generated.controlPlane.i_reviewed_the_scanner_findings_and_accept_t_74a7240a")}</span>
                  </label>
                  <FormTextarea
                    label={t("generated.controlPlane.review_note_c201714c")}
                    description={t("generated.controlPlane.required_for_review_required_installs_45caef9a")}
                    value={reviewNote}
                    onChange={(event) => setReviewNote(event.target.value)}
                    placeholder={t("generated.controlPlane.why_this_package_is_acceptable_for_this_agen_63088712")}
                    rows={2}
                  />
                </div>
              ) : null}

              {Object.keys(packageScan.permissions_requested).length > 0 ? (
                <pre className="max-h-40 overflow-auto rounded-xl border border-[var(--border-subtle)] bg-[rgba(0,0,0,0.18)] p-3 text-xs text-[var(--text-tertiary)]">
                  {JSON.stringify(packageScan.permissions_requested, null, 2)}
                </pre>
              ) : null}

              {packageScan.findings.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {packageScan.findings.map((finding) => (
                    <div
                      key={`${finding.id}-${finding.path}-${finding.message}`}
                      className="flex gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-3 py-2 text-xs"
                    >
                      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[var(--tone-warning-text)]" />
                      <div className="min-w-0">
                        <p className="font-medium text-[var(--text-secondary)]">
                          {finding.severity} · {finding.id}
                        </p>
                        <p className="mt-1 text-[var(--text-quaternary)]">{finding.message}</p>
                        {finding.path ? (
                          <p className="mt-1 truncate font-mono text-[10px] text-[var(--text-quaternary)]">
                            {finding.path}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-quaternary)]">{t("generated.controlPlane.no_findings_reported_by_scanner_401ba83e")}</p>
              )}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          {packageLocks.length === 0 ? (
            <div className="rounded-[1.15rem] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-tint)] px-5 py-6 text-sm text-[var(--text-quaternary)]">
              {t("generated.controlPlane.no_installed_skill_packages_custom_skills_ab_c1972733")}
            </div>
          ) : (
            packageLocks.map((lock) => (
              <div
                key={`${lock.package_id}-${lock.package_hash}`}
                className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                      {lock.name} {translate("generated.controlPlane.v_76abe6e8")}{lock.version}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-quaternary)]">
                      {lock.package_id} · {lock.installed_skills.length} {t("generated.controlPlane.skills_fc57c4a4")} · {lock.installed_tools.length}{" "}
                      {t("generated.controlPlane.tools_c8224289")}
                    </p>
                    {lock.package_path ? (
                      <p className="mt-2 truncate font-mono text-[10px] text-[var(--text-quaternary)]">
                        {lock.package_path}
                      </p>
                    ) : null}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {lock.recommendation_status ? (
                        <span className="rounded-lg border border-[var(--border-subtle)] px-2 py-1 text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                          {lock.recommendation_status}
                        </span>
                      ) : null}
                      {lock.installed_at ? (
                        <span className="rounded-lg border border-[var(--border-subtle)] px-2 py-1 font-mono text-[10px] text-[var(--text-quaternary)]">
                          {t("generated.controlPlane.installed_2fc4a4e0")} {lock.installed_at}
                        </span>
                      ) : null}
                      {lock.rollback_ref ? (
                        <span className="rounded-lg border border-[var(--border-subtle)] px-2 py-1 font-mono text-[10px] text-[var(--text-quaternary)]">
                          {t("generated.controlPlane.rollback_68d0d254")} {lock.rollback_ref}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => runPackageEvals(lock.package_id)}
                      disabled={packageBusy !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-tertiary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <CheckCircle2 size={13} />
                      {packageBusy === "evals" ? t("generated.controlPlane.running_evals_359a2c6d") : t("generated.controlPlane.run_evals_56040b57")}
                    </button>
                    <button
                      type="button"
                      onClick={() => rollbackPackage(lock.package_id)}
                      disabled={!lock.rollback_ref || packageBusy !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-tertiary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RotateCcw size={13} />
                      {t("generated.controlPlane.rollback_299e720f")}
                    </button>
                    <button
                      type="button"
                      onClick={() => uninstallPackage(lock.package_id)}
                      disabled={packageBusy !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[rgba(250,82,82,0.30)] px-3 py-2 text-xs text-[var(--tone-danger-text)] transition-colors hover:bg-[rgba(250,82,82,0.08)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Trash2 size={13} />
                      {t("generated.controlPlane.uninstall_00e07cef")}
                    </button>
                  </div>
                </div>
                <div className="mt-4 flex flex-col gap-3 text-xs">
                  <CompactSummary
                    title={t("generated.controlPlane.provenance_cea55c77")}
                    entries={[
                      ["source", lock.source ?? ""],
                      ["manifest", lock.manifest_path ?? ""],
                      ["package_hash", lock.package_hash],
                      ...summaryEntries((lock as Record<string, unknown>).provenance as Record<string, unknown> | undefined),
                    ].filter((entry): entry is [string, string] => Boolean(entry[1]))}
                  />
                  <CompactSummary title={t("generated.controlPlane.trust_3feaa921")} entries={summaryEntries(lock.trust_summary)} />
                  <CompactSummary title={t("generated.controlPlane.eval_summary_51ea59cf")} entries={summaryEntries(lock.eval_summary)} />
                  {lock.skill_evals.length > 0 ? (
                    <div className="border-t border-[var(--divider-hair)] pt-3">
                      <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                        {t("generated.controlPlane.skill_evals_d0eac852")}
                      </p>
                      <div className="mt-2 flex flex-col gap-1.5">
                        {lock.skill_evals.slice(0, 5).map((item, index) => {
                          const result = typeof item.result === "object" && item.result !== null
                            ? item.result as Record<string, unknown>
                            : {};
                          const evalId = String(item.eval_id ?? item.id ?? item.name ?? `eval-${index + 1}`);
                          const status = result.status ? String(result.status) : item.status ? String(item.status) : "";
                          const summary = item.summary ? String(item.summary) : "";
                          return (
                            <div
                              key={`${evalId}-${index}`}
                              className="min-w-0 rounded-lg border border-[var(--border-subtle)] px-2 py-1.5"
                            >
                              <p className="truncate text-[var(--text-secondary)]">
                                {evalId}
                                {status ? <span className="text-[var(--text-quaternary)]"> · {status}</span> : null}
                              </p>
                              {summary ? (
                                <p className="mt-0.5 line-clamp-2 text-[var(--text-quaternary)]">{summary}</p>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* ── Section 3: Developer Mode ────────────────────────── */}
      {developerMode ? (
        <section className="border-t border-[var(--border-subtle)] pt-4">
          <SectionCollapsible
            title={t("generated.controlPlane.advanced_json_0710ef44")}
          >
            <div className="flex flex-col gap-6 pt-3">
              <JsonEditorField
                label={t("generated.controlPlane.skill_policy_dc326581")}
                description={t(
                  "generated.controlPlane.complete_skill_policy_schema_6c7313ed",
                )}
                value={state.skillPolicyJson}
                onChange={(value) =>
                  updateAgentSpecField("skillPolicyJson", value)
                }
              />
              <JsonEditorField
                label={t("generated.controlPlane.custom_skills_6f7f0bb1")}
                description={t(
                  "generated.controlPlane.custom_skills_array_in_json_format_96fe35d6",
                )}
                value={state.customSkillsJson}
                onChange={(value) =>
                  updateAgentSpecField("customSkillsJson", value)
                }
              />
            </div>
          </SectionCollapsible>
        </section>
      ) : null}

      {/* ── Delete confirmation ───────────────────────────────── */}
      <ConfirmationDialog
        open={confirmDelete !== null}
        title={t("generated.controlPlane.remove_skill_dd547537")}
        message={
          skillToDelete
            ? t(
                "generated.controlPlane.are_you_sure_you_want_to_remove_name_this_ac_47fdd888",
                { name: skillToDelete.name || t("generated.controlPlane.unnamed_skill_1ad27319") },
              )
            : ""
        }
        confirmLabel={t("generated.controlPlane.remove_1a281247")}
        onConfirm={() => confirmDelete && deleteSkill(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
