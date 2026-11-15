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
2. **Bootstrap code (recommended for VPS)** — while no owner exists, the control plane writes
   `${STATE_ROOT_DIR}/control_plane/bootstrap.txt` (mode `0600`) at the first auth or onboarding
   status request (the setup screen and the CLI make one right away), and prints a generated code
   once, in a banner on stderr, which is part of the container log (never a
   `CONTROL_PLANE_BOOTSTRAP_CODE` seed, and never in the structured log). The operator SSHs in,
   reads the file or the banner, pastes the code into `/setup`, and the file is deleted after
   registration. The code expires `CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS` (default 900, so
   15 minutes) after the file is written. The next status request after that, such as reloading
   `/setup`, replaces the expired file with a new code and a new banner (a seed is written again,
   with a fresh expiry). A file without both a code line and a readable `expires_at`, such as an
   empty one left by a crash or one that is not UTF-8, never matches and is replaced the same way,
   so an expired or damaged file does not lock setup. The code is the file's first line, whatever
   it holds (a seed may contain `=` or any other separator), and `expires_at` is read from the
   lines after it. The file is published whole: the content goes to a `0600` temp file in the same
   directory, is fsynced, then is hard-linked to `bootstrap.txt`, which fails when that file already
   exists. Writers read, check, replace and publish the file under an `flock` on `.bootstrap.lock`
   beside it, so when replicas race at expiry one replaces the file and the others keep it. Another
   replica never reads a half-written file, a code is announced only when its file is the one on
   disk, and a write that fails leaves no file. An install with an owner never writes the file.
3. **Loopback trust (dev only)** — when `ALLOW_LOOPBACK_BOOTSTRAP=true` and the request comes
   from `127.0.0.1` / `::1` with no `X-Forwarded-For` hop, no code is required. This mode is
   refused at boot when `KODA_ENV=production`.

