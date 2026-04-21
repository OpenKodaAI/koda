# Authentication & Recovery Model

Koda runs in **single-user mode**: one owner account, created on first boot, manages every
agent and integration through the web dashboard. This document describes how that account is
created, how sessions work, and how password recovery is designed to be safe on a public
deployment without a mail relay.

_Last reviewed: 2026-04-17._

## Account creation (first boot)

The first-run flow (`/setup`) authenticates the registration request with one of three
mechanisms, checked in priority order:

1. **Legacy registration token** — obtained via `koda bootstrap-code issue`, then
   `POST /api/control-plane/auth/bootstrap/exchange`. Still supported for automated installs.
2. **Bootstrap code (recommended for VPS)** — on first boot the control plane writes
   `${STATE_ROOT_DIR}/control_plane/bootstrap.txt` (mode `0600`) and prints it to the
   container log once. The operator SSHs in, reads the file, pastes it into `/setup`, and the
   file is deleted after registration.
3. **Loopback trust (dev only)** — when `ALLOW_LOOPBACK_BOOTSTRAP=true` and the request comes
   from `127.0.0.1` / `::1` with no `X-Forwarded-For` hop, no code is required. This mode is
   refused at boot when `KODA_ENV=production`.

Passwords are hashed with **Argon2id** (`argon2-cffi` defaults). The password must:

- be 12+ characters (`CONTROL_PLANE_OPERATOR_PASSWORD_MIN_LENGTH`)
- include at least 3 of 4 classes (upper / lower / digit / symbol)
- not contain the username or email local-part
- not appear in the bundled top-500 common-passwords list
- not have degenerate Shannon entropy (`>= 2.0 bits/char`)

On successful registration the control plane:

- creates the user row in `cp_operator_users`
- issues **10 one-time recovery codes**, hashed with Argon2 in
  `cp_operator_recovery_codes`, with a generation marker copied onto
  `cp_operator_users.recovery_generation`
- opens a session
- returns the plaintext codes **once only** in the HTTP response

The web UI shows the codes on the second setup screen, requires an acknowledgement checkbox
("I saved my codes"), and never retrieves them again.

## Session model

- Session secret: 32-byte URL-safe random, hashed with SHA-256 before persistence in
  `cp_operator_sessions`.
- TTL: `CONTROL_PLANE_OPERATOR_SESSION_TTL_SECONDS` (default: 7 days).
- Transport: session token is sealed into the `koda_operator_session` cookie with AES-256-GCM
  using `WEB_OPERATOR_SESSION_SECRET`. Cookie flags: `HttpOnly; Secure; SameSite=Strict`.
- Revocation: logout revokes the current session. Password _change_ revokes every other
  session for the same user and keeps the initiating session alive. Password _reset_ via
  recovery code revokes **all** sessions for the user.

## Recovery code lifecycle

- Codes are 12 lowercase characters (`xxxx-xxxx-xxxx`) from the `BOOTSTRAP_ALPHABET`
  (no `I`, `O`, `0`, `1`).
- Each code can be used exactly once, enforced by `consumed_at` and `generation` matching
  against `cp_operator_users.recovery_generation`.
- After a successful `POST /api/control-plane/auth/password/recover`:
  - the consumed code is marked `consumed_at = now`, `consumed_reason = "password_reset"`
  - **every other unused code** under the same generation is also marked consumed with
    `consumed_reason = "password_reset_invalidation"`
  - all sessions are revoked
  - the password hash is rotated
- The owner must regenerate a fresh batch from `/settings/account` › Security (calling
  `POST /api/control-plane/auth/recovery-codes/regenerate`, which requires the current
  password).

This mirrors Google and GitHub's policy: a printed sheet of codes is useful once, but once
one of them is compromised the whole sheet has to be rotated.

## Rate limits (bucket budgets)

Per-IP, enforced in `koda/control_plane/rate_limit.py`:

| Endpoint                                            | Budget              |
| --------------------------------------------------- | ------------------- |
| `POST /auth/login`                                  | 5 requests / 5 min  |
| `POST /auth/password/recover`                       | 5 requests / hour   |
| `POST /auth/password/change`                        | 10 requests / hour  |
| `POST /auth/register-owner`                         | 3 requests / hour   |
| `POST /auth/recovery-codes/regenerate`              | 3 requests / hour   |
| `POST /auth/bootstrap/exchange`                     | 10 requests / hour  |
| `POST /auth/bootstrap/codes`                        | 3 requests / hour   |

Plus the pre-existing per-IP general bucket (`CONTROL_PLANE_RATE_LIMIT`, default 120/min) and
the stricter auth-failure bucket (`CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT`, default 5/min
triggered on any 401/403).

Account-level lockout remains on top of the rate limits: after
`CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES` failed attempts, the row locks for
`CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS`.

## Side-channel mitigations

- All auth-failure paths pad to a 300 ms floor (`_FAILURE_TIMING_FLOOR_SECONDS`) so the
  caller cannot distinguish `user not found` from `wrong password` from `invalid recovery
  code`.
- Responses use a single generic error (`"Invalid credentials."`, or equivalent) without
  leaking whether the identifier exists. The i18n layer binds every failure mode to the same
  message in every language.
- The structured logging pipeline redacts `password`, `new_password`, `current_password`,
  `recovery_code`, `session_token`, `registration_token`, `bootstrap_code`, `code`,
  `totp_secret`, `api_key`, `secret`, `token`, `authorization`, and `cookie` keys.

## Security headers

`apps/web/middleware.ts` enforces:

- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` (when HTTPS)
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()`

On `/login`, `/setup`, and `/forgot-password` a tighter Content-Security-Policy is added:

```
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
font-src 'self' data:;
connect-src 'self';
form-action 'self';
frame-ancestors 'none';
base-uri 'self';
object-src 'none';
```

Next.js App Router injects inline RSC bootstrap scripts that are required for form
hydration, so `'unsafe-inline'` on `script-src` is unavoidable. Everything else is
narrower than the global policy — no third-party origins, no framing, no `<object>`
embedding, form submissions pinned to the same origin. Auth pages also set
`Cache-Control: no-store`.

## Audit events

| Event                                              | Emitted when                                                 |
| -------------------------------------------------- | ------------------------------------------------------------ |
| `security.operator_bootstrap_file_written`         | First-boot bootstrap code written to disk                    |
| `security.operator_bootstrap_loopback_trust_used`  | Loopback-trust path was accepted                             |
| `security.operator_owner_registered`               | Owner account created (includes `bootstrap_mode`)            |
| `security.operator_login_succeeded`                | Successful login                                             |
| `security.operator_login_failed`                   | Login failure (with reason, never the attempted credentials) |
| `security.operator_logout`                         | User-initiated logout                                        |
| `security.operator_password_changed`               | Password change (authenticated)                              |
| `security.operator_password_reset`                 | Password reset via recovery code                             |
| `security.operator_password_reset_failed`          | Identifier lookup or code-mismatch during reset              |
| `security.operator_recovery_codes_regenerated`     | Fresh recovery batch issued                                  |
| `security.operator_session_revoked`                | Session revoked by the user                                  |
| `security.control_plane_endpoint_rate_limited`     | Sensitive-endpoint bucket exhausted                          |

## Out of scope in this release

- SMTP-based email verification / password reset.
- Two-factor authentication (TOTP). The `cp_operator_users.totp_secret` column is provisioned
  but unused; enabling it only requires a new endpoint + UI step.
- Multi-user support, including invitation flows.
- SSO / OIDC federation for the operator console.

Future work tracked through separate issues.
