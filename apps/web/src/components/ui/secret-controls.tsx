"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState, type InputHTMLAttributes } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

type SecretVisibilityButtonProps = {
  revealed: boolean;
  onToggle: () => void;
  className?: string;
  masked?: boolean;
};

export function SecretVisibilityButton({
  revealed,
  onToggle,
  className,
  masked = false,
}: SecretVisibilityButtonProps) {
  const { tl } = useAppI18n();

  return (
    <button
      type="button"
      aria-label={
        masked
          ? revealed
            ? tl("Ocultar valor mascarado")
            : tl("Mostrar valor mascarado")
          : revealed
            ? tl("Esconder valor")
            : tl("Visualizar valor")
      }
      onClick={onToggle}
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-transparent text-[var(--icon-secondary)] transition-colors hover:border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] hover:text-[var(--icon-primary)]",
        className,
      )}
    >
      {revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
    </button>
  );
}

type SecretInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  inputClassName?: string;
};

export function SecretInput({
  className,
  inputClassName,
  autoComplete,
  spellCheck,
  ...props
}: SecretInputProps) {
  const [revealed, setRevealed] = useState(false);

  return (
    <div className={cn("relative isolate", className)}>
      <input
        {...props}
        type={revealed ? "text" : "password"}
        autoComplete={autoComplete ?? "new-password"}
        spellCheck={spellCheck ?? false}
        className={cn(
          "field-shell w-full px-4 py-2.5 pr-14 text-sm text-[var(--text-primary)]",
          inputClassName,
        )}
      />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 flex items-center pr-2">
        <SecretVisibilityButton
          revealed={revealed}
          onToggle={() => setRevealed((current) => !current)}
          className="pointer-events-auto"
        />
      </div>
    </div>
  );
}

// MaskedSecretPreview was intentionally removed. Stored secrets must never be
// displayed to the user — even in masked form. Callers should render a
// "Configurada/Armazenada" badge plus a replace action instead.
