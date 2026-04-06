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

export function MaskedSecretPreview({
  preview,
  fallbackLabel = "Segredo configurado",
  className,
}: {
  preview?: string;
  fallbackLabel?: string;
  className?: string;
}) {
  const { tl } = useAppI18n();
  const [visible, setVisible] = useState(true);
  const maskedValue = preview?.trim() || tl(fallbackLabel);

  return (
    <div className={cn("flex items-start gap-2", className)}>
      <div className="min-w-0 flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 font-mono text-xs break-all text-[var(--text-secondary)]">
        {visible ? maskedValue : "••••••••••"}
      </div>
      <SecretVisibilityButton
        revealed={visible}
        onToggle={() => setVisible((current) => !current)}
        masked
        className="mt-0.5"
      />
    </div>
  );
}
