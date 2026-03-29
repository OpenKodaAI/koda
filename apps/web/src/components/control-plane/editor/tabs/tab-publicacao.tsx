"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  XCircle,
  AlertTriangle,
  Copy,
  Trash2,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useToast } from "@/hooks/use-toast";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import { FormInput } from "@/components/control-plane/shared/form-field";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { AsyncActionButton, InlineSpinner } from "@/components/ui/async-feedback";
import { prettyJson } from "@/lib/control-plane-editor";
import { requestJson, requestJsonAllowError } from "@/lib/http-client";
import type { ControlPlanePromptPreview, ControlPlanePromptBudget } from "@/lib/control-plane";
import { formatDateTime } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/*  Publishing helpers                                                         */
/* -------------------------------------------------------------------------- */

function PublishingFact({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5 border-l border-[var(--border-subtle)] pl-3">
      <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
        {label}
      </span>
      <span className="text-sm font-medium text-[var(--text-primary)]">{value}</span>
      {detail ? (
        <span className="text-xs leading-relaxed text-[var(--text-tertiary)]">{detail}</span>
      ) : null}
    </div>
  );
}

function PublicationBadge({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  const toneClass =
    tone === "success"
      ? "border-[var(--tone-success-border)] bg-[rgba(77,137,100,0.08)] text-[var(--tone-success-text)]"
      : tone === "warning"
        ? "border-[var(--tone-warning-border)] bg-[rgba(184,137,56,0.08)] text-[var(--tone-warning-text)]"
        : tone === "danger"
          ? "border-[var(--tone-danger-border)] bg-[rgba(180,90,105,0.08)] text-[var(--tone-danger-text)]"
          : tone === "info"
            ? "border-[var(--tone-info-border)] bg-[rgba(76,127,209,0.08)] text-[var(--tone-info-text)]"
            : "border-[var(--border-subtle)] bg-[rgba(255,255,255,0.03)] text-[var(--text-secondary)]";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-[0.12em] uppercase ${toneClass}`}
    >
      {label}
    </span>
  );
}

function PipelineStep({
  index,
  label,
  description,
  status,
  busy,
  disabled,
  onClick,
}: {
  index: number;
  label: string;
  description: string;
  status: "idle" | "success" | "error" | "busy";
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const toneClass =
    status === "success"
      ? "border-[var(--tone-success-border)] bg-[rgba(77,137,100,0.05)]"
      : status === "error"
        ? "border-[var(--tone-danger-border)] bg-[rgba(180,90,105,0.05)]"
        : "border-[var(--border-subtle)] bg-transparent";

  return (
    <button
      type="button"
      className={`flex min-h-[74px] items-center gap-3 rounded-2xl border px-4 py-3 text-left shadow-none transition-colors ${toneClass}`}
      style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer" }}
      disabled={disabled || busy}
      onClick={onClick}
    >
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-tint)] text-[11px] font-medium text-[var(--text-secondary)]">
        {index}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-[var(--text-primary)]">{label}</div>
        <div className="mt-0.5 text-xs leading-relaxed text-[var(--text-tertiary)]">{description}</div>
      </div>
      <div className="shrink-0">
        {status === "success" ? (
          <PublicationBadge label="ok" tone="success" />
        ) : status === "error" ? (
          <PublicationBadge label="erro" tone="danger" />
        ) : busy ? (
          <InlineSpinner className="h-4 w-4" />
        ) : (
          <PublicationBadge label="pendente" tone="neutral" />
        )}
      </div>
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Tab: Publicacao                                                            */
/* -------------------------------------------------------------------------- */

export function TabPublicacao() {
  const {
    state,
    updateField,
    setCompiledPrompt,
    setValidationJson,
    refreshCompiledPrompt,
    persistDraft,
  } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const { runAction, isPending } = useAsyncAction();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<{
    validate: "idle" | "success" | "error";
    checks: "idle" | "success" | "error";
    publish: "idle" | "success" | "error";
  }>({ validate: "idle", checks: "idle", publish: "idle" });

  const botId = state.bot.id;

  /* ---------------------------------------------------------------------- */
  /*  Pipeline actions                                                       */
  /* ---------------------------------------------------------------------- */

  async function handleValidation(endpoint: "validate" | "publish-checks") {
    const key = endpoint === "validate" ? "validate" : "checks";
    await runAction(key, async () => {
      await persistDraft();
      const response = await requestJsonAllowError(
        `/api/control-plane/agents/${botId}/${endpoint}`,
        { method: "POST" },
      );
      setValidationJson(prettyJson(response.data || {}));
      try {
        await refreshCompiledPrompt();
      } catch {
        if (
          response.data &&
          typeof response.data === "object" &&
          "compiled_prompt" in response.data
        ) {
          setCompiledPrompt(String(response.data.compiled_prompt || ""));
        }
      }
      if (!response.ok) {
        setPipelineStatus((s) => ({ ...s, [key]: "error" }));
        throw new Error(response.error || tl("Falha ao executar {{endpoint}}.", { endpoint }));
      }
      setPipelineStatus((s) => ({ ...s, [key]: "success" }));
      return response;
    }, {
      successMessage:
        endpoint === "validate"
          ? tl("Validacao concluida.")
          : tl("Verificacoes de publicacao ok."),
      errorMessage: tl("Erro ao executar {{endpoint}}.", { endpoint }),
      onError: async () => {
        setPipelineStatus((s) => ({ ...s, [key]: "error" }));
      },
    });
  }

  async function handlePublish() {
    await runAction("publish", async () => {
      await persistDraft();
      await requestJson(`/api/control-plane/agents/${botId}/publish`, {
        method: "POST",
      });
      setPipelineStatus((s) => ({ ...s, publish: "success" }));
      router.refresh();
    }, {
      successMessage: tl("Bot publicado com sucesso."),
      errorMessage: tl("Erro ao publicar."),
      onError: async () => {
        setPipelineStatus((s) => ({ ...s, publish: "error" }));
      },
    });
  }

  /* ---------------------------------------------------------------------- */
  /*  Clone                                                                  */
  /* ---------------------------------------------------------------------- */

  async function handleClone() {
    if (!state.cloneId.trim()) {
      showToast(tl("ID do clone e obrigatorio."), "warning");
      return;
    }
    await runAction("clone", async () => {
      await requestJson(`/api/control-plane/agents/${botId}/clone`, {
        method: "POST",
        body: JSON.stringify({
          id: state.cloneId.trim(),
          display_name:
            state.cloneDisplayName.trim() || state.cloneId.trim(),
        }),
      });
      router.push(`/control-plane/bots/${state.cloneId.trim()}`);
    }, {
      successMessage: tl("Bot clonado com sucesso."),
      errorMessage: tl("Erro ao clonar."),
    });
  }

  /* ---------------------------------------------------------------------- */
  /*  Delete                                                                 */
  /* ---------------------------------------------------------------------- */

  async function handleDelete() {
    setShowDeleteDialog(false);
    await runAction("delete", async () => {
      await requestJson(`/api/control-plane/agents/${botId}`, {
        method: "DELETE",
      });
      router.push("/control-plane");
    }, {
      successMessage: tl("Bot removido."),
      errorMessage: tl("Erro ao remover bot."),
    });
  }

  /* ---------------------------------------------------------------------- */
  /*  Validation output parsing                                              */
  /* ---------------------------------------------------------------------- */

  let validationPayload: Record<string, unknown> = {};
  let validationErrors: string[] = [];
  let validationWarnings: string[] = [];
  let providerErrors: string[] = [];
  let provenanceWarnings: string[] = [];
  let resourceWarnings: string[] = [];
  let resourceErrors: string[] = [];
  let sectionsPresent: string[] = [];
  let documentSources: Record<string, Record<string, unknown>> = {};
  let documentLengths: Record<string, number> = {};
  let toolPolicySummary: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(state.validationJson || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      validationPayload = parsed as Record<string, unknown>;
    }
    if (Array.isArray(validationPayload.errors)) {
      validationErrors = validationPayload.errors.map(String);
    }
    if (Array.isArray(validationPayload.warnings)) {
      validationWarnings = validationPayload.warnings.map(String);
    }
    if (Array.isArray(validationPayload.provider_errors)) {
      providerErrors = validationPayload.provider_errors.map(String);
    }
    if (Array.isArray(validationPayload.provenance_warnings)) {
      provenanceWarnings = validationPayload.provenance_warnings.map(String);
    }
    if (Array.isArray(validationPayload.resource_warnings)) {
      resourceWarnings = validationPayload.resource_warnings.map(String);
    }
    if (Array.isArray(validationPayload.resource_errors)) {
      resourceErrors = validationPayload.resource_errors.map(String);
    }
    if (Array.isArray(validationPayload.sections_present)) {
      sectionsPresent = validationPayload.sections_present.map(String);
    }
    if (
      validationPayload.document_sources &&
      typeof validationPayload.document_sources === "object" &&
      !Array.isArray(validationPayload.document_sources)
    ) {
      documentSources = validationPayload.document_sources as Record<
        string,
        Record<string, unknown>
      >;
    }
    if (
      validationPayload.document_lengths &&
      typeof validationPayload.document_lengths === "object" &&
      !Array.isArray(validationPayload.document_lengths)
    ) {
      documentLengths = Object.fromEntries(
        Object.entries(validationPayload.document_lengths as Record<string, unknown>).map(
          ([key, value]) => [key, Number(value || 0)],
        ),
      );
    }
    if (
      validationPayload.tool_policy_summary &&
      typeof validationPayload.tool_policy_summary === "object" &&
      !Array.isArray(validationPayload.tool_policy_summary)
    ) {
      toolPolicySummary = validationPayload.tool_policy_summary as Record<
        string,
        unknown
      >;
    }
    if (providerErrors.length > 0) {
      validationErrors = validationErrors.filter(
        (message) => !providerErrors.includes(message),
      );
    }
  } catch {
    /* ignore */
  }

  const compiledPromptPayload = state.compiledPromptPayload;
  const runtimePromptPreview =
    (compiledPromptPayload?.runtime_prompt_preview ??
      compiledPromptPayload?.prompt_preview ??
      (validationPayload.runtime_prompt_preview as ControlPlanePromptPreview | undefined) ??
      (validationPayload.prompt_preview as ControlPlanePromptPreview | undefined)) ||
    null;
  const botContractPromptPreview =
    compiledPromptPayload?.bot_contract_prompt_preview ??
    (validationPayload.bot_contract_prompt_preview as ControlPlanePromptPreview | undefined) ??
    null;
  const runtimeBudget =
    (runtimePromptPreview?.budget as ControlPlanePromptBudget | undefined) || null;
  const runtimeSegmentOrder =
    runtimePromptPreview?.final_segment_order ??
    runtimePromptPreview?.segment_order ??
    [];
  const runtimeBudgetOverflow = Number(runtimeBudget?.overflow_tokens || 0);
  const runtimeWithinBudget =
    typeof runtimeBudget?.within_budget === "boolean"
      ? runtimeBudget.within_budget
      : true;
  const mergedDocumentLengths =
    compiledPromptPayload?.document_lengths && Object.keys(compiledPromptPayload.document_lengths).length > 0
      ? compiledPromptPayload.document_lengths
      : documentLengths;
  const extraWarnings = [...provenanceWarnings, ...resourceWarnings];
  const extraErrors = [...providerErrors, ...resourceErrors];

  const versions = state.bot.versions ?? [];
  const normalizedVersions = [...versions]
    .map((raw, index) => {
      const versionValue = Number(raw.version ?? raw.id ?? versions.length - index);
      const version = Number.isFinite(versionValue) && versionValue > 0 ? versionValue : versions.length - index + 1;
      const status = String(raw.status ?? "unknown");
      const timestamp = raw.created_at
        ? String(raw.created_at)
        : raw.published_at
          ? String(raw.published_at)
          : "";

      return {
        raw,
        version,
        status,
        timestamp,
        dateLabel: timestamp ? formatDateTime(timestamp) : tl("Sem data"),
      };
    })
    .sort((left, right) => {
      if (right.version !== left.version) return right.version - left.version;
      return String(right.timestamp).localeCompare(String(left.timestamp));
    });
  const latestVersion = normalizedVersions[0]?.version ?? null;
  const appliedVersion = state.bot.applied_version ?? null;
  const desiredVersion = state.bot.desired_version ?? latestVersion;
  const nextPublicationVersion = Math.max(appliedVersion ?? 0, desiredVersion ?? 0, latestVersion ?? 0) + 1;
  const hasPendingRollout =
    typeof appliedVersion === "number" &&
    typeof desiredVersion === "number" &&
    desiredVersion > appliedVersion;
  const publicationReadiness =
    validationErrors.length > 0
      ? tl("Existem bloqueios para publicar")
      : hasPendingRollout
        ? tl("Versão nova publicada, aguardando aplicação no runtime")
      : validationWarnings.length > 0
        ? tl("Pode publicar, mas vale revisar avisos")
        : pipelineStatus.validate === "success" || pipelineStatus.checks === "success"
          ? tl("Pronto para publicar")
          : tl("Ainda não revisado");
  const releaseTone =
    validationErrors.length > 0
      ? "danger"
      : hasPendingRollout
        ? "info"
        : validationWarnings.length > 0
          ? "warning"
          : desiredVersion
            ? "success"
            : "neutral";
  const sampledVersions = normalizedVersions.slice(0, 3);

  /* ---------------------------------------------------------------------- */
  /*  Render                                                                 */
  /* ---------------------------------------------------------------------- */

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-6">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.015)] px-5 py-5">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex min-w-0 flex-col gap-2">
                <span className="eyebrow">{tl("Resumo final")}</span>
                <div className="text-base font-semibold text-[var(--text-primary)]">
                  {publicationReadiness}
                </div>
                <div className="text-sm leading-relaxed text-[var(--text-tertiary)]">
                  {tl("Revise a versão que está em runtime, a versão já publicada e o que acontecerá se você publicar novamente.")}
                </div>
              </div>
              <PublicationBadge
                label={
                  validationErrors.length > 0
                    ? tl("bloqueado")
                    : hasPendingRollout
                      ? tl("aguardando runtime")
                      : validationWarnings.length > 0
                        ? tl("com avisos")
                        : desiredVersion
                          ? tl("estável")
                          : tl("sem publicação")
                }
                tone={releaseTone}
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <PublishingFact
                label={tl("Versão em runtime")}
                value={appliedVersion ? `v${appliedVersion}` : tl("Ainda não aplicada")}
                detail={tl("O que está realmente ativo agora")}
              />
              <PublishingFact
                label={tl("Versão publicada")}
                value={desiredVersion ? `v${desiredVersion}` : tl("Nenhuma ainda")}
                detail={tl("A última publicação registrada")}
              />
              <PublishingFact
                label={tl("Próxima publicação")}
                value={`v${nextPublicationVersion}`}
                detail={tl("Número esperado se você publicar novamente")}
              />
              <PublishingFact
                label={tl("Prompt final")}
                value={state.compiledPrompt ? tl("Pronto para revisar") : tl("Gere ao validar")}
                detail={tl("Use o prompt compilado como conferência final")}
              />
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border-subtle)] pt-4">
              <PublicationBadge
                label={tl(`${validationErrors.length} erro(s)`)}
                tone={validationErrors.length > 0 ? "danger" : "neutral"}
              />
              <PublicationBadge
                label={tl(`${validationWarnings.length} aviso(s)`)}
                tone={validationWarnings.length > 0 ? "warning" : "neutral"}
              />
              <PublicationBadge
                label={
                  state.compiledPrompt
                    ? tl("prompt disponível")
                    : tl("prompt pendente")
                }
                tone={state.compiledPrompt ? "info" : "neutral"}
              />
            </div>

            {sampledVersions.length > 0 ? (
              <div className="flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-4">
                <span className="eyebrow">{tl("Amostra de versões")}</span>
                <div className="flex flex-wrap gap-2">
                  {sampledVersions.map((item) => (
                    <div
                      key={`sample-${item.version}`}
                      className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.02)] px-3 py-1.5 text-xs text-[var(--text-secondary)]"
                    >
                      <span className="font-mono text-[var(--text-primary)]">v{item.version}</span>
                      <span>{item.status === "published" ? tl("Publicado") : item.status}</span>
                      <span className="text-[var(--text-quaternary)]">{item.dateLabel}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div className="text-base font-semibold text-[var(--text-primary)]">
            {tl("Publicação")}
          </div>
          <div className="text-sm text-[var(--text-tertiary)]">
            {tl("Siga a ordem recomendada para validar, revisar e transformar esta configuração na próxima versão oficial do agente.")}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <PipelineStep
            index={1}
            label={tl("Validar")}
            description={tl("Confere campos essenciais, prompt compilado e consistência geral do agente.")}
            status={isPending("validate") ? "busy" : pipelineStatus.validate}
            busy={isPending("validate")}
            disabled={isPending() && !isPending("validate")}
            onClick={() => void handleValidation("validate")}
          />
          <PipelineStep
            index={2}
            label={tl("Verificar")}
            description={tl("Roda checagens finais de publicação, compatibilidade e origem das camadas.")}
            status={isPending("checks") ? "busy" : pipelineStatus.checks}
            busy={isPending("checks")}
            disabled={isPending() && !isPending("checks")}
            onClick={() => void handleValidation("publish-checks")}
          />
          <PipelineStep
            index={3}
            label={tl("Publicar")}
            description={tl("Cria a próxima versão oficial e a deixa pronta para aplicação no runtime.")}
            status={isPending("publish") ? "busy" : pipelineStatus.publish}
            busy={isPending("publish")}
            disabled={isPending() && !isPending("publish")}
            onClick={handlePublish}
          />
        </div>

        {(validationErrors.length > 0 || validationWarnings.length > 0) && (
          <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.015)] px-4 py-4">
            <div className="text-base font-semibold text-[var(--text-primary)]">
              {tl("O que revisar antes de publicar")}
            </div>
            <AnimatePresence>
              {validationErrors.map((err, i) => (
                <motion.div
                  key={`err-${i}`}
                  role="alert"
                  className="flex items-start gap-2 px-4 py-3 rounded border"
                  style={{
                    borderColor: "var(--tone-danger-border)",
                    backgroundColor: "rgba(180, 90, 105, 0.06)",
                  }}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <XCircle
                    size={16}
                    className="text-[var(--tone-danger-dot)] shrink-0 mt-0.5"
                  />
                  <span className="text-sm text-[var(--tone-danger-text)]">
                    {err}
                  </span>
                </motion.div>
              ))}
              {validationWarnings.map((warn, i) => (
                <motion.div
                  key={`warn-${i}`}
                  className="flex items-start gap-2 px-4 py-3 rounded border"
                  style={{
                    borderColor: "var(--tone-warning-border)",
                    backgroundColor: "rgba(184, 137, 56, 0.06)",
                  }}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <AlertTriangle
                    size={16}
                    className="text-[var(--tone-warning-dot)] shrink-0 mt-0.5"
                  />
                  <span className="text-sm text-[var(--tone-warning-text)]">
                    {warn}
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}

        {(extraErrors.length > 0 ||
          extraWarnings.length > 0 ||
          sectionsPresent.length > 0 ||
          Object.keys(toolPolicySummary).length > 0 ||
          Object.keys(documentSources).length > 0 ||
          Object.keys(mergedDocumentLengths).length > 0 ||
          runtimePromptPreview) && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {(extraErrors.length > 0 || extraWarnings.length > 0) && (
              <SectionCollapsible title={tl("Diagnosticos de publicacao")}>
                <div className="flex flex-col gap-3 pt-2">
                  {extraErrors.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <span className="eyebrow">{tl("Bloqueios operacionais")}</span>
                      {extraErrors.map((message, index) => (
                        <div
                          key={`provider-${index}`}
                          className="flex items-start gap-2 px-4 py-3 rounded border"
                          style={{
                            borderColor: "var(--tone-danger-border)",
                            backgroundColor: "rgba(180, 90, 105, 0.06)",
                          }}
                        >
                          <XCircle
                            size={16}
                            className="text-[var(--tone-danger-dot)] shrink-0 mt-0.5"
                          />
                          <span className="text-sm text-[var(--tone-danger-text)]">
                            {message}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  {extraWarnings.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <span className="eyebrow">{tl("Avisos operacionais")}</span>
                      {extraWarnings.map((message, index) => (
                        <div
                          key={`provenance-${index}`}
                          className="flex items-start gap-2 px-4 py-3 rounded border"
                          style={{
                            borderColor: "var(--tone-warning-border)",
                            backgroundColor: "rgba(184, 137, 56, 0.06)",
                          }}
                        >
                          <AlertTriangle
                            size={16}
                            className="text-[var(--tone-warning-dot)] shrink-0 mt-0.5"
                          />
                          <span className="text-sm text-[var(--tone-warning-text)]">
                            {message}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </SectionCollapsible>
            )}

            {(sectionsPresent.length > 0 ||
              Object.keys(toolPolicySummary).length > 0 ||
              runtimePromptPreview) && (
              <SectionCollapsible title={tl("Spec efetivo")}>
                <div className="flex flex-col gap-4 pt-2">
                  {sectionsPresent.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <span className="eyebrow">{tl("Camadas ativas")}</span>
                      <div className="flex flex-wrap gap-2">
                        {sectionsPresent.map((section) => (
                          <span key={section} className="chip text-xs">
                            {section}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {Object.keys(toolPolicySummary).length > 0 && (
                    <div className="flex flex-col gap-2">
                      <span className="eyebrow">{tl("Subset de tools resolvido")}</span>
                      <textarea
                        readOnly
                        value={prettyJson(toolPolicySummary)}
                        className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
                        style={{ minHeight: "180px" }}
                        spellCheck={false}
                      />
                    </div>
                  )}
                  {runtimePromptPreview && (
                    <div className="flex flex-col gap-3">
                      <span className="eyebrow">{tl("Prompt efetivo modelado")}</span>
                      <div className="flex flex-wrap gap-2">
                        <PublicationBadge
                          label={
                            runtimeWithinBudget
                              ? tl("budget ok")
                              : tl(`overflow ${runtimeBudgetOverflow}`)
                          }
                          tone={runtimeWithinBudget ? "success" : "danger"}
                        />
                        {runtimePromptPreview.preview_scope ? (
                          <PublicationBadge
                            label={String(runtimePromptPreview.preview_scope)}
                            tone="info"
                          />
                        ) : null}
                        {runtimePromptPreview.provider ? (
                          <PublicationBadge
                            label={`${runtimePromptPreview.provider}:${runtimePromptPreview.model || ""}`}
                            tone="neutral"
                          />
                        ) : null}
                      </div>
                      {runtimeSegmentOrder.length > 0 ? (
                        <div className="flex flex-col gap-2">
                          <span className="text-xs text-[var(--text-tertiary)]">
                            {tl("Ordem final dos segmentos no runtime")}
                          </span>
                          <div className="flex flex-wrap gap-2">
                            {runtimeSegmentOrder.map((segmentId) => (
                              <span key={segmentId} className="chip text-xs">
                                {segmentId}
                              </span>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      <textarea
                        readOnly
                        value={prettyJson(runtimePromptPreview)}
                        className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
                        style={{ minHeight: "220px" }}
                        spellCheck={false}
                      />
                    </div>
                  )}
                </div>
              </SectionCollapsible>
            )}
          </div>
        )}

        {Object.keys(documentSources).length > 0 && (
          <SectionCollapsible title={tl("Origem das camadas")}>
            <textarea
              readOnly
              value={prettyJson(documentSources)}
              className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
              style={{ minHeight: "220px" }}
              spellCheck={false}
            />
          </SectionCollapsible>
        )}

        {Object.keys(mergedDocumentLengths).length > 0 && (
          <SectionCollapsible title={tl("Tamanho das camadas")}>
            <textarea
              readOnly
              value={prettyJson(mergedDocumentLengths)}
              className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
              style={{ minHeight: "180px" }}
              spellCheck={false}
            />
          </SectionCollapsible>
        )}

        {botContractPromptPreview && (
          <SectionCollapsible title={tl("Preview do contrato local do bot")}>
            <textarea
              readOnly
              value={prettyJson(botContractPromptPreview)}
              className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
              style={{ minHeight: "220px" }}
              spellCheck={false}
            />
          </SectionCollapsible>
        )}

        {/* Compiled prompt */}
        {state.compiledPrompt && (
          <SectionCollapsible title={tl("Prompt compilado")}>
            <textarea
              value={state.compiledPrompt}
              readOnly
              className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
              style={{ minHeight: "300px" }}
              spellCheck={false}
            />
          </SectionCollapsible>
        )}
      </section>

      <section className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-6">
        <div className="flex flex-col gap-1">
          <span className="eyebrow">{tl("Histórico de publicações")}</span>
          <p className="text-sm text-[var(--text-tertiary)]">
            {tl("Veja as versões mais recentes e identifique rapidamente o que está publicado e o que já está rodando em runtime.")}
          </p>
        </div>

        {normalizedVersions.length === 0 ? (
          <p className="text-sm text-[var(--text-quaternary)]">
            {tl("Nenhuma versao disponivel.")}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {sampledVersions.map((item, index) => {
              const isLatest = index === 0;
              const isApplied = item.version === appliedVersion;
              const isDesired = item.version === desiredVersion;

              return (
                <div
                  key={String(item.version)}
                  className="flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 transition-colors"
                  style={{
                    borderColor: isApplied || isLatest
                      ? "var(--tone-info-border)"
                      : "var(--border-subtle)",
                  }}
                >
                  <span className="chip text-xs font-mono">
                    v{String(item.version)}
                  </span>
                  <span
                    className="text-sm"
                    style={{
                      color:
                        item.status === "published"
                          ? "var(--tone-success-text)"
                          : "var(--text-secondary)",
                    }}
                  >
                    {item.status === "published"
                      ? tl("Publicado")
                      : item.status === "draft"
                        ? tl("Rascunho")
                        : item.status}
                  </span>
                  {isLatest ? <span className="chip text-xs">{tl("Mais recente")}</span> : null}
                  {isDesired ? <span className="chip text-xs">{tl("Publicado atual")}</span> : null}
                  {isApplied ? <span className="chip text-xs">{tl("Em runtime")}</span> : null}
                  <span className="text-xs text-[var(--text-quaternary)] ml-auto tabular-nums">
                    {item.dateLabel}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Clone */}
      <section className="border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Clonar agente")}
          description={tl("Crie uma cópia para testar outra versão sem mexer no agente atual.")}
          icon={Copy}
        >
          <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.015)] px-4 py-3 text-sm text-[var(--text-tertiary)]">
            {tl("Dica: use a clonagem para experimentar novos modelos, tools ou políticas antes de trocar o agente principal.")}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <FormInput
              label={tl("ID do Clone")}
              description={tl("Nome técnico único do novo agente, sem repetir IDs existentes.")}
              value={state.cloneId}
              onChange={(e) => updateField("cloneId", e.target.value)}
              placeholder={tl("novo-agente-id")}
            />
            <FormInput
              label={tl("Nome do Clone")}
              description={tl("Nome amigável que aparecerá na interface.")}
              value={state.cloneDisplayName}
              onChange={(e) =>
                updateField("cloneDisplayName", e.target.value)
              }
              placeholder={tl("Copia de...")}
            />
          </div>
          <div className="flex justify-end">
            <AsyncActionButton
              type="button"
              variant="secondary"
              size="sm"
              disabled={!state.cloneId.trim()}
              loading={isPending("clone")}
              loadingLabel={tl("Clonando")}
              onClick={handleClone}
            >
              {tl("Clonar agente")}
            </AsyncActionButton>
          </div>
        </PolicyCard>
      </section>

      {/* Danger zone */}
      <section className="border-t border-[var(--border-subtle)] pt-6">
        <PolicyCard
          title={tl("Zona de perigo")}
          description={tl("Ações irreversíveis que apagam este agente permanentemente.")}
          icon={Trash2}
        >
          <div
            className="p-4 rounded border"
            style={{ borderColor: "var(--tone-danger-border)" }}
          >
            <p className="text-sm text-[var(--text-tertiary)] mb-3">
              {tl("Remover permanentemente este agente, incluindo todas as configuracoes, documentos, versoes e credenciais associadas.")}
            </p>
            <AsyncActionButton
              type="button"
              variant="danger"
              size="sm"
              style={{
                borderColor: "var(--tone-danger-border)",
                color: "var(--tone-danger-text)",
              }}
              onClick={() => setShowDeleteDialog(true)}
              loading={isPending("delete")}
              loadingLabel={tl("Removendo")}
            >
              {tl("Remover agente permanentemente")}
            </AsyncActionButton>
          </div>
        </PolicyCard>
      </section>

      {/* Delete confirmation */}
      <ConfirmationDialog
        open={showDeleteDialog}
        title={tl("Remover agente")}
        message={tl('Tem certeza que deseja remover "{{name}}"? Todas as configuracoes, documentos e versoes serao permanentemente excluidos. Esta acao nao pode ser desfeita.', {
          name: state.displayName || botId,
        })}
        confirmLabel={tl("Remover")}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteDialog(false)}
      />
    </div>
  );
}
