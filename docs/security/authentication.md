# Authentication & Recovery Model

Koda runs in **single-user mode**: one owner account, created on first boot, manages every
agent and integration through the web dashboard. This document describes how that account is
created, how sessions work, and how password recovery is designed to be safe on a public
deployment without a mail relay.

_Last reviewed: 2026-05-18._

## Account creation (first boot)

The first-run flow (`/setup`) authenticates the registration request with one of three
mechanisms, checked in priority order:

1. **Legacy registration token** — obtained via `koda auth issue-code`, then
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
- issues **10 one-time recovery codes**, hashed before storage in
  `cp_operator_recovery_codes`, with a generation marker copied onto
  `cp_operator_users.recovery_generation`
- opens a session
- returns the plaintext codes **once only** in the HTTP response

The web UI shows the codes on the second setup screen, requires an acknowledgement checkbox
("I saved my codes"), and never retrieves them again.

Successful owner registration does not seed product data. A fresh control plane starts with no
agents, workspaces, squads, provider connection rows, MCP catalog rows, or global settings rows;
operators create those records explicitly after login.

## Backend enforcement (no dev/open bypass)

The control-plane backend (`koda/control_plane/api.py`, bound to `127.0.0.1:8090`) enforces an
operator-session bearer token on every `/api/control-plane/*` request via
`control_plane_auth_middleware`. Requests must carry `Authorization: Bearer <token>`; the
token is resolved by `OperatorAuthService.resolve_bearer_token`, which accepts session tokens
(`cp_operator_sessions`) and the break-glass `CONTROL_PLANE_API_TOKEN(S)`. Anything else
returns `401`.

Unedited `.env.example` placeholders (values starting with `replace-with-`) never
authenticate: they are dropped from `CONTROL_PLANE_API_TOKEN(S)` and treated as an unset
`RUNTIME_LOCAL_UI_TOKEN`, and the supervisor logs `control_plane_api_token_placeholder_ignored`
/ `runtime_local_ui_token_placeholder_ignored` at startup. The web app likewise treats a
placeholder `WEB_OPERATOR_SESSION_SECRET` as unconfigured and refuses to seal sessions in
production; the login and owner-registration routes check this before contacting the control
plane, so a misconfigured dashboard never consumes a setup code or recovery codes. The packaged
installer generates random values; manual installs use `scripts/generate_env_secrets.py`
(see `docs/install/local.md`, including the upgrade path for existing installs).