Setup codes are matched in the same canonical form as recovery codes (see
[Recovery code lifecycle](#recovery-code-lifecycle)), on both sides: the stored code (the hash
of a `koda auth issue-code` code, the code in `bootstrap.txt`, or a `CONTROL_PLANE_BOOTSTRAP_CODE`
seed) and the code the operator types are reduced to their ASCII letters and digits,
upper-cased and regrouped in fours (`_normalize_bootstrap_code` in
`koda/control_plane/operator_auth.py`). `abcd efgh jklm`, `ABCDEFGHJKLM` and
` abcd-efgh-jklm ` all register the owner with the issued `ABCD-EFGH-JKLM`, through
`POST /api/control-plane/auth/register-owner` and `POST /api/control-plane/auth/bootstrap/exchange`
alike. Every other character is ignored: whitespace, separators of any kind (an en dash, a
trailing non-breaking space) and any other non-ASCII character, so `ABCD-EFGH-JKLMé` matches
too. A missing, wrong or extra letter or digit, or a non-ASCII look-alike typed in place of one
(for example `ſ` in place of `S`), fails with the same generic `Setup code is invalid or expired.`
The `/setup` screen's code field takes at most 12 characters, from
`ABCDEFGHJKLMNPQRSTUVWXYZ23456789` only (no `I`, `O`, `0` or `1`), the alphabet of generated codes:
it drops any other character as it is typed and submits the dashed, uppercase form.

The same rule applies to a `CONTROL_PLANE_BOOTSTRAP_CODE` seed: only its ASCII letters and digits
count towards its strength. `Hunter2!!` is matched as `HUNT-ER2` (7 letters and digits), and
`!!!!a!!!!` is matched by a typed `a`. A seed meant to be typed on `/setup` should therefore be
exactly 12 characters from that alphabet, separators aside (fewer is weaker than a generated code):
`Wb7k-Qz3m-Np4x` is typed and matched as `WB7K-QZ3M-NP4X`. A seed with more letters and digits, or with `I`, `O`, `0` or `1`, can only be sent
to the API (`POST /api/control-plane/auth/register-owner`): the `/setup` field would submit fewer
characters than the seed has, and the code would not match. When the control plane writes
`bootstrap.txt`, it prints a generated code once, in a banner on stderr, never a seed. The
structured log never carries the code: its `bootstrap_file_written` event names
`code_source=generated` or `code_source=CONTROL_PLANE_BOOTSTRAP_CODE` instead, as the operator
chose a seed. From a seed it also logs a `bootstrap_code_seed_weak` warning when the seed
has fewer than 12 ASCII letters and digits (a generated code has 12) and a
`bootstrap_code_seed_not_typeable` warning when the `/setup` field cannot take it, neither with the
seed; a seed with no ASCII letter or digit never matches.

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

The user row, the recovery codes, the session and the consumption of the setup code (or of
the registration token) are written in one database transaction. If any of these writes
fails, none of them is kept: there is never an owner without recovery codes, and what the
failed registration presented can be used again. With a bootstrap code, that is the same
setup code. With a legacy registration token, it is the same registration token, not the
setup code: `POST /api/control-plane/auth/bootstrap/exchange` already consumed the setup
code, so a retry with it fails with `Setup code is invalid or expired.`
`bootstrap.txt` is deleted only after the transaction commits.

A setup code or registration token is consumed only while it is still unused: the
transaction's first write marks it consumed on that condition, and a write that matches no
row rolls the whole transaction back. Two registrations sent at once with the same code
therefore create one owner. The other request waits for the first to commit, writes nothing,
and gets the answer of any other invalid code: `Setup code is invalid or expired.`, or
`Registration token is invalid or expired.` for a token. That request has already hashed its
password, so a registration with an invalid setup code or token hashes the submitted password
too before it answers: the two answer in about the same time, the loser later only by the
wait for the winner's commit. The setup routes have no timing floor.
`POST /api/control-plane/auth/bootstrap/exchange` consumes the setup code on the same
condition, so of two exchanges sent at once with one code, one gets a registration token and
the other `Setup code is invalid or expired.`

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

During a rotation, `CONTROL_PLANE_API_TOKEN` holds a comma-separated list (`new-token,old-token`)
and each token in it authenticates on its own. `koda auth issue-code` (and `koda install`, which
calls it) sends the first token of that list that is not a placeholder, never the whole list.
`scripts/doctor.py --provider` does the same, its `control_plane_api_token` check passes while one
such token remains, and `--strict` requires every such token to be at least 32 characters. Doctor
sends that token straight to the control plane and ignores `http_proxy` and `https_proxy`, so a
proxy never sees it, and it never follows a redirect with it: a `3xx` from `--base-url` fails the
provider check instead of carrying the token to the host the redirect names. It sends the token over
plain HTTP only to loopback (`127.0.0.0/8`, `[::1]`, `localhost`), where the CLI sends it; a plain-HTTP
`--base-url` on another host fails the provider check before any connection carries the token. Use
an SSH tunnel or an `https://` URL from another machine.

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

- `/api/control-plane/onboarding/status` (two fields before login, see below)
- `/api/control-plane/auth/status`
- `/api/control-plane/auth/bootstrap/exchange`
- `/api/control-plane/auth/login`
- `/api/control-plane/auth/register-owner`
- `/api/control-plane/auth/password/recover`

Paths match exactly, in the backend and in the dashboard. A trailing slash or a route added
under one of these paths (`/api/control-plane/auth/login/...`) still needs a session. The
backend also checks the route the request resolved to: it skips the bearer check only when the
router matched one of these routes itself, with the method it is registered for (`GET` and
`HEAD` for the two status routes, `POST` for the others). So a route added later cannot take
over a public path. A `GET /api/control-plane/auth/login` that a new `/auth/{name}` pattern would
answer needs a session, and so does an encoded slash (`auth%2Fstatus`) that resolves to another
route. `tests/test_control_plane_public_paths.py` checks the methods against the registered
routes.

The dashboard uses the same list. `apps/web/src/lib/public-control-plane-paths.ts` is read by
both the Next.js proxy (`apps/web/src/proxy.ts`) and the catch-all BFF route, and
`tests/test_control_plane_public_paths.py` fails when it differs from the backend list or when
the OpenAPI stops marking one of these routes as callable without a token. Every other
control-plane route, including `/api/control-plane/onboarding/readiness`, needs an operator
session in the dashboard as well as in the backend.

There is **no** development/open mode that disables the middleware. Any local process
(browser extension, neighbor container reaching `host.docker.internal`, ad-hoc script) that
talks directly to `127.0.0.1:8090` without a valid session will be rejected. The Next.js
proxy at `5174` is defence in depth, not the only line of defence: `apps/web/src/lib/control-plane.ts`
unseals the operator-session cookie and forwards the bearer token to the backend, so the
normal dashboard flow is unaffected.

Outside `/api/control-plane/*` the middleware checks only the two cluster-mode deploy hooks that
change state, `POST /cluster/drain` and `POST /cluster/undrain`
([Cluster mode](../operations/cluster-mode.md)), with the same bearer check: without a valid
token they answer `401` and change nothing. The supervisor's other routes (`/`, `/setup`,
`/health`, `/openapi/control-plane.json` and `GET /cluster/status`) answer without a
session. `tests/test_control_plane_auth_matrix.py` sends a request to every route the supervisor
registers, through its own middleware stack, without a session and with one. It fails when a
route answers without a session and the OpenAPI document does not let that operation through
without a token. It also fails when the routes that answer without a session differ, by path or
method, from the public routes listed above or from the dashboard list. Outside
`/api/control-plane/` it pins the supervisor routes listed here (`ANONYMOUS_ROOT_ROUTES` in the
test, with their `HEAD` twins): a new route there that answers without a session fails the test,
even when the OpenAPI document marks it `security: []`, until it is added to that set. It sends
other spellings of each public path (a sub-path, a trailing slash, another case or method, dot
segments, encoded slashes) and routes added under or next to one, and fails if any of them
reaches a handler without a session.

