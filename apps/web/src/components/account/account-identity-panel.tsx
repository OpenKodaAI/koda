"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AtSign, Check, Fingerprint, LoaderCircle, LogOut, MonitorCheck, UserRound, X, type LucideIcon } from "lucide-react";
import { ProfilePhotoEditor } from "@/components/account/profile-photo-editor";
import { useOptionalAuth, type AuthOperator } from "@/components/providers/auth-provider";
import {
  AvatarPicker,
  getAvatarOption,
  useStoredOperatorAvatar,
  writeStoredOperatorAvatar,
} from "@/components/ui/avatar-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useToast } from "@/hooks/use-toast";
import { parseResponseError } from "@/lib/http-client";

const DISPLAY_NAME_MAX_LENGTH = 80;
const CONTROL_CHAR_PATTERN = /[\x00-\x1f\x7f]/;

type ProfileMutationResponse = {
  ok: boolean;
  operator?: AuthOperator | null;
  photoUrl?: string | null;
  photoHash?: string | null;
  byteSize?: number;
};

function normalizeDisplayName(value: string) {
  return value.trim().split(/\s+/).filter(Boolean).join(" ");
}

function validateDisplayName(value: string) {
  if (CONTROL_CHAR_PATTERN.test(value)) {
    return "Display name cannot contain control characters.";
  }
  const normalized = normalizeDisplayName(value);
  if (!normalized) {
    return "Display name is required.";
  }
  if (normalized.length > DISPLAY_NAME_MAX_LENGTH) {
    return "Display name must be 80 characters or fewer.";
  }
  return null;
}

function ProfileDatum({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="grid min-w-0 grid-cols-[auto_1fr] gap-3 px-4 py-3.5">
      <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--panel-soft)] text-[var(--text-tertiary)]">
        <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <dt className="font-mono text-[0.625rem] uppercase leading-4 tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
          {label}
        </dt>
        <dd className="m-0 mt-1 truncate text-[0.8125rem] text-[var(--text-primary)]" title={value || "—"}>
          {value || "—"}
        </dd>
      </span>
    </div>
  );
}