Postgres and object-storage placeholders (`POSTGRES_PASSWORD`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`) are different: the bundled services were set up with them, so they still
authenticate and Koda still starts. The supervisor logs `storage_secret_placeholder_in_use` (key
names only) at every start, `scripts/doctor.py` fails, and the dashboard shell shows a persistent
banner. The banner reads `GET /api/control-plane/system-settings/placeholder-secrets`, an
operator-only route that returns key names and the rotation link, never values.

A small public whitelist bypasses the bearer check (these endpoints carry their own
credential or are required to bootstrap auth itself):

- `/api/control-plane/onboarding/status`
- `/api/control-plane/auth/status`
- `/api/control-plane/auth/bootstrap/exchange`
- `/api/control-plane/auth/login`
- `/api/control-plane/auth/register-owner`
- `/api/control-plane/auth/password/recover`

There is **no** development/open mode that disables the middleware. Any local process
(browser extension, neighbor container reaching `host.docker.internal`, ad-hoc script) that
talks directly to `127.0.0.1:8090` without a valid session will be rejected. The Next.js
proxy at `5174` is defence in depth, not the only line of defence: `apps/web/src/lib/control-plane.ts`
unseals the operator-session cookie and forwards the bearer token to the backend, so the
normal dashboard flow is unaffected.

## Session model

- Session secret: 32-byte URL-safe random, hashed with SHA-256 before persistence in
  `cp_operator_sessions`.
- TTL: `CONTROL_PLANE_OPERATOR_SESSION_TTL_SECONDS` (default: 7 days).
- Transport: session token is sealed into the `koda_operator_session` cookie with AES-256-GCM
  using `WEB_OPERATOR_SESSION_SECRET`. Cookie flags: `HttpOnly; Secure; SameSite=Strict`.
- Revocation: logout revokes the current session. Password _change_ revokes every other
  session for the same user and keeps the initiating session alive. Password _reset_ via
  recovery code revokes **all** sessions for the user.

## Profile data

The account page lets the authenticated operator update a display name and profile photo
without changing credentials:

- `PATCH /api/control-plane/auth/profile` updates `cp_operator_users.display_name`.
  The value is trimmed, whitespace-collapsed, required, capped at 80 characters, and
  rejected if it contains control characters.
- `POST /api/control-plane/auth/profile/photo` accepts multipart field `photo`. The
  backend caps input at 12 MiB, decodes the image with Pillow, applies EXIF orientation,
  center-crops to a square, resizes to at most 512 px, strips metadata, and stores a
  re-encoded JPEG under `${STATE_ROOT_DIR}/operator_profile_photos/{user_id}.jpg`.
- `GET /api/control-plane/auth/profile/photo?v=<hash>` returns the processed JPEG with
  immutable cache headers and an `ETag`.
- `DELETE /api/control-plane/auth/profile/photo` removes the stored file and clears the
  hash fields on the operator row.

Profile changes require a valid operator session but do not require the current password.
They are treated as low-risk profile preferences; credential and recovery-code changes keep
their stronger password checks.

## Recovery code lifecycle

- Codes are 12 uppercase characters (`XXXX-XXXX-XXXX`) from the `BOOTSTRAP_ALPHABET`
  (no `I`, `O`, `0`, `1`).
- Codes are stored as a SHA-256 hash of that canonical `XXXX-XXXX-XXXX` form. The control
  plane is the authority on matching: before hashing a submitted code it keeps only the
  ASCII letters and digits (whitespace, separators and any non-ASCII character are
  dropped, not case-folded), upper-cases them, and regroups them in fours
  (`_normalize_recovery_code` in `koda/control_plane/operator_auth.py`).
  `abcd efgh jklm`, `ABCDEFGHJKLM` and ` abcd-efgh-jklm ` all match the issued
  `ABCD-EFGH-JKLM`; a code with a missing, wrong or non-ASCII look-alike character (for
  example `ſ` in place of `S`) still fails with the generic error. The `/forgot-password`
  screen shows the field in uppercase and submits it upper-cased so the input matches the
  printed code, but correctness does not depend on the client.
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

Per client address, enforced in `koda/control_plane/rate_limit.py`:

| Endpoint                                            | Budget               |
| --------------------------------------------------- | -------------------- |
| `POST /auth/login`                                  | 10 requests / 5 min  |
| `POST /auth/password/recover`                       | 10 requests / hour   |
| `POST /auth/password/change`                        | 20 requests / hour   |
| `PATCH /auth/profile`                               | 60 requests / hour   |
| `POST /auth/register-owner`                         | 30 requests / hour   |
| `POST /auth/recovery-codes/regenerate`              | 10 requests / hour   |
| `POST /auth/bootstrap/exchange`                     | 30 requests / hour   |
| `POST /auth/bootstrap/codes`                        | 10 requests / hour   |

Plus the per-address general bucket (`CONTROL_PLANE_RATE_LIMIT`, default 120/min) and
the stricter auth-failure bucket (`CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT`, default 5/min
triggered on any 401/403). An exhausted bucket returns `429` with `Retry-After`.

### Which address a request is charged to

- By default a request is charged to its TCP peer. `X-Forwarded-For` is read only when the
  peer is a trusted proxy (`CONTROL_PLANE_TRUSTED_PROXIES`: loopback by default, where a
  native dashboard runs; Docker Compose sets `web`, the dashboard's service, matched by its
  resolved address). The header is then read from the right, skipping trusted hops, and the
  first untrusted address is the client. Entries further left are client-supplied and never
  select a bucket, so a direct caller cannot rotate the header to get a fresh budget.
- The dashboard server decides the browser's address before Next.js runs
  (`apps/web/server.mjs`, `apps/web/src/lib/forwarded-for.mjs`). Next.js only fills an
  *absent* `X-Forwarded-For`, so the server replaces the header on every request with one
  address: the TCP peer, or, when the peer is a trusted proxy (loopback, plus
  `WEB_TRUSTED_PROXIES`, which Compose sets to `gateway`), the first untrusted hop from the
  right. A client that reaches the dashboard port directly is charged to its own address
  whatever header it sends.
- The dashboard BFF forwards that address on every control-plane call
  (`apps/web/src/lib/client-ip.ts`). Each browser therefore has its own budget; one client's
  failed logins do not lock other clients out. The Next.js proxy (`apps/web/src/proxy.ts`)
  keys its own per-client window (120/min) the same way.
- IPv6 clients are charged per /64, both in the API and in the dashboard, so rotating source
  addresses inside one subscriber's block does not buy a fresh budget. Each sensitive
  endpoint keeps its own bucket cache (4096 clients), so cycling through many addresses on
  one endpoint does not evict buckets on another.
- Exception: `POST /auth/register-owner` from a browser on loopback is forwarded without
  `X-Forwarded-For`, because the dev-only loopback trust requires a request with no proxy
  hop. Requests from any other browser carry its address like every other auth call.
- `gateway` (in either setting) is the container's IPv4 default gateway, which is where
  Docker's port proxy connects from: a reverse proxy on the Docker host reaches the
  dashboard, and the API, from that address. A reverse proxy that forwards
  `/api/control-plane/*` straight to the API, such as the bundled `proxy/nginx.conf`, needs
  `CONTROL_PLANE_TRUSTED_PROXIES=web,gateway`; until then all of its clients share one
  bucket. A proxy on another host (`WEB_PUBLISH_ADDRESS`) is trusted by its IP:
  `WEB_TRUSTED_PROXIES=gateway,203.0.113.5`.
- Trust only peers you control: a trusted peer can claim any client address. Docker hides
  the real client behind the gateway whenever its userland proxy carries the connection
  (Docker Desktop, rootless Docker, or an IPv6 host address on an IPv4-only network), so
  when the dashboard is published beyond loopback (`WEB_PUBLISH_ADDRESS`), firewall its port
  so only your proxy can reach it.
- The API trusts `web` by the address Docker DNS returns for it, which must be the address
  the dashboard connects from. In the source `docker-compose.yml` both containers share two
  networks; `scripts/docker_smoke.sh` checks that the two addresses match. If they ever
  differ, every browser falls back to one shared bucket (the safe direction).

Account-level lockout remains on top of the rate limits: after
`CONTROL_PLANE_OPERATOR_LOGIN_MAX_FAILURES` failed attempts, the row locks for
`CONTROL_PLANE_OPERATOR_LOGIN_LOCKOUT_SECONDS`. This lockout is per account, not per client,
so anyone who knows the identifier can still trigger it; the per-client buckets only stop one
client from spending everyone else's budget.

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
| `security.operator_profile_updated`                 | Display name changed                                         |
| `security.operator_profile_photo_updated`           | Profile photo uploaded/replaced                              |
| `security.operator_profile_photo_deleted`           | Profile photo removed                                        |
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
