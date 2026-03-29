"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Database, ShieldCheck, Trash2 } from "lucide-react";
import { PolicyCard } from "@/components/control-plane/shared/policy-card";
import {
  KnowledgePolicyForm,
  MemoryPolicyForm,
} from "@/components/control-plane/shared/policy-forms";
import { useBotEditor } from "@/hooks/use-bot-editor";
import { useToast } from "@/hooks/use-toast";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { JsonEditorField } from "@/components/control-plane/shared/json-editor-field";
import { MarkdownEditorField } from "@/components/control-plane/shared/markdown-editor-field";
import { SectionCollapsible } from "@/components/control-plane/shared/section-collapsible";
import { parseJsonArray } from "@/lib/control-plane-editor";
import {
  parseKnowledgePolicy,
  parseMemoryPolicy,
  serializeKnowledgePolicy,
  serializeMemoryPolicy,
} from "@/lib/policy-serializers";

/* -------------------------------------------------------------------------- */
/*  Request helpers                                                            */
/* -------------------------------------------------------------------------- */

async function requestJson(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Request failed with status ${response.status}`,
    );
  }
  return payload;
}

function collectionJsonLabel(kind: "knowledge-assets" | "templates" | "skills") {
  if (kind === "knowledge-assets") return "Editar ativos em JSON";
  if (kind === "templates") return "Editar templates em JSON";
  return "Editar skills em JSON";
}

function collectionPlaceholder(kind: "knowledge-assets" | "templates" | "skills") {
  if (kind === "knowledge-assets") {
    return `[
  {
    "name": "Runbook de incidentes",
    "content": "# Título\\n\\nConteúdo..."
  }
]`;
  }
  if (kind === "templates") {
    return `[
  {
    "name": "Resumo executivo",
    "content": "Template em Markdown..."
  }
]`;
  }
  return `[
  {
    "name": "architecture",
    "content": "Skill ou instrução reutilizável..."
  }
]`;
}

/* -------------------------------------------------------------------------- */
/*  Collection section                                                         */
/* -------------------------------------------------------------------------- */

function CollectionSection({
  title,
  kind,
  jsonValue,
  onJsonChange,
  items,
  botId,
  onRefresh,
}: {
  title: string;
  kind: "knowledge-assets" | "templates" | "skills";
  jsonValue: string;
  onJsonChange: (v: string) => void;
  items: Array<Record<string, unknown>>;
  botId: string;
  onRefresh: () => void;
}) {
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const [busyKey, setBusyKey] = useState<string | null>(null);

  async function handleUpsert() {
    setBusyKey("upsert");
    try {
      const parsed = parseJsonArray(title, jsonValue);

      await Promise.all(
        parsed.map((item: Record<string, unknown>) => {
          const id = Number(item.id || 0);
          return requestJson(
            `/api/control-plane/agents/${botId}/${kind}${id ? `/${id}` : ""}`,
            {
              method: id ? "PUT" : "POST",
              body: JSON.stringify(item),
            },
          );
        }),
      );

      const desiredIds = new Set(
        parsed
          .map((item) => Number(item.id || 0))
          .filter((id) => Number.isInteger(id) && id > 0),
      );
      const existingIds = items
        .map((item) => Number(item.id || 0))
        .filter((id) => Number.isInteger(id) && id > 0);
      const removedIds = existingIds.filter((id) => !desiredIds.has(id));
      await Promise.all(
        removedIds.map((id) =>
          requestJson(`/api/control-plane/agents/${botId}/${kind}/${id}`, {
            method: "DELETE",
          }),
        ),
      );

      showToast(tl("{{title}} salvos com sucesso.", { title }), "success");
      onRefresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao salvar {{title}}.", { title }),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function handleDelete(itemId: number) {
    setBusyKey(`delete-${itemId}`);
    try {
      await requestJson(`/api/control-plane/agents/${botId}/${kind}/${itemId}`, {
        method: "DELETE",
      });
      showToast(tl("Item {{id}} removido.", { id: itemId }), "success");
      onRefresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao remover item."),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <section className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-6 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
            {title}
          </h3>
          <p className="text-sm text-[var(--text-tertiary)]">
            {tl("Use esta coleção para publicar conhecimento reutilizável que o agente pode consultar com segurança.")}
          </p>
        </div>
        <span className="chip text-xs">
          {tl("{{count}} item(s)", { count: items.length })}
        </span>
      </div>

      {items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map((item) => {
            const id = Number(item.id || 0);
            const name = String(item.name || item.title || item.id || "—");
            return (
              <div
                key={id || name}
                className="flex items-center justify-between gap-3 rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.018)] px-3 py-2.5"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="chip text-xs">{id || tl("new")}</span>
                  <span className="text-sm text-[var(--text-primary)] truncate">
                    {name}
                  </span>
                </div>
                {id > 0 && (
                  <button
                    type="button"
                    className="shrink-0 p-1.5 text-[var(--text-quaternary)] hover:text-[var(--tone-danger-text)] transition-colors"
                    disabled={busyKey !== null}
                    onClick={() => handleDelete(id)}
                    aria-label={tl("Delete {{name}}", { name })}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[rgba(255,255,255,0.01)] px-4 py-5 text-sm text-[var(--text-tertiary)]">
          {tl("Ainda não há itens publicados nesta coleção. Se quiser, abra a edição em JSON para importar uma lista de uma vez.")}
        </div>
      ) : null}

      <SectionCollapsible title={tl(collectionJsonLabel(kind))}>
        <div className="flex flex-col gap-4 pt-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="max-w-3xl text-sm text-[var(--text-tertiary)]">
              {tl("Cole uma lista JSON e use salvar para sincronizar os itens publicados desta coleção. Esse modo é útil quando você quer importar ou atualizar vários itens de uma vez.")}
            </p>
            <button
              type="button"
              className="button-shell button-shell--primary button-shell--sm"
              disabled={busyKey !== null}
              onClick={handleUpsert}
            >
              <span>{busyKey === "upsert" ? tl("Salvando...") : tl("Salvar coleção")}</span>
            </button>
          </div>

          <textarea
            value={jsonValue}
            onChange={(e) => onJsonChange(e.target.value)}
            className="field-shell w-full resize-y px-4 py-4 font-mono text-xs text-[var(--text-primary)]"
            style={{ minHeight: "220px" }}
            spellCheck={false}
            placeholder={collectionPlaceholder(kind)}
          />
        </div>
      </SectionCollapsible>
    </section>
  );
}

function asOptions(
  catalog: Array<Record<string, unknown>>,
  fallback: Array<{ value: string; label: string }>,
) {
  if (catalog.length === 0) {
    return fallback;
  }
  return catalog.map((item) => ({
    value: String(item.id),
    label: String(item.label || item.id),
  }));
}

/* -------------------------------------------------------------------------- */
/*  Tab: Conhecimento                                                          */
/* -------------------------------------------------------------------------- */

export function TabConhecimento() {
  const {
    core,
    state,
    developerMode,
    updateField,
    updateCollectionJson,
    updateDocument,
    updateAgentSpecField,
  } = useBotEditor();
  const { showToast } = useToast();
  const { tl } = useAppI18n();
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const botId = state.bot.id;
  const memoryPolicy = useMemo(
    () => parseMemoryPolicy(state.memoryPolicyJson),
    [state.memoryPolicyJson],
  );
  const knowledgePolicy = useMemo(
    () => parseKnowledgePolicy(state.knowledgePolicyJson),
    [state.knowledgePolicyJson],
  );
  const layerOptions = useMemo(
    () =>
      asOptions([], [
        { value: "canonical_policy", label: tl("Canônico") },
        { value: "approved_runbook", label: tl("Runbooks aprovados") },
        { value: "workspace_doc", label: tl("Documentos do workspace") },
        { value: "observed_pattern", label: tl("Padrões observados") },
      ]),
    [tl],
  );
  const providerOptions = useMemo(
    () =>
      Object.entries(core.providers.providers || {})
        .filter(([, provider]) => String(provider.category || "general") === "general")
        .filter(([providerId]) =>
          Array.isArray(core.providers.enabled_providers) &&
          core.providers.enabled_providers.includes(String(providerId)),
        )
        .map(([providerId, provider]) => ({
          value: String(providerId),
          label: String(provider.title || providerId),
        })),
    [core.providers.enabled_providers, core.providers.providers],
  );
  const totalKnowledgeItems =
    state.bot.knowledge_assets.length + state.bot.templates.length + state.bot.skills.length;

  function handleRefresh() {
    router.refresh();
  }

  async function handleCandidateAction(action: "approve" | "reject") {
    const candidateId = Number(state.candidateActionId);
    if (!Number.isInteger(candidateId) || candidateId <= 0) {
      showToast(tl("Informe um candidate ID valido."), "warning");
      return;
    }

    setBusyKey(`${action}-candidate`);
    try {
      await requestJson(
        `/api/control-plane/agents/${botId}/knowledge-candidates/${candidateId}/${action}`,
        { method: "POST" },
      );
      showToast(
        action === "approve"
          ? tl("Candidate aprovado com sucesso.")
          : tl("Candidate rejeitado com sucesso."),
        "success",
      );
      updateField("candidateActionId", "");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao processar candidate."),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function handleRunbookRevalidate() {
    const runbookId = Number(state.runbookActionId);
    if (!Number.isInteger(runbookId) || runbookId <= 0) {
      showToast(tl("Informe um runbook ID valido."), "warning");
      return;
    }

    setBusyKey("revalidate-runbook");
    try {
      await requestJson(
        `/api/control-plane/agents/${botId}/runbooks/${runbookId}/revalidate`,
        { method: "POST" },
      );
      showToast(tl("Runbook revalidado com sucesso."), "success");
      updateField("runbookActionId", "");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : tl("Erro ao revalidar runbook."),
        "error",
      );
    } finally {
      setBusyKey(null);
    }
  }

  function updateMemoryPolicy(nextPolicy: ReturnType<typeof parseMemoryPolicy>) {
    updateAgentSpecField(
      "memoryPolicyJson",
      serializeMemoryPolicy(nextPolicy),
    );
  }

  function updateKnowledgePolicy(
    nextPolicy: ReturnType<typeof parseKnowledgePolicy>,
  ) {
    updateAgentSpecField(
      "knowledgePolicyJson",
      serializeKnowledgePolicy(nextPolicy),
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          {tl("Conhecimento")}
        </h2>
        <p className="text-sm text-[var(--text-tertiary)]">
          {tl("Configure o que o agente pode lembrar, em quais fontes pode se apoiar e quais conteúdos publicados ficam disponíveis para grounding.")}
        </p>
      </div>

      <section className="flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-6">
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
            {tl("Memória e grounding")}
          </h3>
          <p className="text-sm text-[var(--text-tertiary)]">
            {tl("Aqui você define a política do agente. Chunking, knowledge graph, reranking, drift-aware retrieval e manutenção do índice continuam automáticos no runtime.")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            <span className="font-medium text-[var(--text-primary)]">
              {memoryPolicy.enabled ? tl("Memória ligada") : tl("Memória desligada")}
            </span>
            {` · `}
            <span className="font-medium text-[var(--text-primary)]">
              {knowledgePolicy.enabled ? tl("Grounding ativo") : tl("Grounding desligado")}
            </span>
            {` · ${totalKnowledgeItems} ${tl("itens publicados")}`}
          </p>
        </div>

        <PolicyCard
          title={tl("Memória persistente")}
          description={tl("Defina se o agente pode aprender com o uso, quanto contexto pode trazer e quais tipos de memória merecem prioridade.")}
          icon={Database}
          dirty={state.dirty.agentSpec}
        >
          <MemoryPolicyForm
            policy={memoryPolicy}
            onChange={updateMemoryPolicy}
            providerOptions={providerOptions}
          />
        </PolicyCard>

        <PolicyCard
          title={tl("Conhecimento e grounding")}
          description={tl("Defina em quais fontes o agente pode se apoiar e o quanto ele pode puxar de contexto antes de responder.")}
          icon={ShieldCheck}
          dirty={state.dirty.agentSpec}
        >
          <KnowledgePolicyForm
            policy={knowledgePolicy}
            onChange={updateKnowledgePolicy}
            layerOptions={layerOptions}
          />
        </PolicyCard>

        {developerMode ? (
          <SectionCollapsible title={tl("Overrides avançados")}>
            <div className="flex flex-col gap-6 pt-2">
              <JsonEditorField
                label={tl("Memory Extraction Schema")}
                description={tl("Schema de extração de memória.")}
                value={state.memoryExtractionSchemaJson}
                onChange={(v) =>
                  updateAgentSpecField("memoryExtractionSchemaJson", v)
                }
              />

              <MarkdownEditorField
                label={tl("Memory Extraction Prompt")}
                description={tl("Prompt usado para extrair memória de um turno.")}
                value={state.documents["memory_extraction_prompt_md"] ?? ""}
                onChange={(v) => updateDocument("memory_extraction_prompt_md", v)}
                minHeight="180px"
              />

              <SectionCollapsible title={tl("JSON bruto das políticas")}>
                <div className="flex flex-col gap-6 pt-2">
                  <JsonEditorField
                    label={tl("Knowledge Policy JSON")}
                    description={tl("Override bruto do schema canônico completo.")}
                    value={state.knowledgePolicyJson}
                    onChange={(v) => updateAgentSpecField("knowledgePolicyJson", v)}
                  />

                  <JsonEditorField
                    label={tl("Memory Policy JSON")}
                    description={tl("Override bruto do schema canônico completo.")}
                    value={state.memoryPolicyJson}
                    onChange={(v) => updateAgentSpecField("memoryPolicyJson", v)}
                  />
                </div>
              </SectionCollapsible>
            </div>
          </SectionCollapsible>
        ) : (
          <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.018)] p-4 text-sm text-[var(--text-tertiary)]">
            {tl("O sistema cuida sozinho de chunking, knowledge graph, reranking, busca híbrida e manutenção do índice. Aqui você só define a política que o agente deve seguir.")}
          </div>
        )}
      </section>

      <CollectionSection
        title={tl("Ativos de conhecimento")}
        kind="knowledge-assets"
        jsonValue={state.knowledgeJson}
        onJsonChange={(v) => updateCollectionJson("knowledge", v)}
        items={state.bot.knowledge_assets}
        botId={botId}
        onRefresh={handleRefresh}
      />

      <CollectionSection
        title={tl("Templates")}
        kind="templates"
        jsonValue={state.templatesJson}
        onJsonChange={(v) => updateCollectionJson("templates", v)}
        items={state.bot.templates}
        botId={botId}
        onRefresh={handleRefresh}
      />

      <CollectionSection
        title={tl("Skills")}
        kind="skills"
        jsonValue={state.skillsJson}
        onJsonChange={(v) => updateCollectionJson("skills", v)}
        items={state.bot.skills}
        botId={botId}
        onRefresh={handleRefresh}
      />

      <SectionCollapsible title={tl("Governanca e aprendizado")}>
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="flex flex-col gap-2">
              <span className="eyebrow">{tl("Knowledge candidates pendentes")}</span>
              <textarea
                readOnly
                value={state.knowledgeCandidatesJson}
                className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
                style={{ minHeight: "220px" }}
                spellCheck={false}
              />
            </div>
            <div className="flex flex-col gap-2">
              <span className="eyebrow">{tl("Runbooks aprovados")}</span>
              <textarea
                readOnly
                value={state.runbooksJson}
                className="field-shell w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)] resize-y opacity-80 cursor-default"
                style={{ minHeight: "220px" }}
                spellCheck={false}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-medium text-[var(--text-quaternary)] uppercase tracking-wider">
                  {tl("Candidate ID")}
                </span>
                <input
                  type="number"
                  value={state.candidateActionId}
                  onChange={(event) =>
                    updateField("candidateActionId", event.target.value)
                  }
                  className="field-shell px-3 py-2.5 text-sm text-[var(--text-primary)] font-mono"
                  placeholder={tl("Ex: 12")}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-shell button-shell--primary button-shell--sm"
                  disabled={busyKey !== null}
                  onClick={() => void handleCandidateAction("approve")}
                >
                  <span>
                    {busyKey === "approve-candidate"
                      ? tl("Aprovando...")
                      : tl("Aprovar candidate")}
                  </span>
                </button>
                <button
                  type="button"
                  className="button-shell button-shell--secondary button-shell--sm"
                  disabled={busyKey !== null}
                  onClick={() => void handleCandidateAction("reject")}
                >
                  <span>
                    {busyKey === "reject-candidate"
                      ? tl("Rejeitando...")
                      : tl("Rejeitar candidate")}
                  </span>
                </button>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-medium text-[var(--text-quaternary)] uppercase tracking-wider">
                  {tl("Runbook ID")}
                </span>
                <input
                  type="number"
                  value={state.runbookActionId}
                  onChange={(event) =>
                    updateField("runbookActionId", event.target.value)
                  }
                  className="field-shell px-3 py-2.5 text-sm text-[var(--text-primary)] font-mono"
                  placeholder={tl("Ex: 5")}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-shell button-shell--secondary button-shell--sm"
                  disabled={busyKey !== null}
                  onClick={() => void handleRunbookRevalidate()}
                >
                  <span>
                    {busyKey === "revalidate-runbook"
                      ? tl("Revalidando...")
                      : tl("Revalidar runbook")}
                  </span>
                </button>
                <button
                  type="button"
                  className="button-shell button-shell--secondary button-shell--sm"
                  disabled={busyKey !== null}
                  onClick={handleRefresh}
                >
                  <span>{tl("Atualizar fila")}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </SectionCollapsible>
    </div>
  );
}
