"use client";

import {
  createRouteErrorBoundary,
  type RouteErrorBoundaryProps,
} from "@/components/ui/route-error-state";

const ApplicationError = createRouteErrorBoundary(
  "generated.routes.we_hit_an_application_error_c753e3c3",
  "generated.routes.the_application_could_not_recover_from_this__cdbfd90d",
);

export default function GlobalError(props: RouteErrorBoundaryProps) {
  return (
    <html lang="en-US">
      <body className="bg-background text-foreground">
        <div className="mx-auto flex min-h-screen w-full max-w-[1720px] items-center px-6 py-10">
          <ApplicationError {...props} />
        </div>
      </body>
    </html>
  );
}
