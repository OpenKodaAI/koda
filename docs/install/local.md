# Local Install

Use this path when you want Koda running on your machine with the same core topology used by the VPS deployment.

## Prerequisites

- Docker and Docker Compose
- Node.js with npm for the packaged CLI path
- A repository clone only if you are contributing from source

## Quickstart

```bash
npm install -g @openkodaai/koda
koda install
```

Without a global install:

```bash
npx @openkodaai/koda@latest install
```

From a source clone on apt-based Linux hosts:

```bash
git clone <your-fork-or-repo-url> ./koda
cd ./koda
./scripts/install.sh
```

The installer verifies prerequisites, stages the product bundle, creates `.env` if needed, starts Docker Compose, runs doctor checks, and prints the setup URL plus a short-lived setup code.

## What Starts

```text
web :3000
app :8090
postgres
seaweedfs + seaweedfs-init
security + memory + artifact + retrieval + runtime-kernel
```

Optional overlays:

| Need | Enable |
|---|---|
| Telegram fan-in for many agents | `docker compose --profile bot-gateway up -d` |
| Workspace quotas | `docker compose --profile policy-engine up -d` |
| Multi-supervisor cluster | `docker compose -f docker-compose.yml -f docker-compose-cluster.yml up -d` |
| Prometheus/Grafana/Tempo | `docker compose -f docker-compose.yml -f docker-compose-observability.yml up -d` |

## First Boot

Open:

```text
http://127.0.0.1:3000/setup
```

Then:

1. Paste the setup code printed by the installer.
2. Create the owner account.
3. Save the ten one-time recovery codes.
4. Sign in to the dashboard.

The setup code is stored inside the app container at `${STATE_ROOT_DIR}/control_plane/bootstrap.txt`, mode `0600`, and is deleted after the owner is registered. If it expires, run:

```bash
koda auth issue-code
```

## Configure From The Dashboard

After login, use the dashboard to:

- connect providers
- create agents
- attach integrations and secrets
- publish runtime configuration
- inspect health, activity, costs, executions, sessions, memory, and routines

The quickstart path does not require per-agent env configuration. Product configuration lives in the control-plane UI and API after the platform boots.

`CONTROL_PLANE_API_TOKEN` is a break-glass and CLI credential. Browser auth uses owner login and HTTP-only sessions.

The dashboard (`http://localhost:3000`) and the control-plane API (`http://localhost:8090`) are
published on loopback only. To reach the dashboard from another machine, serve it over HTTPS with a
reverse proxy or `tailscale serve` (see `docs/install/vps.md`); plain-HTTP access from another
machine does not work because operator session cookies are `Secure`.

## Demo Data For Screenshots

```bash
docker compose exec app python scripts/seed_demo_data.py --apply
python3 scripts/capture_docs_screenshots.py \
  --base-url http://127.0.0.1:3000 \
  --out docs/assets/screenshots
```

Clear only demo data:

```bash
docker compose exec app python scripts/seed_demo_data.py --clear
```

## Doctor