export function AccountIdentityPanel() {
  const { t, tl } = useAppI18n();
  const { showToast } = useToast();
  const { runAction, isPending } = useAsyncAction();
  const auth = useOptionalAuth();
  const operator = auth?.operator ?? null;
  const selectedAvatarId = useStoredOperatorAvatar();
  const selectedAvatar = useMemo(() => getAvatarOption(selectedAvatarId), [selectedAvatarId]);
  const [signingOut, setSigningOut] = useState(false);

  const displayName = useMemo(() => {
    return operator?.display_name?.trim() || operator?.username?.trim() || operator?.email?.trim() || tl("Operator");
  }, [operator?.display_name, operator?.email, operator?.username, tl]);
  const persistedDisplayName = normalizeDisplayName(operator?.display_name || displayName);
  const [displayNameDraft, setDisplayNameDraft] = useState(persistedDisplayName);
  const [displayNameError, setDisplayNameError] = useState<string | null>(null);

  useEffect(() => {
    setDisplayNameDraft(persistedDisplayName);
    setDisplayNameError(null);
  }, [operator?.id, persistedDisplayName]);

  const normalizedDraft = normalizeDisplayName(displayNameDraft);
  const nameDirty = normalizedDraft !== persistedDisplayName;
  const savingName = isPending("account.profile.name");

  const handleSignOut = async () => {
    if (!auth || signingOut) return;
    setSigningOut(true);
    showToast(tl("Sign-out requested."), "success", {
      id: "account.sign_out.requested",
      durationMs: 2200,
    });
    try {
      await auth.signOut();
    } finally {
      setSigningOut(false);
    }
  };

  const updateOperatorFromResponse = (data: ProfileMutationResponse) => {
    if (data.operator && auth?.updateOperator) {
      auth.updateOperator(data.operator);
    }
  };

  const handleAvatarChange = (avatarId: string) => {
    const normalized = writeStoredOperatorAvatar(avatarId);
    showToast(tl("Avatar atualizado."), "success", {
      id: `account.profile.avatar.${normalized}`,
      durationMs: 1800,
    });
  };

  const handleSaveName = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!auth?.operator || savingName) return;
    const validationError = validateDisplayName(displayNameDraft);
    if (validationError) {
      setDisplayNameError(validationError);
      showToast(tl("Informe um nome de exibição válido."), "warning", {
        id: "account.profile.name.invalid",
      });
      return;
    }
    if (!nameDirty) return;

    await runAction(
      "account.profile.name",
      async () => {
        const response = await fetch("/api/control-plane/auth/profile", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: normalizedDraft }),
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(await parseResponseError(response, "Unable to update display name."));
        }
        return (await response.json()) as ProfileMutationResponse;
      },
      {
        successMessage: tl("Nome atualizado."),
        onSuccess: (data) => {
          setDisplayNameError(null);
          setDisplayNameDraft(data.operator?.display_name || normalizedDraft);
          updateOperatorFromResponse(data);
        },
      },
    );
  };

  const handleUploadPhoto = async (blob: Blob) => {
    if (!auth?.operator) return;
    await runAction(
      "account.profile.photo.upload",
      async () => {
        const formData = new FormData();
        formData.append("photo", blob, "profile-photo.jpg");
        const response = await fetch("/api/control-plane/auth/profile/photo", {
          method: "POST",
          body: formData,
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(await parseResponseError(response, "Unable to update profile photo."));
        }
        return (await response.json()) as ProfileMutationResponse;
      },
      {
        successMessage: tl("Foto atualizada."),
        onSuccess: updateOperatorFromResponse,
      },
    );
  };

  const handleRemovePhoto = async () => {
    if (!auth?.operator) return;
    await runAction(
      "account.profile.photo.remove",
      async () => {
        const response = await fetch("/api/control-plane/auth/profile/photo", {
          method: "DELETE",
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(await parseResponseError(response, "Unable to remove profile photo."));
        }
        return (await response.json()) as ProfileMutationResponse;
      },
      {
        successMessage: tl("Foto removida."),
        onSuccess: updateOperatorFromResponse,
      },
    );
  };

  return (
    <Card>
      <CardHeader className="px-5 py-4">
        <div className="min-w-0">
          <CardTitle>{t("auth.account_menu.account")}</CardTitle>
          <CardDescription>{tl("Operator identity and synced profile preferences.")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid min-w-0 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="border-b border-[var(--divider-hair)] p-5 lg:border-b-0 lg:border-r">
            <ProfilePhotoEditor
              currentPhotoUrl={operator?.profile_photo_url ?? null}
              displayName={displayName}
              fallbackAvatarId={selectedAvatarId}
              onUpload={handleUploadPhoto}
              onRemove={handleRemovePhoto}
            />
            <div className="mt-5 grid gap-2">
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-[0.625rem] uppercase leading-4 tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                  {tl("Avatar")}
                </span>
                <span className="truncate text-right text-[0.6875rem] text-[var(--text-tertiary)]">
                  {selectedAvatar.label}
                </span>
              </div>
              <AvatarPicker
                value={selectedAvatarId}
                onChange={handleAvatarChange}
                displayName={displayName}
                subtitle={tl("Choose avatar color")}
                showPreview={false}
              />
            </div>
          </div>

          <div className="min-w-0">
            <div className="border-b border-[var(--divider-hair)] p-4">
              <form className="grid gap-3" onSubmit={(event) => void handleSaveName(event)}>
                <div className="grid gap-1.5">
                  <label
                    htmlFor="account-display-name"
                    className="font-mono text-[0.625rem] uppercase leading-4 tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]"
                  >
                    Display name
                  </label>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Input
                      id="account-display-name"
                      value={displayNameDraft}
                      onChange={(event) => {
                        setDisplayNameDraft(event.target.value);
                        setDisplayNameError(null);
                      }}
                      maxLength={DISPLAY_NAME_MAX_LENGTH + 12}
                      invalid={Boolean(displayNameError)}
                      disabled={!auth?.operator || savingName}
                      aria-describedby={displayNameError ? "account-display-name-error" : undefined}
                    />
                    <div className="flex gap-2">
                      <Button
                        type="submit"
                        variant="accent"
                        size="sm"
                        disabled={!auth?.operator || !nameDirty || savingName}
                      >
                        {savingName ? (
                          <LoaderCircle className="h-3.5 w-3.5 animate-spin" strokeWidth={2} aria-hidden="true" />
                        ) : (
                          <Check className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                        )}
                        <span>{tl("Save")}</span>
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={!nameDirty || savingName}
                        onClick={() => {
                          setDisplayNameDraft(persistedDisplayName);
                          setDisplayNameError(null);
                        }}
                      >
                        <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                        <span>{tl("Cancel")}</span>
                      </Button>
                    </div>
                  </div>
                  {displayNameError ? (
                    <p id="account-display-name-error" role="alert" className="m-0 text-[0.75rem] text-[var(--tone-danger-dot)]">
                      {displayNameError}
                    </p>
                  ) : null}
                </div>
              </form>
            </div>

            <dl className="grid min-w-0 divide-y divide-[var(--divider-hair)] sm:grid-cols-2 sm:divide-x sm:divide-y-0">
              <div className="divide-y divide-[var(--divider-hair)]">
                <ProfileDatum icon={AtSign} label="Email" value={operator?.email || "—"} />
                <ProfileDatum icon={Fingerprint} label="Display name" value={operator?.display_name || displayName} />
              </div>
              <div className="divide-y divide-[var(--divider-hair)]">
                <ProfileDatum icon={UserRound} label="Username" value={operator?.username || "—"} />
                <ProfileDatum
                  icon={MonitorCheck}
                  label={tl("Photo")}
                  value={operator?.profile_photo_hash ? tl("Uploaded") : selectedAvatar.label}
                />
              </div>
            </dl>
            <div className="flex flex-col gap-3 border-t border-[var(--divider-hair)] px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="m-0 text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
                {tl("Profile changes are saved to this operator account.")}
              </p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  void handleSignOut();
                }}
                disabled={!auth || signingOut}
                className="self-start"
              >
                {signingOut ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" strokeWidth={1.75} />
                ) : (
                  <LogOut className="h-4 w-4" strokeWidth={1.75} />
                )}
                <span>{t("auth.account_menu.sign_out")}</span>
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
