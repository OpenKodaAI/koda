"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import { Calendar, Code2, GitBranch, Loader2, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  useAnimatedPresence,
  useBodyScrollLock,
  useEscapeToClose,
} from "@/hooks/use-animated-presence";
import { ConnectorPicker } from "@/components/routines/connector-picker";
import {
  RecurrencePicker,
  type RecurrencePickerValue,
} from "@/components/routines/recurrence-picker";
import { TriggerTile } from "@/components/routines/trigger-tile";
import {
  cronToPreset,
  defaultRecurrenceFields,
  presetToCron,
} from "@/lib/routines/recurrence";
import type { AgentDisplay } from "@/lib/agent-constants";
import type { CronJob, ScheduleDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

type TriggerKind = "schedule" | "github_event" | "api";
type SettingsTab = "connectors" | "behavior" | "permissions";
type NotificationMode = "summary_complete" | "failures_only" | "none";
type VerificationMode = "post_write_if_any" | "task_success";

export interface RoutineFormPayload {
  name: string;
  instructions: string;
  agentId: string;
  modelPreference: string | null;
  triggerKind: TriggerKind;
  scheduleMode: "once" | "recurring";
  triggerType: "one_shot" | "cron";
  scheduleExpr: string;
  oneShotAt: string | null;
  timezone: string;
  connectors: string[];
  notificationMode: NotificationMode;
  verificationMode: VerificationMode;
  readOnly: boolean;
  allowedPaths: string[];
}

interface RoutineEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  job?: CronJob | null;
  detail?: ScheduleDetail | null;
  agents: AgentDisplay[];
  defaultAgentId?: string;
  busy?: boolean;
  errorMessage?: string | null;
  onSubmit: (payload: RoutineFormPayload) => Promise<void> | void;
  onDelete?: () => Promise<void> | void;
}

interface FormState extends RecurrencePickerValue {
  name: string;
  instructions: string;
  agentId: string;
  modelPreference: string;
  triggerKind: TriggerKind;
  connectors: string[];
  notificationMode: NotificationMode;
  verificationMode: VerificationMode;
  readOnly: boolean;
  allowedPaths: string;
}