```bash
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

The doctor validates bootstrap files, secrets, storage, control-plane reachability, and dashboard reachability.
It fails while `POSTGRES_PASSWORD` or an `S3_*` secret is still a `replace-with-...` placeholder and prints
the rotation command (see [Rotating placeholder Postgres and object-storage
secrets](#rotating-placeholder-postgres-and-object-storage-secrets)).

It reads the storage settings the way Koda receives them. Under Docker Compose the `.env` holds
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` and `S3_*`, and Compose builds the app's Postgres DSN
and object-storage keys from them. A native install sets `KNOWLEDGE_V2_POSTGRES_DSN` and
`KNOWLEDGE_V2_S3_*` itself; when `.env` sets `KNOWLEDGE_V2_POSTGRES_DSN`, doctor uses it.
Compose does not publish Postgres or SeaweedFS on the host. For a Compose `.env`, when this host cannot
resolve their service names (`postgres`, `seaweedfs`), doctor opens the connection from the app container
with `docker compose exec app`, in the Compose project of the `--env-file` directory. For a project started
with `-p`, set `COMPOSE_PROJECT_NAME`. A native install's app connects from this host, so a `.env` that sets
`KNOWLEDGE_V2_POSTGRES_DSN` is always probed from here: an endpoint left at a Compose service name, such
as the `.env.example` value `KNOWLEDGE_V2_S3_ENDPOINT_URL=http://seaweedfs:8333`, fails the check even
while a Compose stack runs from the same checkout.
When Compose cannot parse the `.env` (an unterminated quote, or a `${` that Compose cannot read as a
variable), its error repeats the offending value, so doctor reports only that the file could not be
parsed. Run `docker compose --env-file .env config -q` to see where. A bare `$NAME` in a value is not a
parse error, and doctor does not report it: Compose replaces it with that variable, or with an empty
string and only a warning, so `POSTGRES_PASSWORD=P@ss$word` reaches the stack as `P@ss`. Keep `$` out
of hand-set secrets; `scripts/generate_env_secrets.py` writes hex values, which never contain one.
Doctor connects to the control plane and the dashboard directly and ignores `http_proxy`, `https_proxy`
and `no_proxy`, so the break-glass token that `--provider` sends never passes through a proxy. It sends
that token only to the `--base-url` it was given: when that request answers a redirect, doctor does not
follow it, and `provider_verification` fails and names the redirect target. Point `--base-url` at the
control plane itself, not at an address that redirects to a sign-in page.
With `OBJECT_STORAGE_REQUIRED=false`, the object-storage checks are still reported, marked
`"required": false`, and do not fail doctor. An unset value means `true`. An empty value means `true`
under Compose (`${OBJECT_STORAGE_REQUIRED:-true}`) and `false` on a native install, as Koda reads its own
`.env`; doctor reads a `.env` that sets `KNOWLEDGE_V2_POSTGRES_DSN` as a native install's.

Doctor itself needs only the Python standard library. Its sandbox check imports Koda. Under a `python3` that
is not Koda's environment, such as the system Python, the check is `skipped`: doctor still passes, and
`--strict` fails. Koda's environment is an interpreter that has Koda installed, or that runs from the
checkout's `.venv` or from the environment that `VIRTUAL_ENV` or `UV_PROJECT_ENVIRONMENT` names. There, a
missing dependency is a broken install: the check is `unavailable` and doctor fails. To include the
sandbox check, run doctor with Koda's environment from the source checkout:
`uv run python scripts/doctor.py --env-file .env`.

During a token rotation (`CONTROL_PLANE_API_TOKEN=new-token,old-token`), doctor's token check passes while
one token of the list is not a placeholder, and `--provider` authenticates with the first such token.

## Manual Startup

Every `replace-with-...` value in `.env.example` must become a random secret before the first
start. Koda never authenticates with an unedited placeholder: break-glass and runtime tokens stay
disabled and the dashboard refuses to start sessions until real values are set.
`scripts/generate_env_secrets.py` creates `.env` from `.env.example` (mode `0600`) when it does
not exist and fills every placeholder. On an existing `.env` it only fills the authentication
placeholders and never changes values that were already customised, so it is safe to re-run.

