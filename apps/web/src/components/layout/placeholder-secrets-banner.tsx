"use client";

import { ExternalLink } from "lucide-react";
import { useOptionalAuth } from "@/components/providers/auth-provider";
import { InlineAlert } from "@/components/ui/inline-alert";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  placeholderSecretsStatusSchema,
  type PlaceholderSecretsStatus,
} from "@/lib/contracts/system";
import { cn } from "@/lib/utils";

export const PLACEHOLDER_SECRETS_PATH = "/api/control-plane/system-settings/placeholder-secrets";

async function fetchPlaceholderSecrets(): Promise<PlaceholderSecretsStatus> {
  const response = await fetch(PLACEHOLDER_SECRETS_PATH, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`placeholder-secrets returned ${response.status}`);
  }
  return placeholderSecretsStatusSchema.parse(await response.json());
}

/**
 * Persistent shell banner shown while the Postgres password or an S3 secret
 * still holds its public `.env.example` placeholder. The signal comes from an
 * operator-only route that returns key names, never values. Koda keeps
 * running; the banner only links to the rotation steps.
 */
export function PlaceholderSecretsBanner({ className }: { className?: string }) {
  const auth = useOptionalAuth();
  const { t } = useAppI18n();
  const { data } = useControlPlaneQuery({
    tier: "catalog",
    queryKey: ["control-plane", "system-settings", "placeholder-secrets"] as const,
    queryFn: fetchPlaceholderSecrets,
    enabled: Boolean(auth?.isAuthenticated),
  });

  if (!data || data.placeholder_keys.length === 0) {
    return null;
  }

  return (
    <InlineAlert
      tone="warning"
      className={cn("shrink-0", className)}
      action={
        <a
          href={data.rotation_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium underline underline-offset-2"
        >
          {t("securityBanner.placeholderSecrets.action")}
          <ExternalLink className="icon-xs" strokeWidth={1.75} aria-hidden="true" />
        </a>
      }
    >
      <p className="font-medium">{t("securityBanner.placeholderSecrets.title")}</p>
      <p className="mt-0.5 text-[var(--text-secondary)]">
        {t("securityBanner.placeholderSecrets.description", {
          keys: data.placeholder_keys.join(", "),
        })}
      </p>
    </InlineAlert>
  );
}