### Onboarding status before login

`GET /api/control-plane/onboarding/status` is polled before anyone can log in: by the CLI
(`koda doctor`, `koda auth issue-code`) and by `scripts/doctor.py`. Without a valid operator
credential it answers only whether setup is still needed:

```json
{"has_owner": true, "bootstrap_required": false}
```

With a valid session token, personal API token or break-glass token it returns the full status:
agents, owner name, email and GitHub, the Telegram allowlist, provider connection state, storage
health, the bootstrap file path and the remaining auth flags. An unknown, expired or revoked
token gets the two-field answer. Either way the call writes the first-run setup-code file when no
owner exists yet.

When the status cannot be computed, the route still answers `200` so pollers can retry. Before
login that answer is `{"status": "degraded", "error": "onboarding_status_failed"}`, with no
exception text; operators get the degraded status payload with the error message. Through the
dashboard, a caller without a session gets the same two fields, or a plain `503` when the
control plane is unreachable: the dashboard's empty "upstream unavailable" stand-in payloads are
served only to signed-in operators.

### Auth status before login

`GET /api/control-plane/auth/status` is public as well, on `:8090` and through the dashboard:
the login and setup screens read it before anyone has a session. Without a valid operator
credential it returns `has_owner`, `bootstrap_required`, `auth_mode`, `session_required`,
`onboarding_complete` and `authenticated: false`, plus two fields that only apply while no owner
exists:

- `bootstrap_file_path`, the absolute path of the setup-code file on the server. The setup
  screen tells the operator to read the code from it, and `koda doctor` and `scripts/doctor.py`
  report it from this route, because onboarding/status no longer does before login.
