"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/header";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";
import { parseHealthPort, prettyJson } from "@/lib/control-plane-editor";
import type { ControlPlaneAgentSummary } from "@/lib/control-plane";

function slug(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function formatAgentCatalogCount(
  tl: (value: string, options?: Record<string, unknown>) => string,
  count: number,
) {
  return tl(
    count === 1 ? "{{count}} agent no catálogo" : "{{count}} agents no catálogo",
    { count },
  );
}

export function ControlPlaneHome({
  agents,
  globalDefaults,
  coreTools,
  coreProviders,
  corePolicies,
  coreCapabilities,
}: {
  agents: ControlPlaneAgentSummary[];
  globalDefaults: {
    sections: Record<string, Record<string, unknown>>;
    version: number;
  };
  coreTools: {
    items: Array<Record<string, unknown>>;
    governance: Record<string, unknown>;
  };
  coreProviders: Record<string, unknown>;
  corePolicies: Record<string, unknown>;
  coreCapabilities: Record<string, unknown>;
}) {
  const router = useRouter();
  const { tl } = useAppI18n();
  const [agentId, setBotId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [color, setColor] = useState("#6E97D9");
  const [colorRgb, setColorRgb] = useState("110, 151, 217");
  const [healthPort, setHealthPort] = useState("8080");
  const [defaultsJson, setDefaultsJson] = useState(prettyJson(globalDefaults.sections));
  const [message, setMessage] = useState<string | null>(null);
  const { runAction, isPending, getStatus } = useAsyncAction();

  const nextStorageNamespace = useMemo(() => slug(agentId), [agentId]);

  async function handleCreateAgent() {
    const normalizedId = agentId.trim().toUpperCase();
    if (!normalizedId) return;

    setMessage(null);
    await runAction("create", async () => {
      const normalizedHealthPort = parseHealthPort(healthPort);
      const payload = await requestJson<{ id: string }>("/api/control-plane/agents", {
        method: "POST",
        body: JSON.stringify({
          id: normalizedId,
          display_name: displayName.trim() || normalizedId.replace(/_/g, " "),
          status: "paused",
          storage_namespace: nextStorageNamespace || slug(normalizedId),
          appearance: {
            label: displayName.trim() || normalizedId.replace(/_/g, " "),
            color,
            color_rgb: colorRgb,
          },
          runtime_endpoint: {
            health_port: normalizedHealthPort,
            health_url: `http://127.0.0.1:${normalizedHealthPort}/health`,
            runtime_base_url: `http://127.0.0.1:${normalizedHealthPort}`,
          },
        }),
      });
      setMessage(tl("Agent {{id}} criado com sucesso.", { id: payload.id }));
      router.push(`/control-plane/agents/${payload.id}`);
      router.refresh();
    }, {
      successMessage: tl("Bot criado com sucesso."),
      errorMessage: tl("Falha ao criar bot."),
      onError: async (error) => setMessage(error.message),
    });
  }

  async function handleSaveGlobalDefaults() {
    setMessage(null);
    await runAction("defaults", async () => {
      const parsed = JSON.parse(defaultsJson) as Record<string, Record<string, unknown>>;
      await requestJson("/api/control-plane/global-defaults", {
        method: "PATCH",
        body: JSON.stringify({ sections: parsed }),
      });
      setMessage(tl("Defaults globais atualizados."));
      router.refresh();
    }, {
      successMessage: tl("Defaults globais atualizados."),
      errorMessage: tl("Falha ao salvar defaults globais."),
      onError: async (error) => setMessage(error.message),
    });
  }

  async function handleAgentAction(agentIdValue: string, action: "publish" | "activate" | "pause") {
    setMessage(null);
    await runAction(`${action}:${agentIdValue}`, async () => {
      await requestJson(`/api/control-plane/agents/${agentIdValue}/${action}`, {
        method: "POST",
      });
      setMessage(tl("Ação {{action}} aplicada em {{agentId}}.", { action, agentId: agentIdValue }));
      router.refresh();
    }, {
      successMessage: tl("Ação {{action}} aplicada em {{agentId}}.", { action, agentId: agentIdValue }),
      errorMessage: tl("Falha ao executar {{action}}.", { action }),
      onError: async (error) => setMessage(error.message),
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={tl("Control Plane")}
        description={tl("Catálogo dinâmico dos bots, defaults globais e atalhos de publicação.")}
        meta={
          <div className="flex flex-wrap gap-2">
            <span className="chip">{tl("Global defaults")} v{globalDefaults.version}</span>
            <span className="chip">{tl("{{count}} core tools", { count: coreTools.items.length })}</span>
          </div>
        }
      />

      {message ? (
        <section className="glass-card px-5 py-4 text-sm text-[var(--text-secondary)]">
          {message}
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <div className="glass-card p-5 sm:p-6">
          <div className="space-y-4">
            <div>
              <p className="eyebrow">{tl("Bots")}</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                {formatAgentCatalogCount(tl, agents.length)}
              </h2>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {agents.map((agent) => (
                <article
                  key={agent.id}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-2">
                      <Link
                        href={`/control-plane/agents/${agent.id}`}
                        className="inline-flex items-center gap-2 transition-opacity hover:opacity-90"
                      >
                        <span
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: agent.appearance?.color || "#7A8799" }}
                        />
                        <h3 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                          {agent.display_name}
                        </h3>
                      </Link>
                      <p className="text-xs uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                        {agent.id}
                      </p>
                    </div>
                    <span className="chip">
                      {agent.status === "active"
                        ? tl("Ativo")
                        : agent.status === "paused"
                          ? tl("Pausado")
                          : agent.status}
                    </span>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-[var(--text-secondary)]">
                    <span>{tl("Applied")} v{agent.applied_version ?? "—"}</span>
                    <span>{tl("Desired")} v{agent.desired_version ?? "—"}</span>
                    <span>{agent.storage_namespace}</span>
                    <span>{String(agent.runtime_endpoint?.health_port ?? "—")}</span>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href={`/control-plane/agents/${agent.id}`}
                      className="button-shell button-shell--primary button-shell--sm"
                    >
                      {tl("Abrir editor")}
                    </Link>
                    <AsyncActionButton
                      type="button"
                      onClick={() => void handleAgentAction(agent.id, "publish")}
                      variant="secondary"
                      size="sm"
                      loading={isPending(`publish:${agent.id}`)}
                      status={getStatus(`publish:${agent.id}`)}
                      loadingLabel={tl("Publicando")}
                    >
                      {tl("Publicar")}
                    </AsyncActionButton>
                    <AsyncActionButton
                      type="button"
                      onClick={() => void handleAgentAction(agent.id, agent.status === "active" ? "pause" : "activate")}
                      variant="secondary"
                      size="sm"
                      loading={
                        isPending(`activate:${agent.id}`) || isPending(`pause:${agent.id}`)
                      }
                      status={
                        getStatus(`activate:${agent.id}`) !== "idle"
                          ? getStatus(`activate:${agent.id}`)
                          : getStatus(`pause:${agent.id}`)
                      }
                      loadingLabel={agent.status === "active" ? tl("Pausando") : tl("Ativando")}
                    >
                      {agent.status === "active" ? tl("Pausar") : tl("Ativar")}
                    </AsyncActionButton>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>

        <div className="glass-card p-5 sm:p-6">
          <div className="space-y-4">
            <div>
              <p className="eyebrow">{tl("Criar bot")}</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                {tl("Novo bot self-hosted")}
              </h2>
            </div>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {tl("ID")}
              </span>
              <input
                value={agentId}
                onChange={(event) => setBotId(event.target.value.toUpperCase())}
                placeholder={tl("EXEMPLO_BOT")}
                className="field-shell text-[var(--text-primary)]"
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {tl("Display name")}
              </span>
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder={tl("Exemplo Bot")}
                className="field-shell text-[var(--text-primary)]"
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-3">
              <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {tl("Cor")}
              </span>
                <input
                  value={color}
                  onChange={(event) => setColor(event.target.value)}
                  className="field-shell text-[var(--text-primary)]"
                />
              </label>
              <label className="block sm:col-span-2">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                RGB
              </span>
                <input
                  value={colorRgb}
                  onChange={(event) => setColorRgb(event.target.value)}
                  className="field-shell text-[var(--text-primary)]"
                />
              </label>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                  {tl("Namespace")}
              </span>
                <input
                  value={nextStorageNamespace}
                  readOnly
                  className="field-shell text-[var(--text-secondary)]"
                />
              </label>
              <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                  {tl("Health port")}
              </span>
                <input
                  value={healthPort}
                  onChange={(event) => setHealthPort(event.target.value)}
                  className="field-shell text-[var(--text-primary)]"
                />
              </label>
            </div>

            <AsyncActionButton
              type="button"
              onClick={() => void handleCreateAgent()}
              loading={isPending("create")}
              status={getStatus("create")}
              loadingLabel={tl("Criando bot")}
              className="w-full"
            >
              {tl("Criar bot")}
            </AsyncActionButton>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <div className="glass-card p-5 sm:p-6">
          <p className="eyebrow">{tl("Core tools")}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {tl("Catálogo governado pelo sistema")}
          </h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {tl("Os bots só habilitam subsets desse catálogo.")}
          </p>
          <textarea
            readOnly
            value={prettyJson(coreTools)}
            className="field-shell mt-4 min-h-[260px] font-mono text-xs text-[var(--text-primary)]"
          />
        </div>

        <div className="glass-card p-5 sm:p-6">
          <p className="eyebrow">{tl("Providers")}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {tl("Envelope global de modelos")}
          </h2>
          <textarea
            readOnly
            value={prettyJson(coreProviders)}
            className="field-shell mt-4 min-h-[260px] font-mono text-xs text-[var(--text-primary)]"
          />
        </div>

        <div className="glass-card p-5 sm:p-6">
          <p className="eyebrow">{tl("Governança")}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {tl("Policies e capabilities")}
          </h2>
          <textarea
            readOnly
            value={prettyJson({ policies: corePolicies, capabilities: coreCapabilities })}
            className="field-shell mt-4 min-h-[260px] font-mono text-xs text-[var(--text-primary)]"
          />
        </div>
      </section>

      <section className="glass-card p-5 sm:p-6">
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="eyebrow">{tl("Defaults globais")}</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                {tl("Herança base para novos bots e overrides")}
              </h2>
            </div>
            <AsyncActionButton
              type="button"
              onClick={() => void handleSaveGlobalDefaults()}
              loading={isPending("defaults")}
              status={getStatus("defaults")}
              loadingLabel={tl("Salvando defaults")}
              size="sm"
            >
              {tl("Salvar defaults")}
            </AsyncActionButton>
          </div>

          <textarea
            value={defaultsJson}
            onChange={(event) => setDefaultsJson(event.target.value)}
            className="field-shell min-h-[420px] w-full px-4 py-4 font-mono text-xs text-[var(--text-primary)]"
            spellCheck={false}
          />
        </div>
      </section>
    </div>
  );
}
