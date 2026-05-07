"use client";

import Link from "next/link";
import { useState } from "react";
import { LogOut, User } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useOptionalAuth, type AuthOperator } from "@/components/providers/auth-provider";
import { cn } from "@/lib/utils";

function deriveInitial(operator: AuthOperator): string {
  const candidate =
    operator.display_name?.trim() ||
    operator.email?.trim() ||
    operator.username?.trim() ||
    "";
  return candidate.charAt(0).toUpperCase() || "?";
}

export interface AccountMenuProps {
  className?: string;
}

export function AccountMenu({ className }: AccountMenuProps) {
  const { t } = useAppI18n();
  const auth = useOptionalAuth();
  const [open, setOpen] = useState(false);

  if (!auth?.operator) return null;
  const operator = auth.operator;
  const initial = deriveInitial(operator);
  const label =
    operator.display_name?.trim() ||
    operator.email?.trim() ||
    operator.username?.trim() ||
    t("auth.account_menu.account");

  const handleSignOut = async () => {
    setOpen(false);
    await auth.signOut();
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t("auth.account_menu.trigger_label")}
          className={cn(
            "inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] text-[12px] font-medium text-[var(--text-primary)] transition-[background-color,border-color] duration-150 ease-out hover:border-[color:var(--border-strong)] hover:bg-[color:var(--panel)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent)]",
            className,
          )}
          data-testid="account-menu-trigger"
        >
          <Avatar className="h-7 w-7">
            <AvatarFallback className="bg-transparent text-[12px] font-medium text-[var(--text-primary)] border-none">
              {initial}
            </AvatarFallback>
          </Avatar>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="w-[14rem] p-1.5">
        <div className="px-2 pb-2 pt-1">
          <p className="m-0 truncate text-[12.5px] font-medium text-[var(--text-primary)]">
            {label}
          </p>
          {operator.email && operator.email !== label ? (
            <p className="m-0 truncate text-[11.5px] text-[var(--text-tertiary)]">
              {operator.email}
            </p>
          ) : null}
        </div>
        <div className="border-t border-[color:var(--divider-hair)]" />
        <Link
          href="/settings/account"
          onClick={() => setOpen(false)}
          className="mt-1 flex items-center gap-2 rounded-[var(--radius-chip)] px-2 py-1.5 text-[13px] text-[var(--text-primary)] transition-colors duration-150 hover:bg-[color:var(--hover-tint,rgba(255,255,255,0.04))] focus-visible:outline-none focus-visible:bg-[color:var(--hover-tint,rgba(255,255,255,0.04))]"
        >
          <User className="h-4 w-4 text-[var(--text-tertiary)]" strokeWidth={1.75} />
          <span>{t("auth.account_menu.account")}</span>
        </Link>
        <button
          type="button"
          onClick={handleSignOut}
          className="flex w-full items-center gap-2 rounded-[var(--radius-chip)] px-2 py-1.5 text-left text-[13px] text-[var(--text-primary)] transition-colors duration-150 hover:bg-[color:var(--hover-tint,rgba(255,255,255,0.04))] focus-visible:outline-none focus-visible:bg-[color:var(--hover-tint,rgba(255,255,255,0.04))]"
          data-testid="account-menu-sign-out"
        >
          <LogOut className="h-4 w-4 text-[var(--text-tertiary)]" strokeWidth={1.75} />
          <span>{t("auth.account_menu.sign_out")}</span>
        </button>
      </PopoverContent>
    </Popover>
  );
}
