"use client";

import { RouteErrorState } from "@/components/ui/route-error-state";
import { useAppI18n } from "@/hooks/use-app-i18n";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { tl } = useAppI18n();
  return (
    <html lang="en-US">
      <body className="bg-background text-foreground">
        <div className="mx-auto flex min-h-screen w-full max-w-[1720px] items-center px-6 py-10">
          <RouteErrorState
            title={tl("We hit an application error")}
            description={error.message || tl("The application could not recover from this failure.")}
            onRetry={reset}
          />
        </div>
      </body>
    </html>
  );
}