- `loopback_trust_enabled`, which tells the setup screen whether a loopback request needs no
  code.

So until the owner registers, anyone who can reach the control plane learns where the setup-code
file is, though not the code. Once an owner exists the file is deleted and anonymous callers get
neither field. `recovery_available` (whether a break-glass token is configured) is returned only
to an operator. With a valid session, personal API token or break-glass token the route returns
every field and the operator's profile.

## Session model

- Session secret: 32-byte URL-safe random, hashed with SHA-256 before persistence in
  `cp_operator_sessions`.
- TTL: `CONTROL_PLANE_OPERATOR_SESSION_TTL_SECONDS` (default: 7 days).
- Transport: session token is sealed into the `koda_operator_session` cookie with AES-256-GCM
  using `WEB_OPERATOR_SESSION_SECRET`. Cookie flags: `HttpOnly; Secure; SameSite=Strict`.
  The dashboard's production build always sets `Secure` on its cookies; there is no switch
  for it (`ALLOW_INSECURE_COOKIES` only works in development). See
  [Plain HTTP](#plain-http) for what happens when the browser cannot keep them.
- Runtime relays: the terminal, browser-snapshot and noVNC WebSockets at
  `/api/runtime/relay/<id>` read the same cookie on the upgrade, before the handshake
  (`apps/web/src/lib/runtime-relay-server.mjs`). A relay admits only the session that attached
  it, and the token is never taken from the URL. The upgrade's `Origin` must also match the
  `Host` header and `X-Forwarded-Proto` (403 otherwise): the `SameSite=Strict` cookie still
  reaches a page on another origin of the same site. This is stricter than the check on other
  changes (`apps/web/src/lib/request-origin.ts`), which also admits a matching `Referer` or
  `Sec-Fetch-Site: same-origin` when the `Origin` does not match: a browser always sends `Origin`
  with a WebSocket handshake, so the relay takes nothing else.
- Revocation: logout revokes the current session. Password _change_ revokes every other
  session for the same user and keeps the initiating session alive; the new password and the
  revocation are one database transaction, so if either write fails the password and the
  sessions stay as they were. Password _reset_ via recovery code revokes **all** sessions for
  the user.

### Plain HTTP

A browser keeps a `Secure` cookie only on a secure context: an `https://` page, or a loopback
host (`localhost`, `*.localhost`, `127.0.0.0/8`, `[::1]`). Over plain HTTP from any other
address, such as `http://192.168.1.10:3000` on a LAN or a tailnet IP, it drops the session
cookie without an error, so a sign-in the control plane accepted would leave no session. The
dashboard therefore fails explicitly there instead of bouncing the operator back to `/setup`:

- `/login`, `/setup` and `/forgot-password` show an "HTTPS required" screen in place of their
  forms, naming the address that was used and the two ways in: HTTPS through a reverse proxy,
  or a localhost address on the host (for example through an SSH tunnel). Any other page sends
  a signed-out visitor to `/login` once, not to `/setup`, because the owner hint cookie cannot
  be stored either.
- `POST /api/control-plane/auth/login`, `POST /api/control-plane/auth/register-owner` and
  `POST /api/control-plane/auth/password/recover` answer `403` with
  `error.code: "INSECURE_TRANSPORT"` before they contact the control plane. Owner
  registration therefore never spends the setup code or issues recovery codes for a session
  the browser would throw away. Recovery sets no cookie, but over plain HTTP it would send the
  recovery code and the new password across the network in clear text, consume the code,
  revoke every session, and still end on a `/login` that cannot sign in from that browser; it
  works over HTTPS and on a localhost address. The refusal depends only on the transport,
  never on the credentials, so the screens show their own message for it and every
  credential failure keeps the single generic message.
- The web container logs a `[cookie-transport]` warning naming the address (scheme, host and
  port), once per address per hour, for at most 32 addresses within an hour; each hour starts
  with the first warning after the previous one ended. The address comes from the request's
  `Origin`, `X-Forwarded-Host` or `Host` header, which any client can set, so one line per
  address keeps a scanner's made-up address from standing in for the operator's own unless 32
  of them arrive first. Past 32 addresses in that hour the rest are counted but not named: one
  line says so when the first of them arrives, and the first plain-HTTP request after the hour
  logs how many requests went unnamed. Those requests are refused like any other; only their
  address is left out of the log, so a stream of made-up hosts cannot flood it.

The dashboard decides from the request, and refuses only when it is sure: no refusal when the
request carries Fetch Metadata headers (`Sec-Fetch-Site`, `Sec-Fetch-Mode`), which only
browsers send and only to HTTPS and loopback pages, so they outrank an `Origin` that a proxy
rewrote to its plain-HTTP upstream; otherwise the browser's `Origin` header when it sent one;
otherwise the scheme and host from `X-Forwarded-Proto` and `X-Forwarded-Host` (or `Host`),
which Next.js fills from the socket when no proxy set them. A TLS-terminating proxy should
forward `X-Forwarded-Proto $scheme`, as the bundled `proxy/nginx.conf` does, which becomes
`https` once its server block terminates TLS; Caddy and Traefik send it by default. Without it
an older browser that sends no Fetch Metadata would be refused.

The refusal spares the operator a sign-in that cannot last; it is not access control. A
non-browser client on a plain-HTTP address that sets `Sec-Fetch-Site` itself is not refused,
and it gains nothing by it: it already holds the credentials it sends, and a page script cannot
set that header in a browser. Cross-site mutations are still blocked before this check.

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
  example `ſ` in place of `S`) still fails with the generic error, through the
  `/forgot-password` screen and direct API calls alike. The screen only displays the field
  in uppercase (CSS) so the input looks like the printed code; it submits the value
  trimmed but otherwise as typed, with no client-side case mapping, so the control plane
  is the only canonicalizer.
