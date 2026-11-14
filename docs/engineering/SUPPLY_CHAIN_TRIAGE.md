# Supply-chain advisory triage

Task M0-E4-T1 ([MASTER_PLAN.md](MASTER_PLAN.md)) · Owner SEC · 2026-11-14 · Addresses R-03 ([REMAINING_RISKS.md](REMAINING_RISKS.md)) · Feeds M1-E7-T2 (Python), M1-E7-T3 (Node), M1-E7-T4 (Rust)

Every critical and high finding in the locally collected audit data has a disposition below. The Dependabot alert list itself could not be exported, so the counts in §1.3 are compared, not reconciled.

## 1. Scope and method

### 1.1 Data sources

All raw data was collected on 2026-11-14 (UTC) into the session scratchpad and treated as untrusted data. None of it is committed.

| Ecosystem | Input | Command (as recorded) | Advisory data | Collected (UTC) |
|---|---|---|---|---|
| Python | `uv.lock` (150 resolved packages) | `uv export --locked --no-hashes --all-extras --format requirements-txt -o requirements-all.txt`, then `pip-audit` with `--no-deps` on that file, with JSON output in `pip-audit-all.json`. The export has no `--no-dev`, so it also contains the default `dev` group. The full `pip-audit` argv was not logged; its log shows `--no-deps` and "Found 206 known vulnerabilities in 14 packages". A second export, `uv export --locked --no-hashes --no-dev --format requirements-txt -o requirements-runtime.txt`, was used only for `# via` dependency paths. | pip-audit results. GHSA severity and ranges come from a local clone of github/advisory-database at `21efe5e` (2026-11-14T00:37Z). | 06:32 |
| Node | root `pnpm-lock.yaml` (workspace: `apps/web`, `packages/cli`, root) | `pnpm audit` (full) to `pnpm-audit.json` (93 advisory records: 5 critical, 41 high, 39 moderate, 8 low), and `pnpm audit --prod` to `pnpm-audit-prod.json` (36 records: 5 critical, 17 high, 12 moderate, 2 low). Both are JSON output with empty stderr. Only the output files were preserved, not the argv. | The npm advisory records embedded in the pnpm output. | 06:31 |
| Rust | `rust/Cargo.lock` and `rust/koda-command-guard/Cargo.lock` | `cargo-audit` is not installed in this environment. A local semver matcher compared every RustSec advisory against both lockfiles and wrote `rustsec-findings.json` (29 rows: 27 for `rust/Cargo.lock`, 2 for `koda-command-guard`). The Rust analyst re-ran an independent full-database sweep and hand-checked four matches; all 29 rows were identical, with no false positives or negatives. | Local clone of rustsec/advisory-db at `4ef2df8` (2026-11-13T13:33+01:00). | 06:33 |
| GitHub | Dependabot alerts, default branch | Not exported (see §1.3). | — | — |

Repository state: branch `claude/dreamy-cerf-mhvbwn` at `3cda31a`. The report writer ran `git diff --stat origin/main HEAD` over every lockfile and manifest plus `Dockerfile`, `Dockerfile.runtime-kernel` and `apps/web/Dockerfile`, and it was empty. The audited dependency set therefore equals the local `origin/main` ref (tip `4bed7bd`). No fetch was run, so it was not checked whether that ref matches GitHub's current default branch.

### 1.2 Method

- **Slices.** Four analysts covered Python (all 14 pip-audit packages), Node production (every record in `pnpm audit --prod`), Node dev-only (records in the full audit that are not in the prod audit; none are prod-only) and Rust (both lockfiles). Reachability was judged from Koda's code, the `Dockerfile*` files, the compose files, `packages/cli/release/bundle`, installed package sources (`.venv`, `node_modules`, `~/.cargo/registry`) and the local `apps/web/.next` build.
- **Verifiers.** A skeptic pass tried to refute `not_reachable` claims. A feasibility pass checked that each fixed version exists on its registry, covers every listed advisory, is allowed by parent pins, and whether it breaks Koda. Some verifiers ran dry-run resolutions on scratch copies of the manifests and lockfiles, never on the repository: `uv lock --dry-run`, `pnpm update --lockfile-only`, `cargo update --dry-run`.
- **Reconciliation.**
  - Where a verifier did not uphold a claim, this report uses the verifier's corrected values and the row says so.
  - Where a verifier upheld the claim it tested but recorded a different reachability (`next`, `sharp`, `zod`), both values are shown and the higher-exposure one is used for prioritisation.
  - Where an upholding verifier corrected a fixed version (`certifi`, `vite`, `vitest`), the corrected version is used.
  - Packages without a verifier verdict are marked "not verified".
- **Counting.** There is one row per package.
  - Python advisories are de-duplicated by GHSA alias: 206 raw records become 157.
  - Node counts pnpm advisory records. The 93 records are 85 unique GHSA IDs (§1.3).
  - Rust counts RustSec IDs: 28 IDs in 29 rows, because RUSTSEC-2026-0387 matches two `crypto-bigint` versions.
- **Definitions.** Scope is `runtime` (shipped and executed in a production image or process), `build` (used only while building images or bundles) or `dev` (local dev, test and lint tooling, not shipped). Reachability is `reachable` (attacker-influenced input can reach the vulnerable path, with a citation), `not_reachable` (with a cited reason) or `unclear`. Disposition is `upgrade`, `not_reachable`, `no_fix` or `remove`.
- **Read-only.** No repository file other than this report was written, and nothing was installed or upgraded in the repository.

### 1.3 Dependabot comparison (not reconciled)

GitHub reports 352 open Dependabot alerts on the default branch: 23 critical, 163 high, 147 moderate and 19 low (MASTER_PLAN M0-E4-T1, R-03). The plan's `gh api` export step could not be run from this session, so the alert list is compared by count only, not matched alert by alert.

| Source | Critical | High | Moderate | Low | Informational | Total |
|---|---|---|---|---|---|---|
| Dependabot, default branch | 23 | 163 | 147 | 19 | — | 352 |
| This triage: Python (unique GHSA) | 7 | 72 | 70 | 8 | 0 | 157 |
| This triage: Node (pnpm records, full audit) | 5 | 41 | 39 | 8 | 0 | 93 |
| This triage: Rust (RustSec IDs) | 0 | see note | see note | see note | 6 | 28 |

Note on Rust: RustSec carries CVSS for only some advisories, and several labels were assigned by the analyst. Rust severity is therefore reported per package in §2.

Why the Dependabot counts are larger:

- **Per-manifest duplication.** Dependabot alerts are per manifest path. Koda tracks the same Python packages in `pyproject.toml`, `requirements.txt` and `uv.lock`; for example, `requirements.txt` lines 5–32 declare aiohttp, asyncssh, pillow, pypdf, cryptography and urllib3. Rust crates are spread across two lockfiles. Each manifest Dependabot scans can carry its own copy of an alert, while this triage counts each advisory once per ecosystem.
- **Per-alias and per-version-line duplication.** A GHSA that affects two installed version lines or two packages becomes several records.
  - The 93 pnpm records are 85 unique GHSA IDs: brace-expansion has 6 GHSA × the 1.x and 5.x lines, fflate has the 0.6.x and 0.8.x lines, and GHSA-82fw is filed against both `vitest` and `@vitest/mocker`.
  - `crypto-bigint` 0.4.9 and 0.5.5 match one RustSec ID.
  - In the other direction, pip-audit's 206 raw records collapse to 157 here because the PYSEC, BIT and CVE aliases of one GHSA are merged.
- **Smaller effects (not quantified).** GHSA severity labels can differ from RustSec or analyst labels, and the advisory snapshots differ in time. Verifiers found advisories newer than the audit data, such as GHSA-xp26-3454-mjgp and GHSA-vfpm-58rq-9qcg.

## 2. Summary per ecosystem

Advisories by severity (per advisory record):

| Ecosystem | Packages | Advisories | Critical | High | Moderate | Low | Info |
|---|---|---|---|---|---|---|---|
| Python | 14 | 157 | 7 | 72 | 70 | 8 | 0 |
| Node, production tree | 11 | 36 (35 GHSA) | 5 | 17 | 12 | 2 | 0 |
| Node, dev-only | 8 | 57 (50 GHSA) | 0 | 24 | 27 | 6 | 0 |
| Rust | 17 | 28 IDs (29 rows) | 0 | per package | per package | per package | 6 |
| **Total** | **50** | **278** | | | | | |

Packages by highest severity, scope, final reachability and disposition:

| Ecosystem | Highest severity: C / H / M / L / Info | Scope: runtime / build / dev | Reachability: reachable / unclear / not | Disposition: upgrade / not_reachable / no_fix / remove |
|---|---|---|---|---|
| Python | 3 / 9 / 2 / 0 / 0 | 14 / 0 / 0 ¹ | 7 / 1 / 6 | 8 / 6 / 0 / 0 |
| Node, production | 1 / 7 / 2 / 1 / 0 | 5 / 6 / 0 | 3 / 1 / 7 ² | 5 / 6 / 0 / 0 |
| Node, dev-only | 0 / 4 / 4 / 0 / 0 | 0 / 0 / 8 | 0 / 0 / 8 | 7 / 1 / 0 / 0 |
| Rust | 0 / 4 / 5 / 2 / 6 | 13 / 1 / 3 ³ | 5 / 0 / 12 | 5 / 10 / 2 / 0 |
| **Total** | **4 / 24 / 13 / 3 / 6** | **32 / 7 / 11** | **15 / 2 / 33** | **25 / 23 / 2 / 0** |

