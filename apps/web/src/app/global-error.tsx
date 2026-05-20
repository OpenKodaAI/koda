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
  const { t } = useAppI18n();
  return (
    <html lang="en-US">
      <body className="bg-background text-foreground">
        <div className="mx-auto flex min-h-screen w-full max-w-[1720px] items-center px-6 py-10">
          <RouteErrorState
            title={t("generated.routes.we_hit_an_application_error_c753e3c3")}
            description={error.message || t("generated.routes.the_application_could_not_recover_from_this__cdbfd90d")}
            onRetry={reset}
          />
        </div>
      </body>
    </html>
  );
}
