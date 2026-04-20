export default function SetupLoading() {
  return (
    <div className="flex min-h-[100dvh] w-full items-center justify-center bg-[var(--canvas)]">
      <div className="h-9 w-9 rounded-full border-2 border-[var(--border-subtle)] border-t-[var(--accent)] animate-spin" />
    </div>
  );
}