¹ `msgpack` is a dev-group package. It is shipped in both Python images because `uv export` in `Dockerfile:56-65` and `Dockerfile.runtime-kernel:57-66` has no `--no-dev`; it is installed but never executed. `pip` is also used at build time.
² The analyst and verifier disagree on three packages, so the higher-exposure value is used: `next` and `zod` are counted as reachable and `sharp` as unclear.
³ `quinn-proto` and `quinn-udp` are lockfile-only and not compiled into any target. `pyo3` belongs to `koda-command-guard`, which is not shipped. `rustix` is build-only (proto codegen).

Reachable critical and high findings at a glance:

| Ecosystem | Reachable critical | Reachable high | Unclear or disputed |
|---|---|---|---|
| Python | certifi (1 advisory; needs an on-path attacker holding a compromised eMudhra intermediate key) | pillow (10), pypdf (13), aiohttp (3), urllib3 (1, GHSA-vxq7) | cryptography GHSA-537c (high, unclear) |
| Node, production | none confirmed | ws (1, pre-auth); zod (1; reachable per analyst, unclear per verifier) | next (critical; analyst not_reachable, verifier reachable); sharp (3 high, unclear) |
| Node, dev-only | none | none | none |
| Rust | none | rustls-webpki and webpki-roots (1 each; mainly the opt-in bot-gateway); postgres-protocol RUSTSEC-2026-0179 (multi-host cluster mode only) | none |

## 3. Critical and high findings

"Verified-by" records whether the skeptic or feasibility pass upheld the claim. GHSA IDs are listed below; their CVE, PYSEC and BIT aliases are in the raw data.

### 3.1 Python

| Package | Installed | Advisories | Severity | Scope | Reachability (evidence) | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| pillow | 12.2.0 | 55 (18 reachable) | critical (highest reachable: high) | runtime: direct dependency and via rapidocr-onnxruntime; in both Python images | **reachable**. `Image.open()` is called with no `formats=` on attacker bytes at `koda/services/artifact_ingestion.py:1081` (Telegram photos and documents), `koda/control_plane/operator_profile_photos.py:70-90` and `koda/squads/room_photos.py:86-110`, and runs on the event loop. All 5 criticals are on unused paths: no olefile, no Ghostscript, no `draft`/`thumbnail`/`seek`, and no TIFF or PDF save. | upgrade | 13.0.0 | **yes**: semver-major; raise the `<13.0` cap in `pyproject.toml:30` and `requirements.txt:17` | feasibility: upheld. 13.0.0 is on PyPI and covers 55/55. 12.3.0 fixes 13, of which only 2 are reachable, so it is not a sufficient interim. rapidocr-onnxruntime declares Pillow unbounded. 13.0 ships only manylinux_2_28 and musllinux wheels, which fit `python:3.12-slim`. |
| certifi | 2026.2.25 | GHSA-6q48-6c7w-9gw2 | critical | runtime: via httpx, requests and botocore | **reachable, conditional**. httpx verifies with `certifi.where()`; it carries Telegram Bot API traffic (including the token) and Hugging Face downloads, and botocore uses it for S3. Exploitation needs an on-path attacker holding a compromised eMudhra intermediate key. aiohttp uses the system store and is not affected. | upgrade | 2026.10.19 (minimum fixed: 2026.10.18) | no (data-only calver bump) | feasibility: upheld, **target corrected** to 2026.10.19 or later per the advisory: 2026.10.18 removed all emSign roots and 2026.10.19 restored the unaffected ones. pip's vendored certifi is not covered by this bump. |
| anyio | 4.12.1 | GHSA-82r6-8w77-94w6 (critical), GHSA-5p39-cfhj-2xmp (moderate) | critical | runtime: via httpx | not_reachable. httpx IDNA-2008-encodes the host (`httpx/_urlparse.py:390`), so httpcore passes only ASCII to `TLSStream.wrap` (`httpcore/_async/connection.py:151`), which is the advisory's own workaround. `anyio.to_process` is never used. | not_reachable | 4.14.2 (hygiene) | no | skeptic: upheld. The `sni_hostname` override is unused, huggingface_hub uses the sync client, and the 4.14.2 wheel was inspected. |
| pypdf | 6.11.0 | 45 (27 reachable) | high | runtime: direct dependency | **reachable**. `PdfReader(str(path), strict=False)` and `page.extract_text()` at `artifact_ingestion.py:962,974` run on user documents and agent downloads, synchronously on the event loop, so one crafted PDF can stall a runtime worker (CPU or memory DoS). | upgrade | 6.21.4 | no (within `<7.0.0`) | feasibility: upheld (the last 6.x release; covers 45/45) |
| aiohttp | 3.13.5 | 22 (11 reachable) | high | runtime: direct dependency, used as both server and client | **reachable**. Servers: the control-plane at `koda/control_plane/supervisor.py:223-238` (bound to 0.0.0.0 in compose and fronted by nginx), the runtime/health server at `koda/services/health.py:485-497`, and WebSocket endpoints at `koda/services/runtime/api.py:1266-1274`. Client: `koda/services/http_client.py:51-54` fetches attacker-chosen URLs. The C parser is in use. Pre-auth: 5wr8 (high), 4fvr, 63hw, g3cq, mfx4. | upgrade | 3.14.4 | no (within `<4.0`; also needs yarl ≥1.25.1, and the lock has 1.23.0) | feasibility: upheld. yarl must be bumped too; the discord.py and line-bot-sdk ranges are compatible. The lock was not resolved. |
| urllib3 | 2.7.0 | GHSA-vxq7-64xx-v4gw (high), GHSA-8988-9cw3-xx77 (high), GHSA-gh4c-6fx4-qh6g (moderate) | high | runtime: direct (`pyproject.toml:49`), via botocore and requests | **reachable (verifier correction; analyst: not_reachable)**. vxq7: botocore reads non-streaming S3 responses through `read_chunked()`, and the default endpoint is plaintext `http://seaweedfs:8333` on a non-internal bridge, so a compromised SeaweedFS or an on-path peer can trigger it. A loopback test grew peak RSS by about 206 MiB. Agent-written scripts using `requests` in the runtime image also reach vxq7 and the gh4c code path; the shell is enabled by default (`koda/config.py:633`). 8988 is not reachable from Koda code. | upgrade | 2.8.0 | no (raise the floor in `pyproject.toml:49`) | skeptic: **not upheld**, corrected to reachable / upgrade. Do not defer this to a routine lock refresh. |
| asyncssh | 2.23.0 | GHSA-2wxc-x7rj-hg8f (high), GHSA-rw4j-r22c-9gc3 (moderate) | high | runtime: direct dependency | **reachable, conditional (moderate only)**. asyncssh is used only as a client tunnel (`koda/services/db_manager.py:117-137`). rw4j needs a malicious or compromised SSH server configured by the operator. 2wxc (SCP) is not reachable because `asyncssh.scp` is never called. | upgrade | 2.24.0 | no (forces cryptography ≥48.0.1) | feasibility: upheld |
| cryptography | 48.0.0 | GHSA-537c-gmf6-5ccf (high), GHSA-g6cj-pr64-35w5 (high), GHSA-jwv3-5hgf-82ww (high), GHSA-m2h6-j472-rp4c (moderate) | high | runtime: direct dependency and via asyncssh | **unclear**. Koda uses only Fernet (`koda/control_plane/crypto.py:8,51-60`) plus asyncssh. 537c (the bundled OpenSSL; secadv 20260609 is not in the collected data) cannot be mapped to those paths. g6cj, jwv3 and m2h6 hit PKCS#7 and `x509.verification` APIs that Koda does not use. | upgrade | **50.0.0** for all four (verifier correction). 48.0.1 is the non-breaking minimum for 537c. | 50.0.0: **yes**, the `<49.0` cap in `pyproject.toml:41` and `requirements.txt:26` must become `<51`. 48.0.1: no. | feasibility: **not upheld** for "48.0.1 fixes all four"; it fixes only 537c. 50.0.0 drops the win32 and macOS x86_64 wheels, so those dev installs would build from source. |
| filelock | 3.25.2 | 9 (list below) | high | runtime: via huggingface-hub | not_reachable. The only use is huggingface_hub's WeakFileLock during `snapshot_download`. ReadWriteLock is never used, several issues are Windows-only, and the rest need a second local user, while both images run a single uid (botuser). | not_reachable | 4.2.1 | **yes** (3.x to 4.x; there is no 3.x backport) | skeptic: upheld. A dry run resolves cleanly. The dev-group cachecontrol FileCache also ships, but it is never invoked. |
| fsspec | 2026.4.0 | GHSA-27vj-qcqg-25rc | high | runtime: via huggingface-hub | not_reachable. Nothing uses fsspec, `reference://` or HfFileSystem, and jinja2, which the vulnerable sinks import, is not installed. | not_reachable | 2026.6.0 (hygiene) | no | skeptic: upheld |
| soupsieve | 2.8.3 | 8 (list below) | high | runtime: via beautifulsoup4 | not_reachable. Every selector is a constant (`koda/services/http_client.py:324-326`, `artifact_ingestion.py:1489-1497`). The only descendant selector runs on the fixed DuckDuckGo response, and attacker HTML only meets combinator-free selectors, which measured linear. | not_reachable | 4.0.0 fixes all 8; 2.10 fixes 5 with no other change | 4.0.0: **yes**, semver-major and needs `requires-python` ≥3.11.5 | skeptic: upheld, with a correction: 3.0.2 and later require Python ≥3.11.5. |
| msgpack | 1.1.2 | GHSA-6v7p-g79w-8964, GHSA-j586-36cw-2gc2 | high | runtime: shipped but never executed (dev group via pip-audit → cachecontrol; see ¹) | not_reachable. Neither Koda nor any runtime dependency imports it. | not_reachable | 1.2.3 | no | skeptic: upheld. Exporting with `--no-dev` was reproduced and drops msgpack, cachecontrol and pip-audit. |

