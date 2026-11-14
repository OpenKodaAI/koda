/**
 * Control-plane API paths the dashboard forwards without an operator session.
 *
 * This is the backend allowlist (`_PUBLIC_CONTROL_PLANE_API_PATHS` in
 * `koda/control_plane/api.py`); `tests/test_control_plane_public_paths.py`
 * fails when the two lists differ. Both the proxy (`src/proxy.ts`) and the
 * catch-all BFF route read this one list. Every other control-plane path,
 * `onboarding/readiness` included, needs a session here and in the backend.
 */
export const PUBLIC_CONTROL_PLANE_API_PATHS: ReadonlySet<string> = new Set([
  "/api/control-plane/onboarding/status",
  "/api/control-plane/auth/status",
  "/api/control-plane/auth/bootstrap/exchange",
  "/api/control-plane/auth/login",
  "/api/control-plane/auth/register-owner",
  "/api/control-plane/auth/password/recover",
]);

export function isPublicControlPlaneApiPath(pathname: string): boolean {
  return PUBLIC_CONTROL_PLANE_API_PATHS.has(pathname);
}