- Each code can be used exactly once, enforced by `consumed_at` and `generation` matching
  against `cp_operator_users.recovery_generation`.
- After a successful `POST /api/control-plane/auth/password/recover`:
  - the consumed code is marked `consumed_at = now`, `consumed_reason = "password_reset"`
  - **every other unused code** under the same generation is also marked consumed with
    `consumed_reason = "password_reset_invalidation"`
  - all sessions are revoked
  - the password hash is rotated

  These writes are one database transaction: if any of them fails, the password, the
  codes and the sessions all stay as they were, and the same code still works. Its first
  write is the password hash on the user row, so concurrent resets and regenerations of
  one account wait for each other on that row instead of deadlocking on each other's codes.
  Its second marks the code consumed only while it is still unused, and a write that
  matches no row rolls the transaction back, so of two resets sent at once with the same
  code, or with two codes of the same account, one sets its password and the other changes
  nothing and fails with the generic `Invalid identifier or recovery code.`
- The owner must regenerate a fresh batch from `/settings/account` › Security (calling
  `POST /api/control-plane/auth/recovery-codes/regenerate`, which requires the current
  password). Moving `cp_operator_users.recovery_generation` to a new batch, marking the
  current codes consumed (`consumed_reason = "regenerated"`) and storing the new batch are
  one database transaction, written in that order (the user row first, as in a reset): if
  any of these writes fails, the current codes stay usable and no new code is kept.

This mirrors Google and GitHub's policy: a printed sheet of codes is useful once, but once
one of them is compromised the whole sheet has to be rotated.

## Rate limits (bucket budgets)

Per client address, enforced in `koda/control_plane/rate_limit.py`. A bucket allows its
whole budget as a burst and frees capacity evenly over its window, so once a burst has used
it up, the next request is allowed after the window divided by the budget:

