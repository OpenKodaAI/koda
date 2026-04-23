export const WEB_OPERATOR_SESSION_COOKIE = "koda_operator_session";
export const WEB_OPERATOR_SESSION_MAX_AGE_SECONDS = 60 * 60 * 8;

/**
 * Marker cookie used by middleware to decide between /setup (no owner yet) and
 * /login (owner exists but no session). It carries NO authentication value —
 * readable by JavaScript, read-only hint. The server sets it whenever it sees
 * `has_owner=true` from the control plane; middleware reads it to route
 * unauthenticated traffic without a server-round-trip.
 */
export const OWNER_EXISTS_HINT_COOKIE = "koda_has_owner";
export const OWNER_EXISTS_HINT_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

/**
 * Short-lived marker set by the register-owner route while the operator still
 * needs to acknowledge their one-time recovery codes. While the cookie is set,
 * middleware keeps /setup reachable even though the operator already has a
 * valid session cookie. Cleared by the acknowledge endpoint and by logout.
 */
export const PENDING_RECOVERY_COOKIE = "koda_setup_pending_recovery";
export const PENDING_RECOVERY_MAX_AGE_SECONDS = 60 * 30;
