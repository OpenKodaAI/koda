export function RootRouteTransitionLoading() {
  return (
    <div
      className="root-route-loading"
      data-testid="root-route-loading"
      role="status"
      aria-label="Loading route"
    >
      <span className="sr-only">Loading route</span>
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