| Endpoint                               | Budget              | Wait after a burst |
| -------------------------------------- | ------------------- | ------------------ |
| `POST /auth/login`                     | 10 requests / 5 min | 30 s               |
| `POST /auth/password/recover`          | 10 requests / hour  | 6 min              |
| `POST /auth/password/change`           | 20 requests / hour  | 3 min              |
| `PATCH /auth/profile`                  | 60 requests / hour  | 1 min              |
| `POST /auth/register-owner`            | 30 requests / hour  | 2 min              |
| `POST /auth/recovery-codes/regenerate` | 10 requests / hour  | 6 min              |
| `POST /auth/bootstrap/exchange`        | 30 requests / hour  | 2 min              |
| `POST /auth/bootstrap/codes`           | 10 requests / hour  | 6 min              |

Plus the per-address general bucket (`CONTROL_PLANE_RATE_LIMIT`, default 120/min) and
the stricter auth-failure bucket (`CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT`, default 5/min
triggered on any 401/403). A value below 1 refuses every request that bucket covers, with
`Retry-After: 60`, and the control plane logs `control_plane_rate_limit_refuses_every_request`
at startup. An exhausted bucket returns `429` with `Retry-After` set to the
whole seconds, rounded up, until the bucket that refused the request takes the next one:
`Retry-After: 30` for login after a burst, `360` for recovery, `120` for setup. A bucket
does not draw from a request it refuses, so retrying early does not extend its wait. The
value follows only the client address's own requests, so it reveals nothing about an
account.

The dashboard's login, setup and recovery routes pass the `429` and its `Retry-After`
through (`apps/web/src/lib/auth-rate-limited-response.ts`), and the `/login`, `/setup` and
`/forgot-password` screens show a localized message with that wait, such as "Too many
attempts. Wait 6 minutes and try again." (ADR-038). These buckets count requests per client
address and answer the same way for existing and unknown accounts, so the message reveals
nothing about an account. The dashboard's own per-client window (`apps/web/src/proxy.ts`,
120 requests a minute) answers `429` with `Retry-After: 60`, the length of its window, and
the screens show the same message. The `/settings/account` screen and its password-change
and recovery-code routes do not show the wait yet.

### Which address a request is charged to

- By default a request is charged to its TCP peer. `X-Forwarded-For` is read only when the
  peer is a trusted proxy (`CONTROL_PLANE_TRUSTED_PROXIES`: loopback by default, where a
  native dashboard runs; Docker Compose sets `web`, the dashboard's service, matched by its
  resolved address). The header is then read from the right, skipping trusted hops, and the
  first untrusted address is the client. Entries further left are client-supplied and never
  select a bucket, so a direct caller cannot rotate the header to get a fresh budget.
- The dashboard server decides the browser's address before Next.js runs
  (`apps/web/server.mjs`, `apps/web/src/lib/dashboard-server.mjs`,
  `apps/web/src/lib/forwarded-for.mjs`). Next.js only fills an
  *absent* `X-Forwarded-For`, so the server replaces the header on every request with one
  address: the TCP peer, or, when the peer is a trusted proxy (loopback, plus
  `WEB_TRUSTED_PROXIES`, which Compose sets to `gateway`), the first untrusted hop from the
  right. A client that reaches the dashboard port directly is charged to its own address
  whatever header it sends.
- The dashboard BFF forwards that address on every control-plane call
  (`apps/web/src/lib/client-ip.ts`). Each browser therefore has its own budget; one client's
  failed logins do not lock other clients out. The Next.js proxy (`apps/web/src/proxy.ts`)
  keys its own per-client window (120/min) the same way; each of its windows tracks at most
  4096 clients and sweeps idle ones on its own schedule.
- IPv6 clients are charged per /64, both in the API and in the dashboard, so rotating source
  addresses inside one subscriber's block does not buy a fresh budget. Each sensitive
  endpoint keeps its own bucket cache (4096 clients), so cycling through many addresses on
  one endpoint does not evict buckets on another.