Python advisory IDs for the larger packages:

- **pillow**: 13.0.0 fixes all 55; the 13 fixed in 12.3.0 are marked †.
  - Reachable, high (10): GHSA-78g4-xqwv-q3g8, GHSA-cp9v-662q-vvx9, GHSA-c6hw-5grf-ff96, GHSA-q45j-58j2-45rg, GHSA-5xm2-6676-qcp9, GHSA-65qm-jvmh-6pqg, GHSA-g4qv-2jxx-769h, GHSA-vjc4-5qp5-m44j†, GHSA-gg2r-wvfm-q9rx, GHSA-g842-9rc4-69pw.
  - Reachable, moderate (8): GHSA-462x-pgg6-55fp, GHSA-4558-3h8r-v8xp, GHSA-74r2-7ff9-mjj2, GHSA-xgh8-jp6q-p5x8, GHSA-pg7v-jwj7-p798†, GHSA-wqgw-9xfh-qf2g, GHSA-24rc-8hj2-v98c, GHSA-p8hx-v2p6-rp84.
  - Not reachable, critical (5): GHSA-332p-7hrc-92wf (TIFF save), GHSA-5x8w-8jj5-q52h (FPX/MIC, no olefile), GHSA-8g5g-8vmr-9782 (`draft`/`thumbnail`), GHSA-v9pv-5gc8-w2m6 (`seek`), GHSA-w889-685w-c8fh (Ghostscript).
  - Not reachable, high (24): GHSA-22hg-r758-rrw9, GHSA-27h8-gf7j-v5hc, GHSA-3j72-p6qg-6xp7, GHSA-45hq-cxwh-f6vc†, GHSA-58r4-6rv3-gfh8, GHSA-5x94-69rx-g8h2†, GHSA-62p4-gmf7-7g93†, GHSA-6r8x-57c9-28j4†, GHSA-7mwm-ghpf-9vrm, GHSA-8v84-f9pq-wr9x†, GHSA-9hw9-ch79-4vh6†, GHSA-9v9v-9qvf-h2hj, GHSA-f2g6-542v-9j58, GHSA-g7cr-3p24-7wf7, GHSA-j4m9-6w36-pw47, GHSA-jg86-v3jv-hrpm, GHSA-jjj6-mw9f-p565†, GHSA-mrfp-p49p-3hf2, GHSA-p4wg-p73j-c528, GHSA-pchr-8j38-3x4p, GHSA-phj9-mv4w-65pm†, GHSA-xcvg-w56q-r89m, GHSA-xj96-63gp-2gmr†, GHSA-xvh5-g6gv-559v.
  - Not reachable, moderate (8): GHSA-254f-3936-288h, GHSA-4rm8-3hmm-39fg, GHSA-4rr5-89j8-mwwm, GHSA-4x4j-2g7c-83w6†, GHSA-654x-cwwv-5j9c, GHSA-fc9g-5qg7-mf45, GHSA-fj7v-r99m-22gq†, GHSA-vx6w-vv9f-6gvg.
- **pypdf**: 6.21.4 fixes all 45.
  - Reachable, high (13): GHSA-5849-834g-hvw5, GHSA-jr96-gvgh-j3r4, GHSA-gmh7-3g9r-mjh5, GHSA-x3rh-gjgm-fmqc, GHSA-5jq2-8x83-x246, GHSA-6c7f-9265-g8fw, GHSA-jw7q-gvrg-4vj3, GHSA-cggf-277g-3q54, GHSA-62m5-6wh8-28x7, GHSA-5xf7-4p34-54qr, GHSA-g867-7843-wf8q, GHSA-fp3h-c4fm-7vvf, GHSA-g9cg-prrw-2r8q.
  - Reachable, moderate (14): GHSA-248m-82v9-q6g6, GHSA-39mj-jf6j-2qj3, GHSA-55h5-xmcq-c37v, GHSA-fc8x-2rww-xw9m, GHSA-f54x-cmq8-qg57, GHSA-jm82-fx9c-mx94, GHSA-7mh2-4gg2-979f, GHSA-5hgr-hg42-57jg, GHSA-cgf9-327m-v77c, GHSA-fp3f-mc75-235c, GHSA-fwg2-594c-jp42, GHSA-j543-4vmf-qm7v, GHSA-763m-79hh-57f2, GHSA-5qjq-93h5-hrgp.
  - Not reachable, high (7): GHSA-42gh-23hr-vphw, GHSA-4vqv-7265-gm2w (strict mode), GHSA-mfr5-77xh-9j7h, GHSA-php9-fj8v-98fj, GHSA-qv6h-rv94-w285, GHSA-v247-6f48-mgcj, GHSA-w23x-9jrw-r45c.
  - Not reachable, moderate (10): GHSA-m2v9-299j-rv96, GHSA-g9xf-7f8q-9mcj, GHSA-jp53-mhqp-8xcg, GHSA-9mx8-4j7g-633p, GHSA-qfv9-64jg-mh7p, GHSA-23w6-3w8w-8484, GHSA-6vvc-x485-93v7, GHSA-wjqc-6w8f-h24c, GHSA-52x6-gq3r-vpf4, GHSA-cj93-chg6-vgv8.
  - Not reachable, low (1): GHSA-5hx5-vpf9-5wcv.
  - The unreachable ones cover writer, merge and clone paths, outline, page-label, form, embedded-file and XMP readers, layout-mode extraction, strict mode, and image extraction.
- **aiohttp**: 3.14.4 fixes all 22.
  - Reachable, high (3): GHSA-5wr8-gcqf-gqf3 (pre-auth), GHSA-2g87-pp6c-29x5 (WebSocket, after a runtime token), GHSA-cq5v-8q36-5273 (client parser).
  - Reachable, moderate (6): GHSA-4fvr-rgm6-gqmc, GHSA-63hw-fmq6-xxg2, GHSA-g3cq-j2xw-wf74, GHSA-mfx4-hv73-q22v, GHSA-xcgm-r5h9-7989, GHSA-6cjc-53gc-5rqm.
  - Reachable, low (2): GHSA-9x8q-7h8h-wcw9, GHSA-gx76-c99x-2c96.
  - Not reachable, high (1): GHSA-9xw5-w5jj-pvcg (needs `Request.post()`; Koda uses `request.multipart()`).
  - Not reachable, moderate (7): GHSA-f9xw-jh8m-3mwq, GHSA-jg22-mg44-37j8, GHSA-hg6j-4rv6-33pg, GHSA-hpj7-wq8m-9hgp, GHSA-494j-54xm-rwp3, GHSA-mq44-7p77-q5h7, GHSA-pqxq-w44r-73xw.
  - Not reachable, low (3): GHSA-2fqr-mr3j-6wp8, GHSA-4m7w-qmgq-4wj5, GHSA-m6qw-4cw2-hm4m.
- **filelock** (high: v4x8; low: 567q, 9vhv; others moderate): GHSA-v4x8-3wr5-3wq8, GHSA-567q-5qvw-pf92, GHSA-69hj-f68j-2879, GHSA-8mx5-7m5m-r77g, GHSA-9vhv-jxww-xfm5, GHSA-cwqr-hh33-gh44, GHSA-fq56-3cx3-fjxp, GHSA-j8f7-rjxc-mr56 (fixed in 4.0.9), GHSA-rfpc-qcw5-3pc4.
- **soupsieve** (high: 2wc2, 836r, 6655, mmhr): GHSA-2wc2-fm75-p42x and GHSA-836r-79rf-4m37 (2.8.4); GHSA-gjv8-xp57-g29c and GHSA-j934-xhv5-fg8f (2.9.0); GHSA-4j63-6c4x-wfg4 (2.10.0); GHSA-6655-6qjp-jx7x and GHSA-7g44-g9rc-x53w (3.0.2); GHSA-mmhr-3c5m-f64f (4.0.0).

