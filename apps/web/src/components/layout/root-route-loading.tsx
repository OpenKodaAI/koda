import { translate } from "@/lib/i18n";
export function RootRouteTransitionLoading() {
  return (
    <div
      className="root-route-loading"
      data-testid="root-route-loading"
      role="status"
      aria-label={translate("generated.shell.loading_route_0945ac20")}
    >
      <span className="sr-only">{translate("generated.shell.loading_route_0945ac20")}</span>
      <span className="root-route-loading__bar" aria-hidden="true" />
    </div>
  );
}

export function RootRouteLoadingForPathname({
  pathname,
}: {
  pathname?: string | null;
}) {
  void pathname;
  return <RootRouteTransitionLoading />;
}