- Exception: `POST /auth/register-owner` from a browser on loopback is forwarded without
  `X-Forwarded-For`, because the dev-only loopback trust requires a request with no proxy
  hop. Requests from any other browser carry its address like every other auth call.
- `gateway` (in either setting) is the container's IPv4 default gateway, which is where
  Docker's port proxy connects from: a reverse proxy on the Docker host reaches the
  dashboard, and the API, from that address. Browser requests reach the API through the
  dashboard. A reverse proxy that forwards requests straight to the API, as the bundled
  `proxy/nginx.conf` does for API-token requests (`Authorization: Bearer`), needs
  `CONTROL_PLANE_TRUSTED_PROXIES=web,gateway`; until then all of those clients share one
  bucket. A proxy on another host (`WEB_PUBLISH_ADDRESS`) is trusted by its IP:
  `WEB_TRUSTED_PROXIES=gateway,203.0.113.5`. `WEB_TRUSTED_PROXIES` takes no hostnames, so a
  proxy container on the Compose network is trusted by a fixed `ipv4_address`
  ([VPS Install](../install/vps.md#reverse-proxy)).
- A trusted proxy must add the address it received the request from to `X-Forwarded-For`,
  appended or replacing the header: nginx
  `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` (or `$remote_addr`), as in the
  bundled `proxy/nginx.conf`; HAProxy `option forwardfor` (without `if-none`); Caddy and Traefik
  do it by default. The last entry is the one a trusted peer vouches for, so a proxy that passes
  the client's header through unchanged (nginx and HAProxy otherwise) lets each client name its
  own bucket, and clients that send no header all share one bucket.
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
client from spending everyone else's budget. A locked account is not a `429`: it answers
exactly like a wrong password, and the screens show the generic error, because a lockout
message would reveal that the account exists.

## Side-channel mitigations

- Planned, not yet in place (timing floor pending M1-E1-T13): every auth-failure path pads
  to a 300 ms floor (`_FAILURE_TIMING_FLOOR_SECONDS`) so the caller cannot distinguish
  `user not found` from `wrong password` from `invalid recovery code` by response time.
  Today the constant is `0.0` and nothing applies it: a login for an unknown identifier or a
  locked account fails before any password hash is checked, so it answers faster than a
  wrong password for an existing account.
- Responses use a single generic error (`"Invalid credentials."`, or equivalent) without
  leaking whether the identifier exists. The i18n layer binds every failure mode (wrong
  password, unknown user, locked account, invalid recovery code) to the same message in
  every language. Two answers get their own message, because neither depends on the account:
  the per-client `429`, which shows the wait since it is the same for every identifier (see
  [Rate limits](#rate-limits-bucket-budgets)), and the plain-HTTP refusal
  (`error.code: "INSECURE_TRANSPORT"`), which the dashboard decides from the transport before
  it reads any credential (see [Plain HTTP](#plain-http)).
- The control plane (`python -m koda.control_plane`) configures the structured logging pipeline
  (`setup_logging` in `koda/logging_config.py`) before anything logs; the agent workers configure
  it at startup. `LOG_FORMAT=json` writes one JSON object per line on stdout; any other value
  writes console lines. The pipeline replaces with `***` the value of these top-level event keys,
  in any case: `password`, `new_password`, `current_password`, `recovery_code`, `session_token`,
  `registration_token`, `bootstrap_code`, `code`, `totp_secret`, `api_key`, `apikey`, `secret`,
  `private_key`, `token`, `authorization` and `cookie`. It does not look inside nested values, and
  records from the standard `logging` module, such as third-party libraries', are formatted (with
  the same `level`, `logger` and `timestamp` keys) but not redacted. Both formats print an
  exception's plain traceback, its type, message and stack, without local variables: a console
  line prints it below the event, and a JSON line carries it as a string in its `exception` key.
  In the control plane, aiohttp's access log stays off, because its request lines carry query
  strings such as the authorization code of an MCP OAuth callback.

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
