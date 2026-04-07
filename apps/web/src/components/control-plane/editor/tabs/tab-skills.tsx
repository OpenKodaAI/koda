"use client";

import { useMemo, useState, useCallback } from "react";
import {
  ChevronRight,
  Plus,
  Trash2,
  Wand2,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useBotEditor } from "@/hooks/use-bot-editor";
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

/* -------------------------------------------------------------------------- */
/*  Constants                                                                  */
/* -------------------------------------------------------------------------- */

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

/* -------------------------------------------------------------------------- */
/*  CategoryBadge                                                              */
/* -------------------------------------------------------------------------- */

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

/* -------------------------------------------------------------------------- */
/*  TabSkills                                                                  */
/* -------------------------------------------------------------------------- */

export function TabSkills() {
  const { state, developerMode, updateAgentSpecField } = useBotEditor();
  const { tl } = useAppI18n();

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
            <h3 className="eyebrow">{tl("Agent skills")}</h3>
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
                            placeholder="e.g. deploy-review, sales-playbook"
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
                            placeholder="Diretiva imperativa descrevendo QUANDO e COMO o agente deve usar esta skill"
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
                            placeholder="Metodologia completa em Markdown. Inclua ## Abordagem, ## Formato de Saida, ## Principios Chave"
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
                                  placeholder="e.g. dr, deploy"
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
                                  placeholder="e.g. security, devops"
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
                                placeholder="e.g. **Risks** as [Severity] description → mitigation. **Summary** with 3 action items."
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
