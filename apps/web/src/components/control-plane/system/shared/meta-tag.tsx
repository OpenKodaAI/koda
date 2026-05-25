import { cn } from "@/lib/utils";

export function MetaTag({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "accent" | "danger";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium",
        tone === "accent" && "bg-[rgba(113,219,190,0.12)] text-[var(--text-primary)]",
        tone === "danger" && "bg-[rgba(255,110,110,0.12)] text-[var(--tone-danger-text)]",
        tone === "neutral" && "bg-[rgba(255,255,255,0.04)] text-[var(--text-secondary)]",
      )}
    >
      {label}
    </span>
  );
}
