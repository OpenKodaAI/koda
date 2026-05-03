"use client";

import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useOptionalAuth } from "@/components/providers/auth-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";

export function AccountIdentityPanel() {
  const { t } = useAppI18n();
  const auth = useOptionalAuth();
  const operator = auth?.operator ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("auth.account_menu.account")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-[120px_1fr] gap-y-1 text-[13px]">
          <dt className="text-[var(--text-tertiary)]">Email</dt>
          <dd className="m-0 truncate text-[var(--text-primary)]">
            {operator?.email || "—"}
          </dd>
          <dt className="text-[var(--text-tertiary)]">Username</dt>
          <dd className="m-0 truncate text-[var(--text-primary)]">
            {operator?.username || "—"}
          </dd>
          {operator?.display_name ? (
            <>
              <dt className="text-[var(--text-tertiary)]">Display name</dt>
              <dd className="m-0 truncate text-[var(--text-primary)]">
                {operator.display_name}
              </dd>
            </>
          ) : null}
        </dl>
        <div className="border-t border-[color:var(--divider-hair)]" />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => {
            void auth?.signOut();
          }}
          className="self-start"
        >
          <LogOut className="h-4 w-4" strokeWidth={1.75} />
          <span>{t("auth.account_menu.sign_out")}</span>
        </Button>
      </CardContent>
    </Card>
  );
}