### 3.2 Node, production tree (`pnpm audit --prod`)

| Package | Installed | Advisories | Severity | Scope | Reachability (evidence) | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| next | 16.2.6 (exact pin in `apps/web/package.json`) | 20 (list below) | critical | runtime: custom server `apps/web/server.mjs:115`, image `apps/web/Dockerfile:49-77` | **disputed; treated as reachable**. The analyst found it not reachable because no advisory's precondition is met: no `'use server'`, `'use cache'`, `next/og`, i18n or rewrites; `remotePatterns []`; a Linux image; production mode. The optimizer also fetches only local URLs, through a cookie-less internal request that passes `src/proxy.ts`. The verifier found it reachable at package level: `/_next/image` is unauthenticated (`src/proxy.ts:338`), the optimizer is on by default, and the Turbopack build plus `src/proxy.ts` match GHSA-6gpp. | upgrade | 16.4.1 | no (minor bump; edit the exact pin and move eslint-config-next in lockstep) | feasibility: upheld. 16.4.1 is the minimum; the 16.2.x backports end at 16.2.12, which is still affected. |
| sharp | 0.34.5 (@img/sharp-linux-x64, libvips 1.2.4) | GHSA-f88m-g3jw-g9cj (libvips, 0.35.0), GHSA-rgj7-g3m4-5g8c (libheif, 0.35.4), GHSA-wq5f-xc86-pv6w (librsvg, 0.35.5) | high | runtime: optional dependency of next, present in the runner image | **unclear (verifier; analyst: not_reachable)**. The only caller is `/_next/image`. The analyst found no unauthenticated local URL that serves attacker-authored GIF, TIFF, VIPS, HEIF or SVG bytes; the verifier did not determine this. The runner is glibc (node:26-slim), which matches the advisories' RCE conditions. | upgrade | 0.35.5 | not for Koda: it arrives via next 16.4.1, which declares ^0.35.5. 0.34 to 0.35 counts as major under 0.x caret rules. | feasibility: upheld. Parent pin: next 16.2.x declares ^0.34.5, so this needs next ≥16.4.1 or an override outside next's range, which is unsupported. |
| ws | 8.20.1 | GHSA-96hv-2xvq-fx4p | high | runtime: direct dependency (`server.mjs:3`) | **reachable**. `server.mjs:144-151` completes `handleUpgrade` for any `/api/runtime/relay/*` request before checking the descriptor or token. There is no `maxPayload` (`server.mjs:125`), and the graceful `close()` keeps parsing frames during the 30 s close timeout. Anyone who can reach the web port (default 127.0.0.1:3000) can exhaust the dashboard's memory without authenticating. | upgrade | 8.21.0 | no (inside ^8.20.1) | feasibility: upheld |
| zod | 4.4.3 | GHSA-mrhx-c7xc-m3w5 | high | runtime: server routes and client bundle | **reachable per analyst, unclear per verifier; treated as reachable**. `z.array` body schemas in `src/app/api/control-plane/[...path]/route.ts:384-396` run after the operator-token check (`:342-345`), and in 4.4.3 `.max()` runs only after every element is parsed. The client also parses agent output with `z.array` (`src/lib/contracts/generative-ui.ts:63-228`). Exploitation needs an authenticated operator or prompt-injected agent output, and the impact is low. | upgrade | 4.6.6 | no (inside ^4.4.3) | feasibility: upheld. The verifier did not trace attacker-supplied server input. |
| postcss | 8.5.14 (forced by the root `pnpm.overrides`) | GHSA-r28c-9q8g-f849 (high), GHSA-fxqj-rqcc-2cmp (moderate) | high | build | not_reachable. It runs only at build time on first-party CSS (`apps/web/postcss.config.mjs`), and it is absent from the `.next/server` chunks. | upgrade (override edit) | 8.5.23 | no | feasibility: upheld. Keep the override until next is ≥16.4.1, because next 16.2.6 pins the vulnerable 8.4.31. 8.5.23 needs nanoid ^3.3.16. |
| nanoid | 3.3.12 | GHSA-28wg-ghj8-5hjv, GHSA-2v37-7h3g-55p8 | high | build (on disk in the runner image, not executed) | not_reachable. postcss is the only caller and passes a constant size (`nanoid(6)`); `customAlphabet` and `customRandom` are never called. | not_reachable | 3.3.18 | no | skeptic: upheld, with corrections. nanoid is present in the runner image and inlined into the `.next/build` PostCSS worker, but neither is traced into the server. Next's bundled `next/dist/compiled/nanoid` is a separate copy that pnpm cannot see or override. No postcss bump is needed. |
| browserslist | 4.28.2 | GHSA-c83g-rgw3-j3cx, GHSA-73wf-gq98-2v4g | high | build (on disk in the runner image via styled-jsx's optional peer @babel/core) | not_reachable. Only @babel/core loads it; Next compiles with SWC and uses its own vendored browserslist. Queries come from config, and there is no stats file. | not_reachable | 4.28.7 | no | skeptic: upheld. It is present in the prod install but never loaded. |
| source-map-js | 1.2.1 | GHSA-68fv-2mgg-jv7q | high | build (on disk in the runner image) | not_reachable. Only postcss requires it, and the production server trace contains neither postcss nor source-map-js (confirmed with a dynamic load hook). | not_reachable | 1.2.2 | no | skeptic: upheld, with corrections. It ships on disk, and postcss does reach the vulnerable loop, but only on build-time first-party CSS. No postcss bump is needed. |

next advisory IDs, all fixed by 16.4.1. Nine are fixed in 16.2.11; GHSA-p293 and 2xp9 in 16.3.3; vcvr in 16.3.6; cjq9, 4jqv, f87g, mcj8 and 39w2 in 16.3.8; 2464, p3m5 and 673q in 16.4.1.

- Critical: GHSA-p293-qw3h-jr36 (Windows), GHSA-2xp9-vwfh-vxw4 and GHSA-2464-fhr4-w9xw (AVIF and SVG in the image optimizer), GHSA-vcvr-r3jv-pc5j (`next/og`), GHSA-673q-mjm6-r5xr (`'use cache'`).
- High: GHSA-6gpp-xcg3-4w24 (proxy bypass; per the analyst it needs Turbopack and a single i18n locale), GHSA-m99w-x7hq-7vfj, GHSA-89xv-2m56-2m9x and GHSA-p3m5-59mp-jv5r (Server Actions), GHSA-p9j2-gv94-2wf4 (rewrites), GHSA-cjq9-62q9-8jv4 (remotePatterns).
- Moderate: GHSA-68g3-v927-f742 and GHSA-4633-3j49-mh5q (fetch cache), GHSA-4c39-4ccg-62r3 and GHSA-955p-x3mx-jcvp (Server Actions, `'use cache'`), GHSA-q8wf-6r8g-63ch (remotePatterns), GHSA-4jqv-mc3x-m676 and GHSA-mcj8-r9mp-w47p (SSG/ISR), GHSA-f87g-xv8r-7p7x (metadata image routes).
- Low: GHSA-39w2-rjm5-chcv (dev-server MCP endpoint).

### 3.3 Node, dev-only

| Package | Installed | Advisories | Severity | Scope | Reachability (evidence) | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| undici | 7.25.0 | 29 (list below) | high | dev: via jsdom (the Vitest environment) | not_reachable. jsdom is used only as the test environment (`apps/web/vitest.config.ts:15`). Tests stub fetch, EventSource and WebSocket, and no ProxyAgent, BalancedPool or interceptors are configured. It is not in `pnpm install --prod`. | upgrade (to clear the audit gate) | 7.30.1 | no (inside jsdom's ^7.25.0) | feasibility: upheld. A lock refresh resolves 7.30.2. |
| brace-expansion | 1.1.13, 5.0.6 | 6 GHSA × 2 lines (12 records; list below) | high | dev: ESLint via minimatch | not_reachable. Brace patterns come from repository config. The 5.x copy is reached only through typescript-estree's project-service path, which is not enabled. | upgrade | 1.1.21 (1.x) / 5.0.12 (5.x) | no | feasibility: upheld, **with a correction**. The root override at `package.json:8` (`"brace-expansion@1.1.12": "1.1.13"`) actively pins 1.x to 1.1.13, because pnpm matches overrides by range intersection, so it must change to ≥1.1.21. The 5.x override at `package.json:9` would force 5.0.5 onto any future dependent. |
| vite | 8.0.12 | 7 (list below) | high | dev: via vitest | not_reachable. `vitest run` uses middleware mode with `ws: false` and never calls `listen()`. Koda runs no Vite dev server, and the launch-editor issues are Windows-only. | upgrade | **≥8.3.3 recommended** (8.1.6 on the 8.1 line; 8.2.0–8.2.3 and 8.3.0–8.3.2 are still vulnerable) | no | feasibility: upheld, **fixed version corrected**: a bare `>=8.1.6` floor is not safe. |
| js-yaml | 4.1.1 | GHSA-h67p-54hq-rp68, GHSA-52cp-r559-cp3m, GHSA-5p4m-2wfm-xmqj, GHSA-2883-xcg3-v3hh | high | dev: @eslint/eslintrc | not_reachable. It is loaded only in legacy eslintrc mode; the repository uses flat config and has no `.eslintrc*` file. | upgrade | 4.3.2 | no | feasibility: upheld |

Dev-only advisory IDs:

- **undici** (29; 7.30.1 is the highest patched floor): GHSA-vmh5-mc38-953g, GHSA-p88m-4jfj-68fv, GHSA-hm92-r4w5-c3mj, GHSA-g8m3-5g58-fq7m, GHSA-pr7r-676h-xcf6, GHSA-8xcm-r25x-g524, GHSA-4cwx-7wf7-3272, GHSA-m8rv-5g2x-5cg5, GHSA-jr45-8vmc-qm54, GHSA-v3r7-h72x-cjcm, GHSA-35p6-xmwp-9g52, GHSA-pmjh-fq2x-6v4x, GHSA-r53p-7pc4-xj5r, GHSA-rfgv-xxqx-mfg5, GHSA-3xpg-4rpp-hhhm, GHSA-2jfj-6hjv-fm6j, GHSA-2gqq-gqf2-x968, GHSA-w293-vg96-wgc3, GHSA-8436-99hf-9mmv, GHSA-rx4f-c7p8-82vq, GHSA-4qv8-2p9j-2685, GHSA-f72v-6w45-q472, GHSA-xjj6-f33q-929c, GHSA-4w7w-5xrc-9h26, GHSA-2m5v-pch6-74hx, GHSA-qrxm-fqhp-jwvm, GHSA-9fm3-97px-rjf6, GHSA-55wc-3pg8-jfw6, GHSA-vxpw-j846-p89q.
- **brace-expansion** (each GHSA once per version line): GHSA-3jxr-9vmj-r5cp, GHSA-mh99-v99m-4gvg, GHSA-rgw5-rvv9-x895, GHSA-q2hr-2g5m-vwhr, GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p.
- **vite**: GHSA-v6wh-96g9-6wx3, GHSA-698v-4r3x-3vcv, GHSA-r825-w8mm-5pxw, GHSA-587h-7wmj-h5pm (high), GHSA-9jrq-w75r-8gcw, GHSA-rq7h-c2jc-7f22, GHSA-fx2h-pf6j-xcff.

### 3.4 Rust

| Package | Installed | Advisories | Severity | Scope | Reachability (evidence) | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| rustls-webpki | 0.103.13 | RUSTSEC-2026-0382 (CVE-2026-111943) | high (assigned by the analyst; no CVSS) | runtime | **reachable**. koda-bot-gateway calls `https://api.telegram.org` (`rust/koda-bot-gateway/src/config.rs:37-39`) and trusts webpki-roots 1.0.7, which still contains emSign ECC Root CA - G3; the bot token travels in the URL path (`telegram.rs:82`). bot-gateway is an opt-in profile (`docker-compose.yml:299`) and is not in the release bundle. The artifact-engine S3 client is affected only with an https or AWS endpoint; the default is `http://seaweedfs:8333`. | upgrade | 0.103.16 | no (patch) | feasibility: upheld. It must be bumped explicitly, because rustls 0.23.46 alone allows 0.103.14–15, which are still affected. Knock-on bumps: aws-lc-rs 1.16.2 → 1.19.0 and aws-lc-sys 0.39.1 → 0.47.0, a C build in artifact-engine that was not built. |
| webpki-roots | 1.0.7 | RUSTSEC-2026-0381 (CVE-2026-111943) | high (assigned by the analyst) | runtime (bot-gateway only) | **reachable** by the same path. `cargo tree -p <bin>` shows that only koda-bot-gateway links it. | upgrade | 1.0.10 | no | feasibility: upheld (the dry run changes only this crate) |
| postgres-protocol | 0.6.11 | RUSTSEC-2026-0179 / GHSA-5x78-73v4-xg6w (high, CVSS 4.0 about 8.7); RUSTSEC-2026-0180 / GHSA-rgqc-3x5p-6gwg (moderate) | high | runtime: artifact, memory and retrieval; opt-in bot-gateway and policy | **reachable in multi-host cluster mode (verifier correction; analyst: not_reachable)**. The DSN comes only from the environment, and every compose file pins `postgres:5432`, so the default bundle is not exposed. However, TLS is hard-coded off (`rust/koda-postgres/src/lib.rs:155`, `rust/koda-policy-engine/src/store.rs:133`), and `docs/operations/cluster-mode.md` documents sidecars reaching a shared Postgres on another host. In that setup an attacker on the path can exploit 0179 (unbounded SCRAM iteration count). 0180 is not reachable because hstore is never used. | upgrade | 0.6.12 | no | skeptic: **not upheld**, corrected to reachable / upgrade |
| quinn-proto | 0.11.14 | 7 (list below) | high (CVSS 3.1 7.5 on 0185 and 0340) | dev (lockfile-only, not compiled) | not_reachable. reqwest is built without `http3`, `cargo tree -i quinn-proto --target all` prints nothing, and `rust/target` contains no quinn artifacts. | not_reachable | 0.11.19 (lock hygiene) | no | skeptic: upheld. A dry run resolves. Until the lock is bumped or the IDs are ignored, `cargo audit` at `security.yml:127` and `release.yml:397` will fail. |

quinn-proto IDs: RUSTSEC-2026-0185 (CVE-2026-25800, GHSA-4w2j-m93h-cj5j), RUSTSEC-2026-0338 (GHSA-465w-v9q3-7j98), RUSTSEC-2026-0339 (GHSA-hmxj-32vh-65vr), RUSTSEC-2026-0340 (GHSA-3g6h-r5qx-f6hq), RUSTSEC-2026-0342 (GHSA-2hv7-gw8g-gpq5), RUSTSEC-2026-0523 (GHSA-53rm-773f-4q8c), RUSTSEC-2026-0524 (GHSA-wppq-2f6r-wfvm).

## 4. Moderate, low and informational findings

Python:

| Package | Installed | Advisories | Severity | Scope | Reachability | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| pip | 26.0 (Dockerfile pin); 26.1 (dev-group export) | GHSA-qwm4-qh6w-59xr, GHSA-wf93-45jw-7689 | moderate | runtime and build | **reachable**. The Telegram `/pip` command runs `pip <args>` (`koda/handlers/packages.py:15-36`, registered at `koda/__main__.py:347`). `PIP_ENABLED` defaults to true (`koda/config.py:770`) and the index URL is unrestricted. The command is gated by `@authorized` and `@with_approval('pip')`. | upgrade | 26.2 | no | feasibility: upheld. Both pins must change (`Dockerfile:20`, `Dockerfile.runtime-kernel:28`), and either the locked pip must be bumped or `--no-dev` added. |
| multidict | 6.7.1 | GHSA-54p9-h82j-f925 | moderate | runtime | not_reachable. There are no items-view set operators in the installed aiohttp and yarl or in koda. | not_reachable | 6.9.1 | no | not verified |

Node, production tree:

| Package | Installed | Advisories | Severity | Scope | Reachability | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| fflate | 0.8.2, 0.6.10 | GHSA-px8p-9vwx-vf98 (2 records) | moderate | runtime (browser only; drei/three-stdlib) | not_reachable. The `unzipSync` loaders are never imported, and fflate code is absent from the client chunks. | not_reachable | 0.8.3 / 0.6.11 | no | not verified |
| baseline-browser-mapping | 2.10.29 | GHSA-w5vr-8v7q-w6rv | moderate | build | not_reachable. It is used only by Next's vendored browserslist at build time. | not_reachable | 2.11.0 | no | not verified |
| @babel/core | 7.29.0 | GHSA-4x5r-pxfx-6jf8 | low | build | not_reachable. There is no babel config, Next uses SWC, and only Koda's own source is compiled. | not_reachable | 7.29.6 | no | not verified |

Node, dev-only:

| Package | Installed | Advisories | Severity | Scope | Reachability | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| @vitest/mocker | 4.1.6 | GHSA-82fw-gwwq-j7x9, GHSA-qxg6-89mg-rqv8 | moderate | dev | not_reachable. `mockerPlugin` and `interceptorPlugin` are unused, and nothing listens under `vitest run`. | upgrade (via vitest) | 4.1.12 | no | feasibility: upheld. 4.1.11 is also affected by GHSA-xp26-3454-mjgp, which is not in the audit data. |
| vitest | 4.1.6 | GHSA-82fw-gwwq-j7x9 | moderate | dev | not_reachable (same reason) | upgrade | 4.1.12 (corrected from 4.1.11) | no | feasibility: upheld |
| @humanfs/node | 0.16.7 | GHSA-p498-v437-472g | moderate | dev | not_reachable. ESLint uses only `isDirectory` and `walk`, never `copy` or `copyAll`. | upgrade | 0.16.8 | no | feasibility: upheld |
| minimatch | 10.2.5 | GHSA-g3hv-75wg-m249 | moderate | dev | not_reachable. The only path is typescript-estree's project service, which is not enabled, and the default `optimizationLevel` of 1 is below the advisory's ≥2 condition. | not_reachable (needs risk acceptance for the audit gate) | 11.0.1 | **yes**. It is outside the consumer's ^10.2.2 range, and no 10.x fix exists. | not verified |

Rust:

| Package | Installed | Advisories | Severity | Scope | Reachability | Disposition | Fixed | Breaking? | Verified-by |
|---|---|---|---|---|---|---|---|---|---|
| rustls | 0.23.37 | RUSTSEC-2026-0285, -0346, -0348, -0349 (CVE-2026-123613, -123609, -123610, -123611) | moderate (highest 5.3) | runtime (all 7 binaries, via tonic) | **reachable**. 0285 affects any TLS 1.3 session (bot-gateway to Telegram, https S3, gRPC server TLS when configured), with negligible impact. 0349 affects only artifact-engine (aws-lc-rs with prefer-post-quantum) against https S3. 0346 and 0348 are not reachable: there is no custom `ClientSessionStore`, and brotli is off. | upgrade | 0.23.46 | no | feasibility: upheld |
| h2 | 0.4.13 | RUSTSEC-2026-0258 / GHSA-q83h-524g-xf6h | low | runtime (tonic servers in all 7 binaries) | **reachable, internal network only**. gRPC binds 0.0.0.0 inside containers and is not published to the host. A peer on the backend network, such as a prompt-injected agent in the app container, can flood empty DATA frames. | upgrade | 0.4.16 | no | feasibility: upheld. Which handlers leave request streams undrained was not traced. |
| tokio-postgres | 0.7.17 | RUSTSEC-2026-0178 / GHSA-3gjw-f78c-vvpw | moderate | runtime | not_reachable in the default deployment: it needs a hostile server, and the DSN is pinned to the bundled Postgres. The verifier's NoTls / cluster-mode finding for postgres-protocol applies equally here. | not_reachable (fix it in the same batch) | 0.7.18 | no | not verified |
| quinn-udp | 0.5.14 | RUSTSEC-2026-0538 / GHSA-6pp4-4cxf-xf88 | moderate (assigned by the analyst) | dev (lockfile-only) | not_reachable. It is not compiled, and the Linux images are unaffected in any case. | not_reachable | 0.5.16 | no | not verified |
| crypto-bigint | 0.4.9, 0.5.5 | RUSTSEC-2026-0387 | moderate (assigned by the analyst) | runtime (artifact-engine, `sigv4a` feature) | not_reachable. SigV4a is used only for Multi-Region Access Points; Koda signs single-bucket requests with HMAC SigV4. Exploitation would also need a co-located timing observer. | not_reachable | 0.7.9 (0.7.6–0.7.8 are yanked) | yes. It cannot be forced and arrives via aws-sigv4 ≥1.6.4; alternatively drop the unused `sigv4a` feature (`rust/koda-artifact-engine/Cargo.toml:14`). | not verified |
| pyo3 | 0.24.2 | RUSTSEC-2026-0176 / GHSA-36hh-v3qg-5jq4; RUSTSEC-2026-0177 / GHSA-chgr-c6px-7xpp | moderate (assigned by the analyst) | dev (koda-command-guard, not shipped) | not_reachable. It is built into no image, and `lib.rs` uses neither `PyCFunction::new_closure` nor list/tuple `nth`. | not_reachable | 0.29.0 | yes | not verified |
| ctutils | 0.4.2 | RUSTSEC-2026-0385 | low (assigned by the analyst) | runtime | not_reachable. The only constant-time comparison is SCRAM verification against the trusted bundled Postgres. | not_reachable | 0.4.4 | no | not verified |
| tokio | 1.52.3 | RUSTSEC-2026-0386 | informational (unsound) | runtime | not_reachable. Neither Koda nor any of the 360 locked crates uses `AsyncFd`. | not_reachable | 1.53.3 (no 1.52.x fix exists; 1.54.0 is yanked) | no | not verified |
| anyhow | 1.0.102 | RUSTSEC-2026-0190 | informational (unsound) | runtime | not_reachable (no `downcast_mut` anywhere) | not_reachable | 1.0.103 | no | not verified |
| lru | 0.16.3 | RUSTSEC-2026-0253 | informational (unsound) | runtime (the aws-sdk-s3 S3 Express cache) | not_reachable. `LruCache::pop` is never called, and the keys are Strings. | not_reachable | 0.18.2 (via aws-sdk-s3 ≥1.144.0) | major for lru; no Koda manifest change | not verified |
| rustix | 1.1.4 | RUSTSEC-2026-0486 / GHSA-jh2m-fhpj-3vr7 | informational (unsound) | build (prost-build → tempfile) | not_reachable. It is not linked into any binary, and no xattr calls are made. | not_reachable | 1.1.6 | no | not verified |
| rustls-pemfile | 2.2.0 | RUSTSEC-2025-0134 | informational (unmaintained) | runtime (tonic TLS) | not_reachable. It parses only operator-provided PEM, which is unset in the release compose. | no_fix | none; tonic ≥0.13 drops it | yes (tonic major) | not verified |
| pin-utils | 0.1.0 | RUSTSEC-2026-0441 | informational (unmaintained) | runtime (aws-smithy-http) | not_reachable. The notice describes no vulnerable code. | no_fix | none; aws-smithy-http ≥0.64.2 drops it | no (an in-range AWS SDK bump) | not verified |

## 5. Remediation batches

Batches are ordered so that reachable critical and high findings land first. Each batch can be applied and tested on its own. Every proposed version comes from the analysts and verifiers; none has been installed or tested in the repository.

### 5.1 Python: M1-E7-T2

Gates for every batch: `ruff check .`, `ruff format --check .`, `mypy koda/ --ignore-missing-imports`, `pytest --cov=koda --cov-report=term-missing` (the plan's G and G-PG), and `pip-audit` on the image's `uv export`. Rebuild both Python images (`Dockerfile`, `Dockerfile.runtime-kernel`) and run the CI docker-smoke job. `release.yml:360-385` runs pip-audit with `--all-groups --strict`, so any Python item left unfixed will fail the release gate.

| # | Batch | Changes | Specific regression risks |
|---|---|---|---|
| P1 | Reachable, in-range lock bumps | pypdf 6.21.4; aiohttp 3.14.4 together with yarl ≥1.25.1 (multidict 6.9.1 can come too, within `<7`); certifi ≥2026.10.19; urllib3 ≥2.8.0 (raise the floor in `pyproject.toml:49`); asyncssh 2.24.0 with cryptography ≥48.0.1, which also fixes GHSA-537c. Raise the lower bounds in `pyproject.toml` and `requirements.txt` for direct dependencies so a re-lock cannot regress. | aiohttp server: control-plane routes, multipart parsing (`koda/control_plane/api.py:592,2501,4667`), runtime WebSocket and FileResponse endpoints, webhooks. aiohttp client: `http_client.py` and link fetches. pypdf: changes to `extract_text` output affect artifact-ingestion tests. asyncssh: the Postgres SSH tunnel (`db_manager.py:117-137`). certifi trust-store change for Telegram, Hugging Face and S3 TLS. |
| P2 | Image build fixes | Pin pip ≥26.2 at `Dockerfile:20` and `Dockerfile.runtime-kernel:28`. Add `--no-dev` to the `uv export` at `Dockerfile:56-65` and `Dockerfile.runtime-kernel:57-66`, which removes msgpack, cachecontrol, pip-audit, pytest, ruff and the rest of the dev group from production images. Also bump the locked dev-group pip to ≥26.2. `--no-dev` on its own still leaves the vulnerable 26.0 pin. | Any runtime import of a dev-group package would break; whether any exist was not checked beyond pip-audit and cachecontrol, so verify with the image smoke test. `security.yml:79-89` already assumes dev tooling is absent from images, and this change makes that true. |
| P3 | Pillow 13.0.0 (semver-major) | Widen `pyproject.toml:30` and `requirements.txt:17` to `<14`, then re-lock. Start in parallel with P1: Pillow has 10 reachable high advisories, and 12.3.0 is not a meaningful interim because it fixes only 2 of the 18 reachable ones. | Koda's calls (`Image.open`/`load`, `ImageOps.exif_transpose`, `convert`, `crop`, `resize(Image.Resampling.LANCZOS)`, JPEG save, `UnidentifiedImageError`) have not been tested on 13.x. rapidocr-onnxruntime's internal Pillow use is untested, and it is absent from the local Python 3.13 venv, so the OCR path must be tested in the 3.12 image. Profile and room photo uploads and Telegram photo ingestion. |
| P4 | Not-reachable, in-range hygiene | anyio 4.14.2; fsspec 2026.6.0; multidict 6.9.1 if P1 did not already bring it; msgpack 1.2.3 in the dev lock. | Low. anyio is reached via httpx for python-telegram-bot. |
| P5 | Not-reachable majors (clears the audit gates) | cryptography 50.x, which needs the cap raised from `<49.0` to `<51` and clears g6cj, jwv3 and m2h6; filelock 4.2.1 (the verifier's dry run resolves cleanly); soupsieve 4.0.0 with `requires-python` raised to ≥3.11.5, or 2.10 without that bump (fixes 5 of 8). | cryptography 50.0.0 drops the win32 and macOS x86_64 wheels, so those dev installs would build from source; asyncssh 2.24.x compatibility was checked from metadata only. filelock 4.x behaviour inside huggingface_hub `snapshot_download`. Raising `requires-python` changes the supported interpreter floor. |

Code-level hardening outside M1-E7-T2's file list (each needs its own task or a scope extension):

- Pass `formats=['JPEG','PNG','WEBP','GIF']` to `Image.open` at the three call sites. Per the analyst, this removes the TIFF, IPTC, EPS, XBM, JPEG2000, MSP, SPIDER, BMP-RLE and McIdas exposure.
- Move Pillow and pypdf extraction off the event loop, with a timeout.
- Restrict `/pip` (`--index-url`, `BLOCKED_PIP_PATTERN`).
- Keep a reverse proxy with header timeouts in front of port 8090.

### 5.2 Node: M1-E7-T3

Gates for every batch: `pnpm lint:web`, `pnpm test:web`, `pnpm build:web` (the plan's G), `pnpm audit --audit-level=moderate` as run by `security.yml:111` and `release.yml:388` (without `--prod`, so dev items count), and `pnpm audit --prod`. Rebuild `apps/web/Dockerfile`.

| # | Batch | Changes | Specific regression risks |
|---|---|---|---|
| N1 | Reachable, in-range | ws 8.21.0 (raise the specifier to ^8.21.0); zod 4.6.6. | ws: the relay upgrade path in `server.mjs`. zod: 4.6.6 caps issue accumulation, so issue counts can change; tests that assert issue counts were not checked. Re-run the contracts tests. |
| N2 | next and its build chain | Bump next from 16.2.6 to 16.4.1 (exact pin), which brings sharp ^0.35.5 and an exact postcss 8.5.23. Change the root override `postcss` from 8.5.14 to 8.5.23; it can be dropped once next is ≥16.4.1, but do not drop it before then, because next 16.2.6 pins 8.4.31. Refresh the lock so nanoid ≥3.3.18, source-map-js 1.2.2, browserslist 4.28.7, baseline-browser-mapping 2.11.0 and @babel/core 7.29.6 come in. Move eslint-config-next to 16.4.1 in lockstep, which needs the root override `eslint-plugin-react-hooks` 7.0.1 raised to 7.1.x; otherwise leave eslint-config-next where it is. | Auth gating in `src/proxy.ts` (matcher at `:338`); the `server.mjs` `getUpgradeHandler` relay path; 16.3.x disables AVIF optimization; image-optimizer behaviour; Turbopack build output. The 16.3 and 16.4 release notes could not be reached, so minor-version behaviour changes are unreviewed. |
| N3 | Browser-only hygiene | fflate 0.8.3 and 0.6.11, via a pnpm override or a refresh of drei, three-stdlib and maath. | The orb texture component (`src/components/ui/orb.tsx`). |
| N4 | Dev toolchain (clears the audit gate) | vitest ^4.1.12, which pins @vitest/mocker 4.1.12; vite ^8.3.3, not a bare `>=8.1.6`; undici ≥7.30.1 (lock refresh); js-yaml 4.3.2; @humanfs/node 0.16.8. brace-expansion: change the override at `package.json:8` to ≥1.1.21, and set the one at `package.json:9` to ≥5.0.12 or remove it. Fix the stale `picomatch@4.0.3` override at `package.json:13`, which causes an fdir peer warning. | Test-runner behaviour (jsdom environment, mocks); lint results; vite moves rolldown from 1.0.0 to 1.2.19 (per the dry run). |

Code-level hardening for the dashboard (outside dependency files): set `maxPayload` at `server.mjs:125` and `:78`, and validate the relay descriptor and token before `handleUpgrade`. Until N2 lands, `images.unoptimized: true` in `next.config.ts` removes the `/_next/image` and sharp surface. Do not add Server Actions before N2: `server.mjs:130` does not pin Host, so GHSA-89xv would become reachable.

### 5.3 Rust: M1-E7-T4

Gates for every batch: `cargo fmt --all --check --manifest-path rust/Cargo.toml`, `cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets -- -D warnings` and `cargo test --manifest-path rust/Cargo.toml --workspace` (the plan's G-RS), plus `cargo audit` on both lockfiles as `security.yml:127` and `release.yml:397` run it. cargo-audit was not available in this session. Rebuild the affected `Dockerfile.*` images.

| # | Batch | Changes | Specific regression risks |
|---|---|---|---|
| R1 | TLS stack | rustls 0.23.46; rustls-webpki 0.103.16 or later, bumped explicitly; webpki-roots 1.0.10. The dry runs pull aws-lc-rs 1.19.0, aws-lc-sys 0.47.0 and pkg-config 0.3.34. | The aws-lc-sys C build in `Dockerfile.artifact` was not built. TLS behaviour changes for bot-gateway to Telegram, artifact-engine on https S3, and the memory and security gRPC servers when `GRPC_TLS_SERVER_CERT`/`KEY` are set. An alternative is reqwest with `rustls-tls-native-roots`. |
| R2 | HTTP/2 | h2 0.4.16 or later; `http ^1.1` is already satisfied. | tonic gRPC servers in all 7 binaries. |
| R3 | Postgres client | tokio-postgres 0.7.18 together with postgres-protocol 0.6.12 (and postgres-types 0.2.14). MSRV 1.85 is within the rust:1.95 builders. | The koda-postgres pool, the policy-engine store, and `Row::get`/`try_get` call sites. |
| R4 | In-range hygiene (clears the audit gates) | quinn-proto 0.11.19 (the dry run swaps rand 0.9 for rand_pcg 0.10.2); quinn-udp 0.5.16; ctutils 0.4.4; tokio 1.53.3 or ≥1.54.1, never 1.54.0; anyhow 1.0.103; rustix 1.1.6. | tokio minor bump across all binaries. The rest are lockfile-only or build-only crates. |
| R5 | AWS SDK stack (artifact-engine) | Bump within the existing `"1"` requirements: aws-sdk-s3 ≥1.144.0 brings lru ^0.18.2, aws-sigv4 ≥1.6.4 brings crypto-bigint ^0.7.10, and aws-smithy-http ≥0.64.2 drops pin-utils. MSRV is 1.94.1. Alternatively drop the unused `sigv4a` feature if Multi-Region Access Points are not supported. | The S3 client against SeaweedFS (`force_path_style`, custom endpoint). This was not checked with the resolver. |
| R6 | Majors | tonic 0.12 → 0.13+ to drop rustls-pemfile (tonic-build and prost changes); pyo3 0.24 → 0.29 in `koda-command-guard`, which must happen before the wheel ships in any image (`koda/services/command_guard.py:11-14` says production intends to install it). | API renames across pyo3 0.25–0.29 in `lib.rs`; gRPC codegen changes in tonic. |

Code or documentation change outside the lockfiles: add Postgres TLS support, or document a VPN-only requirement for multi-host cluster mode (NoTls is hard-coded at `rust/koda-postgres/src/lib.rs:155` and `rust/koda-policy-engine/src/store.rs:133`).

### 5.4 No-fix items and mitigations

| Item | Status | Mitigation |
|---|---|---|
| rustls-pemfile 2.2.0 (RUSTSEC-2025-0134, unmaintained) | No patched release | It parses only trusted operator PEM, so the risk is maintenance-only. Migrate to tonic ≥0.13 (R6). |
| pin-utils 0.1.0 (RUSTSEC-2026-0441, unmaintained) | No patched release | The AWS SDK bump (R5) removes it with no Koda manifest change. |
| minimatch 10.2.5 (GHSA-g3hv-75wg-m249) | No fix within the consumer's `^10.2.2` range; the latest typescript-estree (8.72.2) keeps that range. | Not reachable. Add a time-boxed pnpm `auditConfig` ignore with this rationale (no `auditConfig` exists today), or force an override to 11.0.1, which upstream does not support and which would need `pnpm lint:web`. Revisit when typescript-eslint moves to minimatch 11. |
| crypto-bigint and lru | They cannot be forced because of parent pins. | Fix through R5. |

### 5.5 Items that need risk acceptance if they are not fixed

Fixing these needs no approval. Each one needs operator approval under MISSION §13, plus an entry in REMAINING_RISKS.md per M1-E7-T2..T4 "Done when", only if it is accepted rather than fixed.

- **minimatch GHSA-g3hv-75wg-m249**: the only route to a green `pnpm audit --audit-level=moderate` short of an unsupported override.
- **Pillow, if 13.0.0 is deferred**: the reachable high and moderate advisories remain, 16 of the 18 if 12.3.0 is applied, and are only partly mitigated by the `formats=` allow-list.
- **cryptography 48.x, if 50.x is deferred**: GHSA-g6cj, jwv3 and m2h6 stay flagged even though they are not reachable. GHSA-537c is fixed by 48.0.1.
- **filelock 3.x and soupsieve ≤2.10, if their major bumps are deferred**: these are not-reachable advisories that keep failing `pip-audit --strict`.
- **Any not-reachable Node or Rust item left in the tree**: it needs an explicit audit ignore with a rationale, because the gates fail on it. Examples are quinn-proto under `cargo audit`, and every moderate-or-higher dev item under `pnpm audit` without `--prod`.
- **Postgres NoTls in multi-host cluster mode, if TLS is not added**: RUSTSEC-2026-0179 and 0178 remain exploitable by a man-in-the-middle in that topology, even after R3 fixes the parser bugs.
- **Unmaintained crates rustls-pemfile and pin-utils**: these need acceptance until R6 and R5 land, if the `cargo audit` gate fails on unmaintained notices. How the gate treats informational notices was not checked.

## 6. Open questions and caveats

General:

1. **The Dependabot list is not reconciled.** Run `gh api` with pagination over the Dependabot alerts endpoint from a session that has access, de-duplicate by GHSA, package and manifest, and match the results against this report. The local `origin/main` ref was not fetched, so it may lag GitHub's default branch.
2. **No image was built or inspected.** Image contents are inferred from the Dockerfiles and a local reproduction of `uv export` (local uv 0.11.32, while the images pin `UV_VERSION=0.10.7`; the same default-group behaviour was assumed). The absence of Ghostscript is inferred from the apt lines and Playwright `--with-deps`. Release workflows, CI gates and `pnpm audit` were not re-run; the gate effects described here are inferred from workflow files.
3. **Major-version upgrades are judged from API usage and metadata only.** This covers Pillow 13, filelock 4, soupsieve 4, cryptography 50, pyo3 0.29, tonic 0.13+ and sharp 0.35. Nothing was installed or tested.
4. **Fixed-version availability has mixed sources.** For Python and many Node and Rust packages, verifiers checked the registry directly (PyPI JSON, the npm registry and bulk advisory endpoint, the crates.io index). Others rest on the audit data's patched ranges or the local sparse cargo index cache, which may be stale: fflate, baseline-browser-mapping, @babel/core, minimatch, and the Rust packages without a verdict.
5. **The advisory snapshot is dated.** Verifiers found advisories newer than the audit data: GHSA-xp26-3454-mjgp (@vitest/mocker 4.1.11) and GHSA-vfpm-58rq-9qcg (vite 8.2.0). Re-run all three audits right before each remediation batch.
6. **Advisory text was treated as data.** Claims in it were checked against installed source, for example multidict's claim about aio-libs servers. The npm GHSA records were not available as local files, so Node semantics come from the pnpm overview text. GHSA-5p4m-2wfm-xmqj has no CVE.

Python:

7. **The local `.venv` is Python 3.13, but the images use 3.12.** rapidocr-onnxruntime (marker `<3.13`) is therefore absent locally. Its image-loading path (`artifact_ingestion._ocr_image_path`) and its behaviour under Pillow 13 are not verified.
8. **cryptography GHSA-537c stays unclear** because OpenSSL secadv 20260609 is not in the collected data.
9. **aiohttp server reachability assumes exposure** through the nginx proxy (`packages/cli/release/bundle/proxy/nginx.conf`), the Next.js server and channel webhooks. Whether nginx normalisation blocks mfx4 (smuggling) or 5wr8 (slow headers) was not tested.
10. **Three findings are conditional:** asyncssh GHSA-rw4j needs a malicious or compromised bastion; certifi needs an attacker holding a compromised eMudhra intermediate key; urllib3 GHSA-gh4c's infinite loop was not reproduced (code path only), and GHSA-8988 exposure exists only for agent scripts using `verify=False` through an https proxy.
11. **pip's vendored certifi is not covered by the certifi bump**, and whether pip uses it or the system store was not checked.
12. **The dev group is shipped in production images** (`--no-dev` is missing). This contradicts the premise of `security.yml:79-89`. The Python 3.12 image dependencies that a 3.13 scan could miss were checked only for fsspec.

Node:

13. **Some Node evidence comes from the local Turbopack build** in `apps/web/.next` (BUILD_ID 2026-11-14 03:19): the server-reference, images and prerender manifests, and the client chunks. A CI or image build could differ if the source changes.
14. **The analyst and verifier disagree on next and sharp.** The open question is whether any optimizer-accepted local URL serves attacker-controlled bytes. `detectContentType` calls `sharp().metadata()` before the SVG gate, so non-image responses do reach the decoder. Per the analyst, GHSA-6gpp also requires a single i18n locale, which `next.config.ts` lacks.
15. **zod:** whether the `z.array` schemas parse attacker-supplied server input was not traced by the verifier.
16. **Several build-only packages are on disk in the runner image** (nanoid, browserslist, source-map-js, postcss), either through the `pnpm install --prod` resolution of styled-jsx's optional peer or as next dependencies, but none is loaded. Next's bundled `next/dist/compiled/{nanoid,browserslist}` copies are invisible to `pnpm audit` and overrides; the vendored browserslist also lacks the bounded-cache fix and is called only at build time.
17. **Runner image hardening:** `apps/web/Dockerfile:64` copies the builder's `apps/web`, including dev `node_modules` symlinks. These dangle today, but a hoisted `nodeLinker` would ship vite, vitest, jsdom, undici and eslint. Copy only `.next`, `public`, `server.mjs` and `package.json`.
18. **Overrides are not inert.** The analyst called the brace-expansion overrides stale. The verifier showed that the 1.x override actively pins 1.1.13, and the 5.x and picomatch overrides are stale but still act on future or peer ranges.
19. **The not-reachable verdicts for dev tooling cover the repository's scripted use** (`vitest run`, `eslint .`). A developer who runs `vitest --ui`, `vitest --api` or browser mode opens a Vite server locally, which makes the vite and @vitest/mocker advisories relevant on that workstation, especially the Windows launch-editor ones.
20. **Fork PRs run lint and test in CI** (`pr-quality.yml`, `permissions: contents: read`, no `pull_request_target`). Their authors can already run arbitrary code there, so the DoS-class advisories add nothing; the secret exposure of those jobs was not audited.
21. **pnpm audit's `dev:false` flag is not reliable for workspace importers.** Dev classification comes from the `apps/web` devDependencies and a reverse-dependency walk of the lockfile.
22. **Not audited:** the provider CLIs installed globally and unpinned in the root `Dockerfile` (`@anthropic-ai/claude-code`, `@openai/codex`, `@google/gemini-cli`; tracked by M1-E7-T1); MCP servers launched via `uvx`, which run in their own environments; and the release SBOM (`packages/cli/release/bundle/sbom.spdx.json`), which does not list the web dependencies.

Rust:

23. **Matcher limitations:**
    - It matches lockfile entries, not the compiled graph, so quinn-proto and quinn-udp appear through reqwest's weak feature `quinn?/ring`.
    - It does not flag yanked fixed versions: crypto-bigint 0.7.6–0.7.8 are yanked.
    - It does no feature- or function-level filtering.
    - RUSTSEC-2026-0387 has no lower bound and names APIs from later crypto-bigint series, so its range may be too broad upstream.
24. **pyo3 is not in the local registry cache.** `cargo tree` failed offline for `koda-command-guard`, so the assessment rests on `Cargo.lock`, `Cargo.toml` and `lib.rs`.
25. **Not checked: whether the Debian ca-certificates in the artifact image still contain the emSign roots.** That decides whether RUSTSEC-2026-0382 affects the artifact-engine S3 client on https endpoints; the bot-gateway path is affected either way.
26. **Feature analysis was done per binary** with `cargo tree -p <bin>`, mirroring the Dockerfiles' `cargo build --release -p <crate>`. Workspace-wide trees overstate features.
27. **koda-bot-gateway and koda-policy-engine are opt-in compose profiles** that are not in the release bundle or the release image builds. They are still classed as runtime because they are documented and supported.
28. **h2 reachability assumes a peer on the backend network** (an LLM-driven agent in the app container) is a realistic attacker position, consistent with R-04. Network sandboxing of agent shell paths was not traced.
29. **The Postgres cluster-mode finding assumes SCRAM runs on every connection**, which is the documented default of the `pgvector/pgvector:pg16` image; the image was not run.
30. **Some severity labels were assigned by the analyst** because the advisories carry no CVSS: rustls-webpki and webpki-roots high; crypto-bigint, pyo3 and quinn-udp moderate; ctutils low. h2 is low per the advisory text. The CVSS 4.0 scores for postgres-protocol and tokio-postgres (about 8.7 and 6.9) were derived from their vectors without a calculator.
31. **Dry runs were not builds.** `cargo update --dry-run`, `pnpm update --lockfile-only` and `uv lock --dry-run` ran on scratch copies only; nothing was built.

Out of scope, noticed while tracing (route to an auth/SSRF review):

32. `/api/elevenlabs/voices` is not in the proxy's `API_GATED_PREFIXES` (`src/proxy.ts:308-329`), and the route never checks an operator token.
33. The `/api/channels/*` routes rely only on the proxy's check that a session cookie is present, and the validate route makes outbound credential-check requests without verifying the token.
34. `server.mjs:130` does not pin Host, which matters if Server Actions are ever added (GHSA-89xv).
