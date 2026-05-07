"use client";

import { AlertTriangle } from "lucide-react";
import { Alert, AlertIcon, AlertTitle } from "@/components/ui/alert-1";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";

export function SettingsWarnings() {
  const { localWarnings } = useSystemSettings();
  const { tl } = useAppI18n();

  if (!localWarnings || localWarnings.length === 0) return null;

  return (
    <Alert variant="warning" appearance="outline" size="sm" className="mb-4">
      <AlertIcon>
        <AlertTriangle />
      </AlertIcon>
      <AlertTitle>
        <p className="font-medium">
          {localWarnings.length === 1
            ? tl("1 aviso de configuração")
            : tl(`${localWarnings.length} avisos de configuração`)}
        </p>
        <ul className="mt-1.5 flex flex-col gap-1">
          {localWarnings.map((warning, i) => (
            <li
              key={i}
              className="text-[var(--text-secondary)] leading-snug"
            >
              {tl(warning)}
            </li>
          ))}
        </ul>
      </AlertTitle>
    </Alert>
  );
}
