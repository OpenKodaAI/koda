// Minimal full-screen loading state for the auth route — the root loading.tsx
// renders the dashboard skeleton, which would briefly flash around /login while
// the server component resolves the auth-status fetch.
export default function LoginLoading() {
  return (
    <div className="flex min-h-[100dvh] w-full items-center justify-center bg-[var(--canvas)]">
      <div className="h-9 w-9 rounded-full border-2 border-[var(--border-subtle)] border-t-[var(--accent)] animate-spin" />
    </div>
  );
}
