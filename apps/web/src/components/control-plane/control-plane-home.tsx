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
import { translate } from "@/lib/i18n";

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
  const { t, tl } = useAppI18n();
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
      setMessage(t("generated.controlPlane.agent_id_criado_com_sucesso_1224f6b9", { id: payload.id }));
      router.push(`/control-plane/agents/${payload.id}`);
      router.refresh();
    }, {
      successMessage: t("generated.controlPlane.bot_criado_com_sucesso_fc2f3c1a"),
      errorMessage: t("generated.controlPlane.falha_ao_criar_bot_0db0f895"),
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
      setMessage(t("generated.controlPlane.defaults_globais_atualizados_1e0a0051"));
      router.refresh();
    }, {
      successMessage: t("generated.controlPlane.defaults_globais_atualizados_1e0a0051"),
      errorMessage: t("generated.controlPlane.falha_ao_salvar_defaults_globais_3dbb9a8f"),
      onError: async (error) => setMessage(error.message),
    });
  }

  async function handleAgentAction(agentIdValue: string, action: "publish" | "activate" | "pause") {
    setMessage(null);
    await runAction(`${action}:${agentIdValue}`, async () => {
      await requestJson(`/api/control-plane/agents/${agentIdValue}/${action}`, {
        method: "POST",
      });
      setMessage(t("generated.controlPlane.acao_action_aplicada_em_agentid_4d9ba5a1", { action, agentId: agentIdValue }));
      router.refresh();
    }, {
      successMessage: t("generated.controlPlane.acao_action_aplicada_em_agentid_4d9ba5a1", { action, agentId: agentIdValue }),
      errorMessage: t("generated.controlPlane.falha_ao_executar_action_cdf27ea6", { action }),
      onError: async (error) => setMessage(error.message),
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("generated.controlPlane.control_plane_744d4a20")}
        description={t("generated.controlPlane.catalogo_dinamico_dos_bots_defaults_globais__63de7fb4")}
        meta={
          <div className="flex flex-wrap gap-2">
            <span className="chip">{t("generated.controlPlane.global_defaults_e66067d9")} {translate("generated.controlPlane.v_76abe6e8")}{globalDefaults.version}</span>
            <span className="chip">{t("generated.controlPlane.count_core_tools_3b1fc27e", { count: coreTools.items.length })}</span>
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
              <p className="eyebrow">{t("generated.controlPlane.bots_b2016c98")}</p>
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
                        ? t("generated.controlPlane.ativo_70b78dfa")
                        : agent.status === "paused"
                          ? t("generated.controlPlane.pausado_687e9e74")
                          : agent.status}
                    </span>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-[var(--text-secondary)]">
                    <span>{t("generated.controlPlane.applied_ca8a9229")} {translate("generated.controlPlane.v_76abe6e8")}{agent.applied_version ?? "—"}</span>
                    <span>{t("generated.controlPlane.desired_918bbbc1")} {translate("generated.controlPlane.v_76abe6e8")}{agent.desired_version ?? "—"}</span>
                    <span>{agent.storage_namespace}</span>
                    <span>{String(agent.runtime_endpoint?.health_port ?? "—")}</span>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href={`/control-plane/agents/${agent.id}`}
                      className="button-shell button-shell--primary button-shell--sm"
                    >
                      {t("generated.controlPlane.abrir_editor_2bc7a60a")}
                    </Link>
                    <AsyncActionButton
                      type="button"
                      onClick={() => void handleAgentAction(agent.id, "publish")}
                      variant="secondary"
                      size="sm"
                      loading={isPending(`publish:${agent.id}`)}
                      status={getStatus(`publish:${agent.id}`)}
                      loadingLabel={t("generated.controlPlane.publicando_101b5815")}
                    >
                      {t("generated.controlPlane.publicar_eaf58f05")}
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
                      loadingLabel={agent.status === "active" ? t("generated.controlPlane.pausando_eef1e878") : t("generated.controlPlane.ativando_d8dad0b2")}
                    >
                      {agent.status === "active" ? t("generated.controlPlane.pausar_85f3ee9b") : t("generated.controlPlane.ativar_db54d834")}
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
              <p className="eyebrow">{t("generated.controlPlane.criar_bot_3f7c6aa1")}</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                {t("generated.controlPlane.novo_bot_self_hosted_401d4835")}
              </h2>
            </div>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("generated.controlPlane.id_eb64177a")}
              </span>
              <input
                value={agentId}
                onChange={(event) => setBotId(event.target.value.toUpperCase())}
                placeholder={t("generated.controlPlane.exemplo_bot_bc80ea67")}
                className="field-shell text-[var(--text-primary)]"
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("generated.controlPlane.display_name_13949286")}
              </span>
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder={t("generated.controlPlane.exemplo_bot_52a4140b")}
                className="field-shell text-[var(--text-primary)]"
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-3">
              <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("generated.controlPlane.cor_a63c4fed")}
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
                  {t("generated.controlPlane.namespace_4a91cf30")}
              </span>
                <input
                  value={nextStorageNamespace}
                  readOnly
                  className="field-shell text-[var(--text-secondary)]"
                />
              </label>
              <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                  {t("generated.controlPlane.health_port_75cfd237")}
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
              loadingLabel={t("generated.controlPlane.criando_bot_a401c37b")}
              className="w-full"
            >
              {t("generated.controlPlane.criar_bot_3f7c6aa1")}
            </AsyncActionButton>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <div className="glass-card p-5 sm:p-6">
          <p className="eyebrow">{t("generated.controlPlane.core_tools_b3b00936")}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {t("generated.controlPlane.catalogo_governado_pelo_sistema_05415f6e")}
          </h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {t("generated.controlPlane.os_bots_so_habilitam_subsets_desse_catalogo_bde5583d")}
          </p>
          <textarea
            readOnly
            value={prettyJson(coreTools)}
            className="field-shell mt-4 min-h-[260px] font-mono text-xs text-[var(--text-primary)]"
          />
        </div>

        <div className="glass-card p-5 sm:p-6">
          <p className="eyebrow">{t("generated.controlPlane.providers_371bc91d")}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {t("generated.controlPlane.envelope_global_de_modelos_1c5b926e")}
          </h2>
          <textarea
            readOnly
            value={prettyJson(coreProviders)}
            className="field-shell mt-4 min-h-[260px] font-mono text-xs text-[var(--text-primary)]"
          />
        </div>

        <div className="glass-card p-5 sm:p-6">
          <p className="eyebrow">{t("generated.controlPlane.governanca_d4101c68")}</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {t("generated.controlPlane.policies_e_capabilities_94621b02")}
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
              <p className="eyebrow">{t("generated.controlPlane.defaults_globais_cdeeccf3")}</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                {t("generated.controlPlane.heranca_base_para_novos_bots_e_overrides_1ee3212f")}
              </h2>
            </div>
            <AsyncActionButton
              type="button"
              onClick={() => void handleSaveGlobalDefaults()}
              loading={isPending("defaults")}
              status={getStatus("defaults")}
              loadingLabel={t("generated.controlPlane.salvando_defaults_e450f89f")}
              size="sm"
            >
              {t("generated.controlPlane.salvar_defaults_8eecb9b1")}
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