function defaultDateTimeLocal(now: Date = new Date()): string {
  const next = new Date(now.getTime() + 60 * 60 * 1000);
  next.setMinutes(0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}T${pad(next.getHours())}:${pad(next.getMinutes())}`;
}

function jobInstructions(job: CronJob | null | undefined): string {
  if (!job) return "";
  const payload = job.payload || {};
  return String(
    payload.query ??
      payload.text ??
      payload.command ??
      job.summary ??
      job.command ??
      "",
  );
}

function jobOneShotAt(job: CronJob | null | undefined): string {
  if (!job?.schedule_expr) return defaultDateTimeLocal();
  const trimmed = job.schedule_expr.trim();
  // Schedule expr for one_shot is typically an ISO datetime string.
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return defaultDateTimeLocal();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

function buildInitialState(
  mode: "create" | "edit",
  job: CronJob | null | undefined,
  defaultAgentId: string | undefined,
  fallbackAgentId: string,
): FormState {
  if (mode === "edit" && job) {
    const triggerType = (job.trigger_type ?? "interval").trim();
    const scheduleMode = triggerType === "one_shot" ? "once" : "recurring";
    const cronExpr = (job.schedule_expr || job.cron_expression || "").trim();
    const detected = scheduleMode === "recurring" ? cronToPreset(cronExpr) : null;
    const recurrence = detected ?? {
      ...defaultRecurrenceFields(),
      preset: "custom" as const,
    };
    const customCron = scheduleMode === "recurring" && !detected ? cronExpr : "";

    const notificationMode = ((job.notification_policy as { mode?: string } | undefined)?.mode ??
      "summary_complete") as NotificationMode;
    const verificationMode = ((job.verification_policy as { mode?: string } | undefined)?.mode ??
      "post_write_if_any") as VerificationMode;

    return {
      name: job.summary ?? "",
      instructions: jobInstructions(job),
      agentId: job.bot_id ?? defaultAgentId ?? fallbackAgentId,
      modelPreference: job.model_preference ?? "",
      triggerKind: "schedule",
      scheduleMode,
      oneShotAt: scheduleMode === "once" ? jobOneShotAt(job) : defaultDateTimeLocal(),
      recurrence,
      customCron,
      timezone: job.timezone ?? "UTC",
      connectors: [],
      notificationMode,
      verificationMode,
      readOnly: false,
      allowedPaths: "",
    };
  }

  return {
    name: "",
    instructions: "",
    agentId: defaultAgentId ?? fallbackAgentId,
    modelPreference: "",
    triggerKind: "schedule",
    scheduleMode: "recurring",
    oneShotAt: defaultDateTimeLocal(),
    recurrence: defaultRecurrenceFields(),
    customCron: "",
    timezone: "UTC",
    connectors: [],
    notificationMode: "summary_complete",
    verificationMode: "post_write_if_any",
    readOnly: false,
    allowedPaths: "",
  };
}

function normalizePayload(state: FormState): RoutineFormPayload {
  const triggerType: "one_shot" | "cron" =
    state.scheduleMode === "once" ? "one_shot" : "cron";
  const scheduleExpr =
    state.scheduleMode === "once"
      ? new Date(state.oneShotAt).toISOString()
      : state.recurrence.preset === "custom"
        ? state.customCron.trim()
        : presetToCron(state.recurrence);

  const allowedPaths = state.allowedPaths
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  return {
    name: state.name.trim(),
    instructions: state.instructions.trim(),
    agentId: state.agentId,
    modelPreference: state.modelPreference.trim() || null,
    triggerKind: state.triggerKind,
    scheduleMode: state.scheduleMode,
    triggerType,
    scheduleExpr,
    oneShotAt: state.scheduleMode === "once" ? state.oneShotAt : null,
    timezone: state.timezone,
    connectors: state.connectors,
    notificationMode: state.notificationMode,
    verificationMode: state.verificationMode,
    readOnly: state.readOnly,
    allowedPaths,
  };
}

function validate(state: FormState): string | null {
  if (!state.name.trim()) return "nameRequired";
  if (!state.instructions.trim()) return "instructionsRequired";
  if (!state.agentId) return "agentRequired";
  if (state.triggerKind !== "schedule") return "triggerUnavailable";
  if (state.scheduleMode === "once" && !state.oneShotAt) return "dateTimeRequired";
  if (
    state.scheduleMode === "recurring" &&
    state.recurrence.preset === "custom" &&
    !state.customCron.trim()
  ) {
    return "customCronRequired";
  }
  return null;
}

export function RoutineEditor({
  open,
  onOpenChange,
  mode,
  job = null,
  agents,
  defaultAgentId,
  busy = false,
  errorMessage,
  onSubmit,
  onDelete,
}: RoutineEditorProps) {
  const { t } = useAppI18n();
  const fallbackAgentId = agents[0]?.id ?? "";
  const [state, setState] = useState<FormState>(() =>
    buildInitialState(mode, job, defaultAgentId, fallbackAgentId),
  );
  const [submitting, setSubmitting] = useState(false);
  const [validationKey, setValidationKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>("connectors");

  useEffect(() => {
    if (!open) return;
    setState(buildInitialState(mode, job, defaultAgentId, fallbackAgentId));
    setSubmitting(false);
    setValidationKey(null);
    setActiveTab("connectors");
  }, [open, mode, job, defaultAgentId, fallbackAgentId]);

  const recurrenceValue: RecurrencePickerValue = useMemo(
    () => ({
      scheduleMode: state.scheduleMode,
      oneShotAt: state.oneShotAt,
      recurrence: state.recurrence,
      customCron: state.customCron,
      timezone: state.timezone,
    }),
    [state.scheduleMode, state.oneShotAt, state.recurrence, state.customCron, state.timezone],
  );

  const handleRecurrenceChange = useCallback((next: RecurrencePickerValue) => {
    setState((prev) => ({
      ...prev,
      scheduleMode: next.scheduleMode,
      oneShotAt: next.oneShotAt,
      recurrence: next.recurrence,
      customCron: next.customCron,
      timezone: next.timezone,
    }));
  }, []);

  const handleConnectorsChange = useCallback((next: string[]) => {
    setState((prev) => ({ ...prev, connectors: next }));
  }, []);

  const disabled = submitting || busy;

  const validation = validate(state);
  const validationMessage = validation
    ? t(`routines.editor.validation.${validation}`)
    : null;

  const inlineError = errorMessage || (validationKey && validationMessage) || null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    if (validation) {
      setValidationKey(validation);
      return;
    }
    setValidationKey(null);
    setSubmitting(true);
    try {
      await onSubmit(normalizePayload(state));
    } finally {
      setSubmitting(false);
    }
  }

  const title =
    mode === "create"
      ? t("routines.editor.createTitle")
      : t("routines.editor.editTitle", {
          id: job?.id ?? 0,
          defaultValue: `Edit routine #${job?.id ?? 0}`,
        });

  const subtitle =
    mode === "create"
      ? t("routines.editor.createSubtitle")
      : t("routines.editor.editSubtitle");

  const submitLabel =
    mode === "create"
      ? t("routines.editor.actions.create")
      : t("routines.editor.actions.save");

  const requestClose = useCallback(() => {
    if (!disabled) onOpenChange(false);
  }, [disabled, onOpenChange]);

  const presence = useAnimatedPresence(open, null, { duration: 200 });
  useBodyScrollLock(presence.shouldRender);
  useEscapeToClose(presence.shouldRender, requestClose);

  if (!presence.shouldRender) return null;
  if (typeof document === "undefined") return null;

  return createPortal(
    <>
      <div
        className="app-overlay-backdrop app-overlay-anim z-[70]"
        data-visible={presence.isVisible}
        onClick={requestClose}
        aria-hidden="true"
      />
      <div className="app-modal-frame z-[80] items-stretch p-3 sm:p-5 lg:p-6">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="routine-editor-title"
          data-visible={presence.isVisible}
          className="app-modal-panel app-modal-anim relative flex h-full w-full max-w-[760px] flex-col overflow-hidden border-[var(--border-strong)]"
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={requestClose}
            className="app-surface-close"
            aria-label={t("routines.editor.actions.cancel")}
            disabled={disabled}
          >
            <X className="h-4 w-4" />
          </button>

          <header className="shrink-0 border-b border-[var(--divider-hair)] px-6 py-5 pr-14">
            <h2
              id="routine-editor-title"
              className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]"
            >
              {title}
            </h2>
            <p className="m-0 mt-1 text-[0.8125rem] text-[var(--text-tertiary)]">{subtitle}</p>
          </header>

          <form id="routine-editor-form" onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
            <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-6 py-6">
          <fieldset className="flex flex-col gap-2">
            <label className="flex flex-col gap-1.5">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("routines.editor.name")}
                <span className="ml-1 text-[var(--accent)]">*</span>
              </span>
              <Input
                value={state.name}
                placeholder={t("routines.editor.namePlaceholder")}
                onChange={(event) => setState((prev) => ({ ...prev, name: event.target.value }))}
                disabled={disabled}
                autoFocus
              />
            </label>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <label className="flex flex-col gap-1.5">
              <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("routines.editor.instructions")}
                <span className="ml-1 text-[var(--accent)]">*</span>
              </span>
              <textarea
                value={state.instructions}
                onChange={(event) =>
                  setState((prev) => ({ ...prev, instructions: event.target.value }))
                }
                placeholder={t("routines.editor.instructionsPlaceholder")}
                rows={6}
                disabled={disabled}
                className="min-h-[160px] w-full resize-y rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3.5 py-2.5 text-[0.875rem] leading-[1.5] text-[var(--text-primary)] outline-none transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] placeholder:text-[var(--text-quaternary)] hover:border-[var(--border-strong)] focus-visible:border-[var(--accent)] focus-visible:bg-[var(--panel)] disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>

            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                  {t("routines.editor.agent")}
                </span>
                <Select
                  value={state.agentId}
                  onValueChange={(v) => setState((prev) => ({ ...prev, agentId: v }))}
                  disabled={disabled || agents.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                  {t("routines.editor.model")}
                </span>
                <Input
                  value={state.modelPreference}
                  placeholder={t("routines.editor.modelPlaceholder")}
                  onChange={(event) =>
                    setState((prev) => ({ ...prev, modelPreference: event.target.value }))
                  }
                  disabled={disabled}
                  spellCheck={false}
                  autoCapitalize="off"
                  autoCorrect="off"
                />
              </label>
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
              {t("routines.editor.triggerHeading")}
            </legend>
            <div role="radiogroup" aria-label={t("routines.editor.triggerHeading")} className="flex flex-col gap-2">
              <TriggerTile
                icon={Calendar}
                title={t("routines.editor.triggers.schedule.title")}
                description={t("routines.editor.triggers.schedule.description")}
                selected={state.triggerKind === "schedule"}
                onClick={() => setState((prev) => ({ ...prev, triggerKind: "schedule" }))}
                disabled={disabled}
              />
              <TriggerTile
                icon={GitBranch}
                title={t("routines.editor.triggers.githubEvent.title")}
                description={t("routines.editor.triggers.githubEvent.description")}
                selected={state.triggerKind === "github_event"}
                disabled
                hint={t("routines.editor.triggers.comingSoon")}
              />
              <TriggerTile
                icon={Code2}
                title={t("routines.editor.triggers.api.title")}
                description={t("routines.editor.triggers.api.description")}
                selected={state.triggerKind === "api"}
                disabled
                hint={t("routines.editor.triggers.comingSoon")}
              />
            </div>
          </fieldset>

          {state.triggerKind === "schedule" ? (
            <fieldset className="flex flex-col gap-3">
              <legend className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                {t("routines.editor.when")}
              </legend>
              <RecurrencePicker
                value={recurrenceValue}
                onChange={handleRecurrenceChange}
                disabled={disabled}
              />
            </fieldset>
          ) : null}

          <div className="flex flex-col gap-3 border-t border-[var(--divider-hair)] pt-5">
            <SoftTabs
              items={[
                {
                  id: "connectors",
                  label: t("routines.editor.tabs.connectors", {
                    defaultValue: "Connectors",
                  }),
                },
                { id: "behavior", label: t("routines.editor.tabs.behavior") },
                { id: "permissions", label: t("routines.editor.tabs.permissions") },
              ]}
              value={activeTab}
              onChange={(id) => setActiveTab(id as SettingsTab)}
              ariaLabel={t("routines.editor.tabs.label")}
            />

            {activeTab === "connectors" ? (
              <ConnectorPicker
                agentId={state.agentId}
                value={state.connectors}
                onChange={handleConnectorsChange}
                disabled={disabled}
              />
            ) : null}

            {activeTab === "behavior" ? (
              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex flex-col gap-1.5">
                  <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                    {t("routines.editor.behavior.notification")}
                  </span>
                  <Select
                    value={state.notificationMode}
                    onValueChange={(v) =>
                      setState((prev) => ({
                        ...prev,
                        notificationMode: v as NotificationMode,
                      }))
                    }
                    disabled={disabled}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="summary_complete">
                        {t("routines.editor.behavior.notificationModes.summary_complete")}
                      </SelectItem>
                      <SelectItem value="failures_only">
                        {t("routines.editor.behavior.notificationModes.failures_only")}
                      </SelectItem>
                      <SelectItem value="none">
                        {t("routines.editor.behavior.notificationModes.none")}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </label>

                <label className="flex flex-col gap-1.5">
                  <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                    {t("routines.editor.behavior.verification")}
                  </span>
                  <Select
                    value={state.verificationMode}
                    onValueChange={(v) =>
                      setState((prev) => ({
                        ...prev,
                        verificationMode: v as VerificationMode,
                      }))
                    }
                    disabled={disabled}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="post_write_if_any">
                        {t("routines.editor.behavior.verificationModes.post_write_if_any")}
                      </SelectItem>
                      <SelectItem value="task_success">
                        {t("routines.editor.behavior.verificationModes.task_success")}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </label>
              </div>
            ) : null}

            {activeTab === "permissions" ? (
              <div className="flex flex-col gap-4">
                <label
                  className={cn(
                    "flex items-start gap-3 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3.5 py-3",
                    disabled && "opacity-60",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={state.readOnly}
                    onChange={(event) =>
                      setState((prev) => ({ ...prev, readOnly: event.target.checked }))
                    }
                    disabled={disabled}
                    className="mt-0.5 h-4 w-4 cursor-pointer accent-[var(--accent)]"
                  />
                  <span className="flex flex-1 flex-col gap-0.5">
                    <span className="text-[0.875rem] font-medium text-[var(--text-primary)]">
                      {t("routines.editor.permissions.readOnly")}
                    </span>
                    <span className="text-[0.8125rem] text-[var(--text-tertiary)]">
                      {t("routines.editor.permissions.readOnlyDescription")}
                    </span>
                  </span>
                </label>

                <label className="flex flex-col gap-1.5">
                  <span className="text-[0.75rem] font-medium uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
                    {t("routines.editor.permissions.allowedPaths")}
                  </span>
                  <textarea
                    value={state.allowedPaths}
                    onChange={(event) =>
                      setState((prev) => ({ ...prev, allowedPaths: event.target.value }))
                    }
                    placeholder={t("routines.editor.permissions.allowedPathsPlaceholder")}
                    rows={4}
                    disabled={disabled}
                    className="min-h-[96px] w-full resize-y rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3.5 py-2.5 font-mono text-[0.8125rem] leading-[1.5] text-[var(--text-primary)] outline-none transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] placeholder:text-[var(--text-quaternary)] hover:border-[var(--border-strong)] focus-visible:border-[var(--accent)] focus-visible:bg-[var(--panel)] disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <span className="text-[0.75rem] text-[var(--text-tertiary)]">
                    {t("routines.editor.permissions.allowedPathsHint")}
                  </span>
                </label>
              </div>
            ) : null}
          </div>

          {inlineError ? (
            <InlineAlert tone="danger">{inlineError}</InlineAlert>
          ) : null}
        </div>

            <footer className="shrink-0 border-t border-[var(--divider-hair)] px-6 py-4">
              <div className="flex items-center justify-between gap-3">
                {mode === "edit" && onDelete ? (
                  <Button
                    type="button"
                    variant="destructive"
                    size="md"
                    onClick={() => void onDelete()}
                    disabled={disabled}
                  >
                    <Trash2 className="icon-sm" strokeWidth={1.75} aria-hidden />
                    {t("routines.editor.actions.delete")}
                  </Button>
                ) : (
                  <span />
                )}

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="md"
                    onClick={requestClose}
                    disabled={disabled}
                  >
                    {t("routines.editor.actions.cancel")}
                  </Button>
                  <Button
                    type="submit"
                    variant="accent"
                    size="md"
                    disabled={disabled}
                  >
                    {submitting ? (
                      <Loader2 className="icon-sm animate-spin" strokeWidth={1.75} aria-hidden />
                    ) : null}
                    {submitLabel}
                  </Button>
                </div>
              </div>
            </footer>
          </form>
        </div>
      </div>
    </>,
    document.body,
  );
}
