"use client";

import { useMemo, useState, useCallback, useEffect } from "react";
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
  parseSkillScanResult,
  skillPackageErrorMessage,
  type SkillPackageLock,
  type SkillScanResult,
} from "@/lib/contracts/skill-package";

/*  Constants                                                                  */

const SKILL_CATEGORIES = [
  { value: "general", label: "General" },
  { value: "engineering", label: "Engineering" },
  { value: "design", label: "Design" },
  { value: "analysis", label: "Analysis" },
  { value: "operations", label: "Operations" },
  { value: "research", label: "Research" },
  { value: "cloud", label: "Cloud" },
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
  const { tl } = useAppI18n();
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
  const [packageScan, setPackageScan] = useState<SkillScanResult | null>(null);
  const [packageError, setPackageError] = useState<string | null>(null);
  const [packageBusy, setPackageBusy] = useState<"list" | "scan" | "install" | "uninstall" | "rollback" | null>(null);

  const packageBasePath = `/api/control-plane/agents/${encodeURIComponent(agentId)}/skills/packages`;

  const refreshPackages = useCallback(async () => {
    setPackageBusy((current) => current ?? "list");
    try {
      const payload = await skillPackageRequest(packageBasePath);
      setPackageLocks(parseSkillPackageLocks(payload));
      setPackageError(null);
    } catch (error) {
      setPackageError(error instanceof Error ? error.message : tl("Failed to load installed packages."));
    } finally {
      setPackageBusy((current) => (current === "list" ? null : current));
    }
  }, [packageBasePath, tl]);

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
      if (!scan) setPackageError(tl("Scan response did not match the skill_scan.v1 contract."));
    } catch (error) {
      setPackageScan(null);
      setPackageError(error instanceof Error ? error.message : tl("Package scan failed."));
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
          review_accepted: packageScan?.decision === "review_required",
        }),
      });
      setPackageScan(null);
      await refreshPackages();
    } catch (error) {
      setPackageError(error instanceof Error ? error.message : tl("Package install failed."));
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
      setPackageError(error instanceof Error ? error.message : tl("Package uninstall failed."));
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
      setPackageError(error instanceof Error ? error.message : tl("Package rollback failed."));
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
            <h3 className="eyebrow">{tl("Bot skills")}</h3>
          </div>
          <ToggleField
            label={tl("Ativado")}
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
                {tl("No custom skills yet")}
              </p>
              <p className="mt-1 max-w-xs text-xs leading-relaxed text-[var(--text-quaternary)]">
                {tl(
                  "Skills teach the agent to follow specific methodologies. Define criteria, formats, and examples for more precise responses.",
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={addSkill}
              className="mt-1 inline-flex items-center gap-2 rounded-xl bg-[var(--tone-info-tint)] px-4 py-2.5 text-sm font-medium text-[var(--tone-info-text)] transition-colors hover:bg-[rgba(15,123,255,0.18)]"
            >
              <Plus size={14} />
              {tl("Create first skill")}
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
                        {skill.name || tl("Unnamed skill")}
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
                      aria-label={tl("Remove skill")}
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
                            label={tl("Skill ativa")}
                            description={tl("Desativar esta skill sem remove-la.")}
                            checked={skill.enabled !== false}
                            onChange={(checked) =>
                              updateSkill(skill.id, { enabled: checked })
                            }
                          />

                          {/* ── Essential fields ──────────────── */}
                          <FormInput
                            label={tl("Name")}
                            description={tl(
                              "Short name that identifies the skill.",
                            )}
                            required
                            value={skill.name}
                            onChange={(e) =>
                              updateSkill(skill.id, {
                                name: e.target.value,
                              })
                            }
                            onBlur={() => markTouched(skill.id, "name")}
                            placeholder={tl("e.g. deploy-review, sales-playbook")}
                            error={
                              nameError
                                ? tl("Name is required")
                                : undefined
                            }
                          />

                          <FormTextarea
                            label={tl("Instruction")}
                            description={tl(
                              "Imperative directive the model receives. Say WHAT to do and HOW to structure the response.",
                            )}
                            required
                            value={skill.instruction}
                            onChange={(e) =>
                              updateSkill(skill.id, {
                                instruction: e.target.value,
                              })
                            }
                            placeholder={tl("Diretiva imperativa descrevendo QUANDO e COMO o agente deve usar esta skill")}
                            rows={3}
                          />

                          <MarkdownEditorField
                            label={tl("Content *")}
                            description={tl(
                              "Full methodology in Markdown. Include approach, criteria, examples, and output format.",
                            )}
                            value={skill.content}
                            onChange={(value) =>
                              updateSkill(skill.id, { content: value })
                            }
                            minHeight="200px"
                            placeholder={tl("Metodologia completa em Markdown. Inclua ## Abordagem, ## Formato de Saída, ## Princípios Chave")}
                          />

                          {/* ── Advanced fields (collapsible) ── */}
                          <SectionCollapsible
                            title={tl("Advanced settings")}
                          >
                            <div className="flex flex-col gap-5 pt-2">
                              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormSelect
                                  label={tl("Category")}
                                  description={tl(
                                    "Groups the skill for filtering.",
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
                                  label={tl("Aliases")}
                                  description={tl(
                                    "Alternative names that trigger this skill.",
                                  )}
                                  items={skill.aliases ?? []}
                                  onChange={(items) =>
                                    updateSkill(skill.id, {
                                      aliases: items,
                                    })
                                  }
                                  placeholder={tl("e.g. dr, deploy")}
                                />
                                <ListEditorField
                                  label={tl("Tags")}
                                  description={tl(
                                    "Tags for classification and semantic search.",
                                  )}
                                  items={skill.tags ?? []}
                                  onChange={(items) =>
                                    updateSkill(skill.id, { tags: items })
                                  }
                                  placeholder={tl("e.g. security, devops")}
                                />
                              </div>

                              <FormTextarea
                                label={tl("Output format")}
                                description={tl(
                                  "Format constraint the model should follow. Optional but recommended.",
                                )}
                                value={skill.output_format_enforcement ?? ""}
                                onChange={(e) =>
                                  updateSkill(skill.id, {
                                    output_format_enforcement:
                                      e.target.value || undefined,
                                  })
                                }
                                placeholder={tl("e.g. **Risks** as [Severity] description → mitigation. **Summary** with 3 action items.")}
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
              {tl("Add skill")}
            </button>
          </div>
        )}
      </section>

      {/* ── Skill Packages ───────────────────────────────────── */}
      <section className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3 px-1">
          <div className="flex items-center gap-2">
            <PackageCheck size={15} className="text-[var(--text-quaternary)]" />
            <h3 className="eyebrow">{tl("Skill packages")}</h3>
          </div>
          <button
            type="button"
            onClick={refreshPackages}
            disabled={packageBusy !== null}
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-xs font-medium text-[var(--text-tertiary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw size={13} />
            {tl("Refresh")}
          </button>
        </div>

        <div className="rounded-[1.15rem] border border-[var(--border-subtle)] bg-[var(--surface-canvas)] p-5">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_auto] lg:items-end">
            <FormInput
              label={tl("Package path")}
              description={tl("Local folder or manifest path. The backend scans statically before install.")}
              value={packagePath}
              onChange={(event) => setPackagePath(event.target.value)}
              placeholder="~/koda-skills/example-safe"
            />
            <button
              type="button"
              onClick={scanPackage}
              disabled={!packagePath.trim() || packageBusy !== null}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-[var(--border-subtle)] px-4 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-strong)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ShieldAlert size={15} />
              {packageBusy === "scan" ? tl("Scanning") : tl("Scan")}
            </button>
            <button
              type="button"
              onClick={installPackage}
              disabled={!packagePath.trim() || packageBusy !== null || packageScan?.decision === "deny"}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-[var(--tone-info-tint)] px-4 text-sm font-medium text-[var(--tone-info-text)] transition-colors hover:bg-[rgba(15,123,255,0.18)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <CheckCircle2 size={15} />
              {packageScan?.decision === "review_required" ? tl("Install after review") : tl("Install")}
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
                    {packageScan.package.name} v{packageScan.package.version}
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
                <PackageMetric label={tl("Skills")} value={String(packageScan.package.skills.length)} />
                <PackageMetric label={tl("Tools")} value={String(packageScan.package.tools.length)} />
                <PackageMetric label={tl("Risk classes")} value={packageScan.risk_classes.join(", ") || tl("none")} />
              </div>

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
                <p className="text-xs text-[var(--text-quaternary)]">{tl("No findings reported by scanner.")}</p>
              )}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          {packageLocks.length === 0 ? (
            <div className="rounded-[1.15rem] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-tint)] px-5 py-6 text-sm text-[var(--text-quaternary)]">
              {tl("No installed skill packages. Custom skills above remain unchanged.")}
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
                      {lock.name} v{lock.version}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-quaternary)]">
                      {lock.package_id} · {lock.installed_skills.length} {tl("skills")} · {lock.installed_tools.length}{" "}
                      {tl("tools")}
                    </p>
                    {lock.package_path ? (
                      <p className="mt-2 truncate font-mono text-[10px] text-[var(--text-quaternary)]">
                        {lock.package_path}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => rollbackPackage(lock.package_id)}
                      disabled={!lock.rollback_ref || packageBusy !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-tertiary)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RotateCcw size={13} />
                      {tl("Rollback")}
                    </button>
                    <button
                      type="button"
                      onClick={() => uninstallPackage(lock.package_id)}
                      disabled={packageBusy !== null}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-[rgba(250,82,82,0.30)] px-3 py-2 text-xs text-[var(--tone-danger-text)] transition-colors hover:bg-[rgba(250,82,82,0.08)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Trash2 size={13} />
                      {tl("Uninstall")}
                    </button>
                  </div>
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
            title={tl("Advanced JSON")}
          >
            <div className="flex flex-col gap-6 pt-3">
              <JsonEditorField
                label={tl("Skill Policy")}
                description={tl(
                  "Complete skill policy schema.",
                )}
                value={state.skillPolicyJson}
                onChange={(value) =>
                  updateAgentSpecField("skillPolicyJson", value)
                }
              />
              <JsonEditorField
                label={tl("Custom Skills")}
                description={tl(
                  "Custom skills array in JSON format.",
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
        title={tl("Remove skill")}
        message={
          skillToDelete
            ? tl(
                'Are you sure you want to remove "{{name}}"? This action cannot be undone.',
                { name: skillToDelete.name || tl("Unnamed skill") },
              )
            : ""
        }
        confirmLabel={tl("Remove")}
        onConfirm={() => confirmDelete && deleteSkill(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
