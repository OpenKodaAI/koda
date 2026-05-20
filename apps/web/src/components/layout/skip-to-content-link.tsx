"use client";

import { translate } from "@/lib/i18n";
export function SkipToContentLink() {
  return (
    <a
      href="#conteudo-principal"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[80] focus:rounded-lg focus:bg-[var(--panel-strong)] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-[var(--text-primary)]"
      suppressHydrationWarning
    >
      {translate("generated.shell.ir_para_o_conteudo_principal_0ed56a5e")}</a>
  );
}