```bash
python3 scripts/generate_env_secrets.py
docker compose up -d --build
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

### Upgrading a manual install that still has placeholders

Older manual installs may still carry `replace-with-...` values. Running the generator on an
existing `.env` replaces only the authentication placeholders; then restart:

```bash
python3 scripts/generate_env_secrets.py
docker compose up -d
```

This rotates `CONTROL_PLANE_API_TOKEN`, `RUNTIME_LOCAL_UI_TOKEN` and `WEB_OPERATOR_SESSION_SECRET`
(dashboard users sign in again). `POSTGRES_PASSWORD` and the `S3_*` values must keep matching the
data already on disk, so they are rotated separately, as described next.

### Rotating placeholder Postgres and object-storage secrets

Placeholder values for `POSTGRES_PASSWORD`, `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` still
work, because the bundled Postgres and SeaweedFS were set up with them. Anyone who can reach those
services can use the public values. Until you rotate them, Koda still starts, but:

- the control plane logs `storage_secret_placeholder_in_use` (key names only) at every start;
- the doctor fails its `storage_secrets_not_placeholders` check;
- the dashboard shows a warning banner that links to this section.

Before the first start, when Postgres has no data yet, generate every value at once:

```bash
python3 scripts/generate_env_secrets.py --all
```

On an install that has already started, Postgres keeps the password it was first started with, so
set the new password inside Postgres before you restart. The commands below use the default
`POSTGRES_USER` and `POSTGRES_DB` (`koda`); use your own values if you changed them.

```bash
python3 scripts/generate_env_secrets.py --all   # writes the new values to .env only
NEW_POSTGRES_PASSWORD="$(sed -n 's/^POSTGRES_PASSWORD=//p' .env)"
docker compose exec -T postgres \
  psql -U koda -d koda -c "ALTER USER koda PASSWORD '${NEW_POSTGRES_PASSWORD}'"
docker compose up -d
python3 scripts/doctor.py \
  --env-file .env \
  --base-url http://127.0.0.1:8090 \
  --dashboard-url http://127.0.0.1:3000
```

If the `ALTER USER` command fails, do not restart: the app would no longer reach Postgres. Fix the
command and run it again first. The bundled SeaweedFS reads the `S3_*` values from its environment
when its container starts, so `docker compose up -d` applies them and keeps the stored objects.
With an external S3-compatible store, create the new keys there and put them in `.env` instead.

## Troubleshooting

- Dashboard unavailable: check `docker compose ps web`.
- API unavailable: check `docker compose ps app`.
- Degraded `/health`: inspect worker and sidecar status in the JSON payload.
- Object storage errors: check `seaweedfs` and `seaweedfs-init`.
- The dashboard shows "HTTPS required", or sign-in does not stick: session cookies are `Secure`,
  so a browser keeps them only over HTTPS or on a localhost address. Opening
  `http://<host-ip>:3000` from another machine cannot keep a session, and `/login`, `/setup` and
  `/forgot-password` say so instead of showing their forms. Put a TLS-terminating reverse proxy
  in front (see [VPS install](vps.md)), or reach the dashboard through an SSH tunnel
  (`ssh -L 3000:127.0.0.1:3000 <host>`, then open `http://localhost:3000`). See
  [Authentication](../security/authentication.md#plain-http).
- Signed out after every restart: `WEB_OPERATOR_SESSION_SECRET` changed; keep it stable in `.env`.
- Runtime worker spawn failures: rebuild `runtime-kernel`; it must contain the Python runtime and shared Koda volumes.
- `koda install` aborts with `Detected pre-existing Docker volumes ... but no .env`: a
  previous install left its volumes behind without its `.env` (typical after deleting
  `~/.koda` by hand; `koda uninstall` keeps both, `koda uninstall --purge` removes
  both). The auto-generated random
  Postgres password will not match the volume on disk. Either restore the matching
  `.env` into the install dir, or run `koda install --reset-volumes` to wipe the
  managed volumes and start clean.
- `koda install` fails after `up -d` with `Postgres rejected the credentials`: same
  root cause as above, surfaced after the stack started. Use the same recovery
  steps.

## Local-Native PID Files

The Docker-free development path writes PID files to `~/.koda-local/var/run/<service>.pid`.

```text
PID file + live process  -> service is running
PID file + dead process  -> remove stale file before restart
```

Use the restart helper to clear stale PID files and data-directory locks:

```bash
~/.koda-local/scripts/dev-down.sh
scripts/dev/dev-restart.sh
```
