export function DaySeparator({ label }: { label: string }) {
  return (
    <div role="separator" aria-label={label} className="flex justify-center py-4">
      <span className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {label}
      </span>
    </div>
  );
}
