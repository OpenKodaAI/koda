"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition, type FormEvent } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { PageHeader } from "@/components/layout/header";
import { PageEmptyState, PageSection } from "@/components/ui/page-primitives";

export function ControlPlaneUnavailable({
  title,
  description,
}: {
  title?: string;
  description: string;
}) {
  const { t } = useAppI18n();
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const resolvedTitle = title ?? t("controlPlane.unavailable.title");

  async function submitOperatorSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const trimmed = token.trim();
    if (!trimmed) {
      setError(t("controlPlane.unavailable.description"));
      return;
    }

    try {
      const response = await fetch("/api/control-plane/web-auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ token: trimmed }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        setError(payload?.error || t("controlPlane.unavailable.description"));
        return;
      }

      setToken("");
      startTransition(() => {
        router.refresh();
      });
    } catch {
      setError(t("controlPlane.unavailable.description"));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={resolvedTitle} description={description} />

      <PageSection className="p-5 sm:p-6">
        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <PageEmptyState
            title={t("controlPlane.unavailable.pageTitle")}
            description={t("controlPlane.unavailable.description")}
            actions={
              <Link
                href="/control-plane"
                className="button-shell button-shell--primary button-shell--sm"
              >
                {t("controlPlane.unavailable.retry")}
              </Link>
            }
          />

          <form className="space-y-4 rounded-2xl border border-white/10 bg-white/5 p-4" onSubmit={submitOperatorSession}>
            <div className="space-y-2">
              <h2 className="text-sm font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                Operator session
              </h2>
              <p className="text-sm text-muted-foreground">
                Paste the control-plane token once to open an HTTP-only session for this browser.
                The token is not stored in query strings or local storage.
              </p>
            </div>
            <label className="grid gap-2 text-sm">
              Control-plane token
              <input
                className="rounded-xl border border-white/10 bg-background px-3 py-2 outline-none"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder="CONTROL_PLANE_API_TOKEN"
                type="password"
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            <button
              className="button-shell button-shell--primary button-shell--sm"
              disabled={isPending}
              type="submit"
            >
              {isPending ? "Connecting..." : "Connect"}
            </button>
          </form>
        </div>
      </PageSection>
    </div>
  );
}
